"""Poids mesurés des signatures C5 : taux de confirmation par signature,
intervalle de Wilson, poids borné appliqué à la confiance des NEED et
Learning de mesure dédupliqué.

Deux modes : READ sans base (dépôts et lectures injectés/mocks) et
persistance réelle (sautée sans ``JUMEAU_PG_DSN``, comme les autres tests
Postgres).
"""
from datetime import datetime, timezone

import pytest

from meridian.adapters.outbound.postgres import (
    boucle, detecteurs_besoins, entreprise_depot, signatures_besoins,
)
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)


class DepotMemoire:
    """Dépôt minimal en mémoire : même contrat d'appel que ``enregistrer_boucle``
    et ``enregistrer_objet``, sur des lignes à ``donnees`` imbriquées comme
    ``objet_entreprise`` (payload plat ou ``donnees`` explicite)."""

    def __init__(self):
        self.objets = {}

    def __call__(self, conn, tenant, objets):
        lot = objets if isinstance(objets, list) else [objets]
        lignes = []
        for brut in lot:
            charge = dict(brut.get("donnees") or {})
            charge.update({cle: valeur for cle, valeur in brut.items() if cle not in (
                "id", "tenant_id", "famille", "type", "mode", "titre", "version",
                "cree_le", "observe_le", "valide_depuis", "valide_jusqua",
                "maj_le", "donnees")})
            ligne = {"id": brut["id"], "tenant_id": tenant,
                     "famille": brut.get("famille"), "type": brut.get("type"),
                     "mode": brut.get("mode"), "titre": brut.get("titre", ""),
                     "donnees": charge,
                     "version": self.objets.get(brut["id"], {}).get("version", 0) + 1}
            self.objets[brut["id"]] = ligne
            lignes.append(ligne)
        return lignes[0] if not isinstance(objets, list) else lignes

    def par_type(self, type_):
        return [ligne for ligne in self.objets.values() if ligne["type"] == type_]


def need(identifiant, signature, statut, **donnees):
    charge = {"signature": signature, "statut": statut,
              "refutable_par": "signal absent 30 jours", "exigence": "cohérent",
              "ecart": "écart", "sujet_detection": f"{identifiant}|sujet"}
    charge.update(donnees)
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "NEED", "mode": "PROPOSED", "titre": identifiant,
            "donnees": charge}


def needs_contournement(**extra):
    """6 jugés (3 confirmés, 2 réfutés, 1 périmé compté à part) + 3 non jugés."""
    needs = [
        need("c-ouv-1", "contournement", "OUVERT"),
        need("c-ouv-2", "contournement", "OUVERT"),
        need("c-qua", "contournement", "QUALIFIE"),
        need("c-cor-1", "contournement", "CORROBORE"),
        need("c-cor-2", "contournement", "CORROBORE"),
        need("c-adr", "contournement", "ADRESSE"),
        need("c-ref-1", "contournement", "REFUTE"),
        need("c-ref-2", "contournement", "REFUTE"),
        need("c-per", "contournement", "PERIME"),
    ]
    needs += [need(f"c-x-{n}", "contournement", statut)
              for n, statut in enumerate(extra.get("statuts", ()))]
    return needs


def assertion(subject, predicate, object_, mode, identifiant=1):
    return {"id": identifiant, "subject": subject, "predicate": predicate,
            "object": object_, "mode": mode, "source": "test",
            "environment": "prod", "observed_at": MAINTENANT.isoformat()}


def situation(identifiant, twin_ids):
    return {"id": identifiant, "tenant_id": TENANT, "famille": "emergence",
            "type": "SITUATION", "mode": "OBSERVED", "titre": identifiant,
            "observe_le": MAINTENANT.isoformat(),
            "donnees": {"twin_ids": list(twin_ids)}}


# --- Mesure ---


def test_stats_comptes_par_signature_et_statut():
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement()
        + [need("r-1", "recurrence", "OUVERT")])

    contournement = stats["contournement"]
    assert contournement["total"] == 9
    assert contournement["comptes"] == {
        "OUVERT": 2, "QUALIFIE": 1, "CORROBORE": 2, "ADRESSE": 1,
        "REFUTE": 2, "PERIME": 1}
    # jugés = CORROBORE + ADRESSE + REFUTE ; PERIME est compté à part
    assert contournement["confirmes"] == 3
    assert contournement["juges"] == 5
    assert contournement["perimes"] == 1

    recurrence = stats["recurrence"]
    assert recurrence["juges"] == 0
    assert recurrence["taux_confirme"] is None
    assert recurrence["ic95"] is None  # jamais un taux sans n


def test_taux_confirme_exact_et_intervalle_wilson():
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    contournement = stats["contournement"]
    assert contournement["taux_confirme"] == pytest.approx(3 / 5)
    ic = contournement["ic95"]
    assert ic["bas"] < contournement["taux_confirme"] < ic["haut"]
    assert ic["bas"] == pytest.approx(0.23, abs=0.03)
    assert ic["haut"] == pytest.approx(0.89, abs=0.03)
    assert ic["z"] == pytest.approx(1.96)


def test_intervalle_wilson_jamais_un_taux_sans_n():
    assert signatures_besoins.intervalle_wilson(0, 0) is None
    ic = signatures_besoins.intervalle_wilson(8, 12)
    assert ic["bas"] < 8 / 12 < ic["haut"]
    with pytest.raises(signatures_besoins.SignaturesInvalide):
        signatures_besoins.intervalle_wilson(5, 2)


def test_statut_inconnu_compte_a_part():
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=[need("x-1", "contournement", "BIZARRE")])
    entree = stats["contournement"]
    assert entree["comptes"]["AUTRE"] == 1
    assert entree["juges"] == 0


# --- Poids ---


def test_poids_neutre_sous_le_minimum_de_preuves():
    assert signatures_besoins.poids(
        "contournement", {"taux_confirme": 0.9, "juges": 4}) == 1.0
    assert signatures_besoins.poids(
        "contournement", {"taux_confirme": None, "juges": 0}) == 1.0
    assert signatures_besoins.poids("contournement", None) == 1.0


def test_poids_taux_haut_au_dessus_de_un():
    assert signatures_besoins.poids(
        "contournement", {"taux_confirme": 0.8, "juges": 20}) > 1.0


def test_poids_taux_bas_en_dessous_de_un():
    facteur = signatures_besoins.poids(
        "contournement", {"taux_confirme": 0.1, "juges": 20})
    assert signatures_besoins.POIDS_MIN <= facteur < 1.0


def test_poids_bornes_et_monotonie():
    haut = signatures_besoins.poids("s", {"taux_confirme": 1.0, "juges": 100})
    bas = signatures_besoins.poids("s", {"taux_confirme": 0.0, "juges": 100})
    assert haut == pytest.approx(signatures_besoins.POIDS_MAX)
    assert bas == pytest.approx(signatures_besoins.POIDS_MIN)
    taux = [signatures_besoins.poids("s", {"taux_confirme": t / 10, "juges": 50})
            for t in range(11)]
    assert taux == sorted(taux)  # monotone croissant en taux


def test_poids_pour_assainit_le_dict():
    assert signatures_besoins.poids_pour(None, "x") == 1.0
    assert signatures_besoins.poids_pour({}, "x") == 1.0
    assert signatures_besoins.poids_pour({"x": "n'importe quoi"}, "x") == 1.0
    assert signatures_besoins.poids_pour({"x": float("nan")}, "x") == 1.0
    assert signatures_besoins.poids_pour({"x": 99.0}, "x") == 1.5
    assert signatures_besoins.poids_pour({"x": 0.01}, "x") == 0.2


# --- Application : confiance des NEED créés ---


def detecter(depot, **kwargs):
    kwargs.setdefault("maintenant", MAINTENANT)
    kwargs.setdefault("persister", depot)
    return detecteurs_besoins.detecter(None, TENANT, **kwargs)


def test_detecter_avec_poids_ajuste_la_confiance():
    depot = DepotMemoire()
    rapport = detecter(
        depot, signature="contournement",
        reponses=[], situations=[], needs=[], unknowns=[], creer_intention=None,
        assertions=[assertion("app-cartes", "CONSOMME", "GET /a", "declared", 1),
                    assertion("app-cartes", "CONSOMME", "GET /b", "observed", 2)],
        poids={"contournement": 1.4})

    assert rapport["totaux"]["crees"] == 1
    [cree] = depot.par_type("NEED")
    assert cree["donnees"]["poids_signature"] == pytest.approx(1.4)
    assert cree["donnees"]["confiance"] == pytest.approx(0.5 * 1.4)
    assert cree["donnees"]["confiance_detecteur"] == pytest.approx(0.5)


def test_detecter_sans_poids_confiance_neutre():
    depot = DepotMemoire()
    detecter(
        depot, signature="contournement",
        reponses=[], situations=[], needs=[], unknowns=[], creer_intention=None,
        assertions=[assertion("app-cartes", "CONSOMME", "GET /a", "declared", 1),
                    assertion("app-cartes", "CONSOMME", "GET /b", "observed", 2)])
    [cree] = depot.par_type("NEED")
    assert cree["donnees"]["poids_signature"] == pytest.approx(1.0)
    assert cree["donnees"]["confiance"] == pytest.approx(0.5)


def test_detecter_poids_borne_la_confiance():
    depot = DepotMemoire()
    detecter(
        depot, signature="recurrence",
        reponses=[], assertions=[], needs=[], unknowns=[], creer_intention=None,
        situations=[situation(f"sit-{n}", ["app-cartes"]) for n in range(3)],
        poids={"recurrence": 99.0})  # re-borné à POIDS_MAX
    [cree] = depot.par_type("NEED")
    assert cree["donnees"]["poids_signature"] == pytest.approx(1.5)
    assert cree["donnees"]["confiance"] == pytest.approx(0.75)


# --- Learning persisté ---


def test_learning_ecrit_quand_la_mesure_est_nouvelle():
    depot = DepotMemoire()
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    rapport = signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=depot,
        maintenant=MAINTENANT)

    assert rapport["totaux"]["ecrits"] == 1
    assert rapport["erreurs"] == []
    [learning] = depot.par_type("LEARNING")
    donnees = learning["donnees"]
    assert learning["famille"] == "resultat_apprentissage"
    assert donnees["signature"] == "contournement"
    assert donnees["taux"] == pytest.approx(0.6)
    assert donnees["n"] == 5
    assert donnees["origine"] == "signatures_besoins"
    assert "3 corroborés / 5 jugés = 0.60" in donnees["enonce"]
    assert "IC95" in donnees["enonce"]


def test_learning_pas_reecrit_a_l_identique():
    depot = DepotMemoire()
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=depot,
        maintenant=MAINTENANT)

    second = signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=depot.par_type("LEARNING"),
        persister=depot, maintenant=MAINTENANT)
    assert second["totaux"]["ecrits"] == 0
    assert second["ignores"][0]["raison"] == "mesure identique au dernier Learning"
    assert len(depot.par_type("LEARNING")) == 1


def test_learning_reecrit_quand_les_stats_changent():
    depot = DepotMemoire()
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=depot,
        maintenant=MAINTENANT)

    nouvelles = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement(statuts=("CORROBORE",)))
    second = signatures_besoins.capitaliser_mesures(
        None, TENANT, nouvelles, learnings=depot.par_type("LEARNING"),
        persister=depot, maintenant=MAINTENANT)
    assert second["totaux"]["ecrits"] == 1
    assert len(depot.par_type("LEARNING")) == 2
    assert depot.par_type("LEARNING")[1]["donnees"]["taux"] == pytest.approx(4 / 6)


def test_changement_non_juge_ne_reecrit_pas():
    """Un besoin OUVERT de plus ne change pas la mesure : l'empreinte est la même."""
    depot = DepotMemoire()
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=depot,
        maintenant=MAINTENANT)
    nouvelles = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement(statuts=("OUVERT",)))
    second = signatures_besoins.capitaliser_mesures(
        None, TENANT, nouvelles, learnings=depot.par_type("LEARNING"),
        persister=depot, maintenant=MAINTENANT)
    assert second["totaux"]["ecrits"] == 0


def test_aucun_learning_sans_besoin_juge():
    depot = DepotMemoire()
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=[need("r-1", "recurrence", "OUVERT")])
    rapport = signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=depot,
        maintenant=MAINTENANT)
    assert rapport["totaux"]["ecrits"] == 0
    assert rapport["ignores"][0]["signature"] == "recurrence"
    assert depot.par_type("LEARNING") == []


def test_erreur_d_ecriture_remonte_fail_closed():
    def persister_en_echec(conn, tenant, objet):
        raise RuntimeError("écriture refusée")
    stats = signatures_besoins.taux_par_signature(
        None, TENANT, needs=needs_contournement())
    rapport = signatures_besoins.capitaliser_mesures(
        None, TENANT, stats, learnings=[], persister=persister_en_echec,
        maintenant=MAINTENANT)
    assert rapport["totaux"]["ecrits"] == 0
    assert rapport["totaux"]["erreurs"] == 1
    assert "refusée" in rapport["erreurs"][0]["erreur"]


# --- Persistance Postgres réelle ---


@besoin_pg
def test_mesure_reelle_stats_learning_et_dedup(conn):
    for rang, (statut, porteur) in enumerate([
            ("OUVERT", ""), ("CORROBORE", "equipe-cartes"),
            ("CORROBORE", "equipe-cartes"), ("ADRESSE", ""),
            ("REFUTE", ""), ("REFUTE", ""), ("PERIME", "")]):
        boucle.enregistrer_boucle(conn, TENANT, boucle.Need(
            id=f"need-c5-{rang}", tenant_id=TENANT, titre=f"Besoin {rang}",
            porteur=porteur, exigence="cohérent", ecart="écart",
            refutable_par="signal absent 30 jours", statut=statut,
            signature="contournement"))

    mesures = signatures_besoins.mesurer(conn, TENANT, maintenant=MAINTENANT)
    stats = mesures["stats"]["contournement"]
    assert stats["juges"] == 5 and stats["confirmes"] == 3
    assert stats["taux_confirme"] == pytest.approx(0.6)
    assert mesures["poids"]["contournement"] > 1.0

    learnings = [l for l in entreprise_depot.lister_objets(
        conn, TENANT, type_="LEARNING", limite=100)
        if (l.get("donnees") or {}).get("origine") == "signatures_besoins"]
    assert len(learnings) == 1
    donnees = learnings[0]["donnees"]
    assert donnees["signature"] == "contournement"
    assert donnees["n"] == 5 and donnees["taux"] == pytest.approx(0.6)

    # même mesure : rien de réécrit ; une réfutation de plus : nouvelle mesure
    assert signatures_besoins.mesurer(
        conn, TENANT)["learnings"]["totaux"]["ecrits"] == 0
    boucle.enregistrer_boucle(conn, TENANT, boucle.Need(
        id="need-c5-refute", tenant_id=TENANT, titre="Réfuté",
        exigence="cohérent", ecart="écart",
        refutable_par="signal absent 30 jours", statut="REFUTE",
        signature="contournement"))
    troisieme = signatures_besoins.mesurer(conn, TENANT)
    assert troisieme["learnings"]["totaux"]["ecrits"] == 1
    assert troisieme["stats"]["contournement"]["taux_confirme"] == pytest.approx(0.5)


@besoin_pg
def test_detecter_reel_poids_applique_a_la_confiance(conn):
    from meridian.domain.interfaces import Assertion, InterfaceGraph
    from meridian.adapters.outbound.postgres import interfaces_depot

    interfaces_depot.enregistrer(conn, TENANT, InterfaceGraph(assertions=[
        Assertion(subject="app-c5", predicate="CONSOMME", object="GET /v1/payments",
                  mode="declared", source="code", locator="spec", environment="prod",
                  confidence=0.9, evidence="contrat"),
        Assertion(subject="app-c5", predicate="CONSOMME", object="POST /legacy/pay",
                  mode="observed", source="runtime", locator="otlp", environment="prod",
                  confidence=0.8, evidence="trace"),
    ]))

    rapport = detecteurs_besoins.detecter(
        conn, TENANT, signature="contournement", maintenant=MAINTENANT,
        poids={"contournement": 1.3})
    assert rapport["erreurs"] == []
    [cree] = rapport["crees"]
    relu = boucle.lire_boucle(conn, TENANT, cree["id"])
    assert relu["donnees"]["poids_signature"] == pytest.approx(1.3)
    assert relu["donnees"]["confiance"] == pytest.approx(0.65)
    assert relu["donnees"]["confiance_detecteur"] == pytest.approx(0.5)
