"""Temporalité : bornes incluses/exclues, intervalles ouverts, fraîcheur, preuves et topologie datée."""
from datetime import datetime, timedelta, timezone

from jumeau import temporalite
from jumeau.graphe import Arete, GrapheMemoire, NoeudTwin

MAINTENANT = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def iso(jours=0):
    return (MAINTENANT - timedelta(days=jours)).isoformat()


def test_bornes_debut_inclus_fin_exclue_et_aliases():
    objet = {
        "id": "o",
        "valide_depuis": "2026-01-01T00:00:00+00:00",
        "valide_jusqua": "2026-02-01T00:00:00+00:00",
    }
    assert temporalite.est_valide(objet, "2026-01-01T00:00:00+00:00")
    assert temporalite.est_valide(objet, "2026-01-15T00:00:00+00:00")
    assert temporalite.est_valide(objet, "2026-01-31T23:59:59+00:00")
    assert not temporalite.est_valide(objet, "2025-12-31T23:59:59+00:00")
    assert not temporalite.est_valide(objet, "2026-02-01T00:00:00+00:00")

    aliases = {"valid_from": "2026-01-01", "valid_to": "2026-02-01"}
    assert temporalite.est_valide(aliases, "2026-01-01")
    assert not temporalite.est_valide(aliases, "2026-02-01")

    imbrique = {"id": "n", "donnees": {"valide_depuis": "2026-01-01",
                                       "valide_jusqua": "2026-02-01"}}
    assert temporalite.est_valide(imbrique, "2026-01-15")


def test_intervalles_ouverts_et_bornes_absentes():
    assert temporalite.est_valide({}, "2026-01-01")
    assert temporalite.est_valide({"valide_depuis": None, "valide_jusqua": None}, "2026-01-01")
    assert not temporalite.est_valide({"valide_depuis": "2026-06-01"}, "2026-05-31")
    assert temporalite.est_valide({"valide_depuis": "2026-06-01"}, "2026-06-01")
    assert temporalite.est_valide({"valide_jusqua": "2026-06-01"}, "2026-05-31")
    assert not temporalite.est_valide({"valide_jusqua": "2026-06-01"}, "2026-06-01")


def test_dates_invalides_ou_intervalle_inverse_sont_refuses():
    assert not temporalite.est_valide({}, "pas une date")
    assert not temporalite.est_valide({"valide_depuis": "pas une date"}, "2026-01-01")
    assert not temporalite.est_valide({"valide_jusqua": "pas une date"}, "2026-01-01")
    assert not temporalite.est_valide(
        {"valide_depuis": "2026-02-01", "valide_jusqua": "2026-01-01"}, "2026-01-15")


def test_etat_a_date_filtre_sans_modifier_ni_casser_sur_date_invalide():
    objets = [
        {"id": "avant", "valide_jusqua": "2026-01-01"},
        {"id": "pendant", "valide_depuis": "2026-01-01", "valide_jusqua": "2026-02-01"},
        {"id": "apres", "valide_depuis": "2026-02-01"},
    ]
    assert [objet["id"] for objet in temporalite.etat_a_date(objets, "2026-01-15")] == ["pendant"]
    assert temporalite.etat_a_date(objets, "pas une date") == []
    assert temporalite.etat_a_date([], "2026-01-15") == []


def test_fraicheur_age_seuil_et_date_manquante():
    fraiche = temporalite.fraicheur({"observe_le": iso(10)}, maintenant=MAINTENANT)
    assert fraiche["observed_at"] == iso(10)
    assert fraiche["age_jours"] == 10.0 and fraiche["stale"] is False
    assert fraiche["etat"] == "fraiche" and fraiche["connu"] is True

    limite = temporalite.fraicheur({"observe_le": iso(30)}, maintenant=MAINTENANT)
    assert limite["stale"] is False  # le seuil est strict

    perimee = temporalite.fraicheur({"observe_le": iso(31)}, maintenant=MAINTENANT)
    assert perimee["stale"] is True and perimee["etat"] == "perimee"

    absente = temporalite.fraicheur({}, maintenant=MAINTENANT)
    assert absente["observed_at"] is None and absente["age_jours"] is None
    assert absente["stale"] is True and absente["etat"] == "inconnue"
    assert absente["connu"] is False

    invalide = temporalite.fraicheur({"observe_le": "pas une date"}, maintenant=MAINTENANT)
    assert invalide["stale"] is True and invalide["connu"] is False


def test_preuves_perimees_par_fin_explicite_ou_observation():
    preuves = [
        {"id": "explicite-expiree", "valid_until": iso(5)},
        {"id": "explicite-limite", "valid_until": MAINTENANT.isoformat()},
        {"id": "explicite-valide", "valid_until": (MAINTENANT + timedelta(days=5)).isoformat()},
        {"id": "observee-ancienne", "observed_at": iso(45)},
        {"id": "observee-fraiche", "observed_at": iso(10)},
        {"id": "sans-date"},
        {"id": "date-invalide", "valid_until": "pas une date"},
    ]
    perimees = temporalite.preuves_perimees(preuves, MAINTENANT, seuil_jours=30)

    assert [preuve["id"] for preuve in perimees] == [
        "explicite-expiree", "explicite-limite", "observee-ancienne", "sans-date", "date-invalide",
    ]
    assert all(preuve in preuves for preuve in perimees)
    assert len(temporalite.preuves_perimees(preuves, "pas une date")) == len(preuves)


def graphe():
    g = GrapheMemoire()
    for identifiant in ("a", "b", "c"):
        g.upsert_twin(NoeudTwin(identifiant, "banque", "APPLICATION", identifiant.upper()))
    for identifiant in ("x", "y"):
        g.upsert_twin(NoeudTwin(identifiant, "assurance", "APPLICATION", identifiant.upper()))
    g.upsert_relation(Arete("r1", "banque", "a", "b"))
    g.upsert_relation(Arete("r2", "banque", "a", "c", valid_from="2026-12-01T00:00:00+00:00"))
    g.upsert_relation(Arete("r3", "banque", "b", "c", valid_from="2026-01-01T00:00:00+00:00",
                            valid_to="2026-02-01T00:00:00+00:00"))
    g.upsert_relation(Arete("r4", "assurance", "x", "y"))
    return g


def test_topologie_graphe_memoire_filtre_par_date_et_isole_le_tenant():
    store = graphe()
    topologie = temporalite.topologie_a_date(store, "banque", "2026-01-15T00:00:00+00:00")

    assert topologie["tenant"] == "banque"
    assert topologie["date"] == "2026-01-15T00:00:00+00:00"
    assert [noeud["id"] for noeud in topologie["noeuds"]] == ["a", "b", "c"]
    assert [arete["id"] for arete in topologie["aretes"]] == ["r1", "r3"]
    assert all(noeud["tenant_id"] == "banque" for noeud in topologie["noeuds"])
    assert all(arete["tenant_id"] == "banque" for arete in topologie["aretes"])
    assert topologie["limite"]

    plus_tard = temporalite.topologie_a_date(store, "banque", "2026-03-01T00:00:00+00:00")
    assert [arete["id"] for arete in plus_tard["aretes"]] == ["r1"]

    autre = temporalite.topologie_a_date(store, "assurance", "2026-01-15T00:00:00+00:00")
    assert [noeud["id"] for noeud in autre["noeuds"]] == ["x", "y"]
    assert [arete["id"] for arete in autre["aretes"]] == ["r4"]


def test_topologie_ignore_une_arete_dont_une_extremite_manque():
    class StoreScope:
        def __init__(self):
            self.appels = []

        def as_dict(self, tenant):
            self.appels.append(tenant)
            return {
                "noeuds": [{"id": "a", "tenant_id": tenant}, {"id": "c", "tenant_id": tenant}],
                "aretes": [
                    {"id": "ok", "tenant_id": tenant, "source": "a", "target": "c"},
                    {"id": "orpheline", "tenant_id": tenant, "source": "a", "target": "absent"},
                ],
            }

    store = StoreScope()
    topologie = temporalite.topologie_a_date(store, "banque", "2026-01-01")

    assert store.appels == ["banque"]
    assert [noeud["id"] for noeud in topologie["noeuds"]] == ["a", "c"]
    assert [arete["id"] for arete in topologie["aretes"]] == ["ok"]
