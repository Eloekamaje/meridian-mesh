"""Tests d'intégration réelle Postgres du pont canonique (skip sans JUMEAU_PG_DSN)."""
from __future__ import annotations

import copy

import pytest

from meridian.adapters.outbound.postgres import boucle, entreprise_depot, migration_canonique
from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
CLE = "cle-de-test-pont-canonique-32"
CLE_INTERNE = "cle-de-test-pont-interne-32"
DATE = "2026-11-05T09:00:00+00:00"
DECIDE_LE = "2026-11-06T10:00:00+00:00"

SITUATION = {
    "id": "sit-pg-1", "tenant_id": TENANT, "titre": "Délai", "resume": "Délai en hausse",
    "statut": "poursuivie", "priorite": "haute", "decision": "Automatiser",
    "decidee_par": "comité", "decidee_le": DECIDE_LE, "detectee": DATE, "cree_le": DATE,
    "jumeaux": ["paiements"], "options": [{"titre": "Automatiser"}],
}


@pytest.fixture(autouse=True)
def _cles(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv(pont.PONT_KEY_INTERNE_ENV, CLE_INTERNE)


def _situation(**champs):
    base = copy.deepcopy(SITUATION)
    base.update(champs)
    return base


def _evenement(document, source_event_id):
    return pont.evenement_depuis_situation(
        document, source_event_id=source_event_id, maintenant="2026-11-06T12:00:00+00:00")


@besoin_pg
def test_timestamps_egaux_b_puis_c_puis_b_ne_s_ecrasent_pas(conn):
    b = _situation(decision="B", maj_le="2026-11-06T12:00:00+00:00")
    c = _situation(decision="C", maj_le="2026-11-06T12:00:00+00:00")
    pont_pg.appliquer_evenement(conn, _evenement(b, "b"))
    version = entreprise_depot.lire_objet(conn, TENANT, "dec-sit-sit-pg-1-1")["version"]

    resultat = pont_pg.appliquer_evenement(conn, _evenement(c, "c"))
    pont_pg.appliquer_evenement(conn, _evenement(b, "b-rejoue"))

    assert resultat["ecrits"] == []
    decision = boucle.lire_boucle(conn, TENANT, "dec-sit-sit-pg-1-1")
    assert decision["donnees"]["choix"] == "B"
    assert decision["version"] == version


@besoin_pg
def test_migration_12h_puis_live_08h_est_ignore(conn):
    migration = _situation(maj_le="2026-11-06T12:00:00+00:00")
    payload = migration_canonique.objet_depuis_situation(migration, TENANT)
    entreprise_depot.enregistrer_objet(conn, TENANT, payload)
    avant = copy.deepcopy(entreprise_depot.lire_objet(conn, TENANT, "sit-pg-1"))

    live = _situation(statut="en observation", maj_le="2026-11-06T08:00:00+00:00")
    resultat = pont_pg.appliquer_evenement(conn, _evenement(live, "live-vieux"))

    assert resultat["ecrits"] == []
    assert entreprise_depot.lire_objet(conn, TENANT, "sit-pg-1")["donnees"] == \
        avant["donnees"]


@besoin_pg
def test_parent_outcome_est_relu_et_fusionne(conn):
    pont_pg.appliquer_evenement(conn, _evenement(_situation(), "maj-1"))
    initiative = entreprise_depot.lire_objet(conn, TENANT, "ini-dec-sit-sit-pg-1-1")
    # Ajoute un champ de migration que le parent doit conserver.
    initiative["donnees"]["description_migree"] = "à conserver"
    entreprise_depot.enregistrer_objet(conn, TENANT, initiative)
    outcome = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id="ini-dec-sit-sit-pg-1-1",
        mesure={"metrique": "delai", "valeur": 2}, metrique="delai",
        periode="2026-11", source_event_id="out-pg")

    resultat = pont_pg.appliquer_evenement(conn, outcome)

    parent = entreprise_depot.lire_objet(conn, TENANT, "ini-dec-sit-sit-pg-1-1")
    assert outcome["canonical_ids"][0] in parent["donnees"]["outcome_ids"]
    assert parent["donnees"]["description_migree"] == "à conserver"
    assert "ini-dec-sit-sit-pg-1-1" in resultat["ecrits"]


@besoin_pg
def test_decisions_proposees_ne_sont_pas_promues(conn):
    situation = _situation(
        statut="décidée",
        decisions=[{"statut": "proposee", "options": ["Option A"], "par": "alice"}],
    )
    situation.pop("decision", None)
    situation.pop("decidee_par", None)
    pont_pg.appliquer_evenement(conn, _evenement(situation, "proposee-pg"))

    decision = boucle.lire_boucle(conn, TENANT, "dec-sit-sit-pg-1-1", as_dict=False)
    assert decision.statut == "PROPOSED"
    assert entreprise_depot.lire_objet(conn, TENANT, "ini-dec-sit-sit-pg-1-1") is None


@besoin_pg
def test_id_modifie_meme_signe_est_refuse(conn):
    evenement = _evenement(_situation(), "maj-1")
    evenement["_id"] = "id-forge-signe"
    evenement = pont.signer_evenement(evenement)

    with pytest.raises(pont.PontInvalide):
        pont_pg.appliquer_evenement(conn, evenement)


@besoin_pg
def test_source_maj_absente_est_refusee(conn):
    evenement = _evenement(_situation(), "maj-1")
    evenement.pop("source_maj_le")
    evenement = pont.signer_evenement(evenement)

    with pytest.raises(pont.PontInvalide):
        pont_pg.appliquer_evenement(conn, evenement)


@besoin_pg
def test_canonical_id_incoherent_est_refuse(conn):
    evenement = _evenement(_situation(), "maj-1")
    evenement["canonical_id"] = "sit-incoherent"
    evenement["_id"] = pont.identifiant_evenement(
        TENANT, evenement["operation"], "sit-incoherent", evenement["source_event_id"])
    evenement["source"]["id"] = "sit-incoherent"
    evenement["source"]["hash"] = pont.hash_contenu(evenement["payload"])
    evenement["hash"] = pont.hash_contenu(evenement["payload"])
    evenement = pont.signer_evenement(evenement)

    with pytest.raises(pont.PontInvalide):
        pont_pg.appliquer_evenement(conn, evenement)


@besoin_pg
def test_parent_exploitation_marker_est_accepte(conn):
    pont_pg.appliquer_evenement(conn, _evenement(_situation(), "maj-1"))
    parent = entreprise_depot.lire_objet(conn, TENANT, "ini-dec-sit-sit-pg-1-1")
    parent["donnees"]["_pont"] = {
        "origine": "exploitation",
        "source": {"collection": "exploitation", "id": "ini-dec-sit-sit-pg-1-1"},
    }
    entreprise_depot.enregistrer_objet(conn, TENANT, parent)
    outcome = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id="ini-dec-sit-sit-pg-1-1",
        mesure={"metrique": "delai", "valeur": 2}, metrique="delai",
        periode="2026-11", source_event_id="out-exploitation")

    pont_pg.appliquer_evenement(conn, outcome)

    apres = entreprise_depot.lire_objet(conn, TENANT, "ini-dec-sit-sit-pg-1-1")
    assert outcome["canonical_ids"][0] in apres["donnees"]["outcome_ids"]


@besoin_pg
def test_croise_b_parent_exploitation_marque_puis_live_c1(conn):
    """A crée le parent, B ajoute Expression/Opportunity, C1 met à jour le parent."""
    try:
        from meridian.adapters.outbound.postgres import objets_exploitation
        from meridian.domain import construction_objets_exploitation as construction
    except ImportError:
        pytest.skip("lot B non mergé : test croisé B → C1 en attente")

    situation = boucle.Situation(
        id="sit-b-cross", tenant_id=TENANT, titre="Situation B/C1",
        description="Créée par A", statut="CANDIDATE", priorite="MOYENNE",
        cree_le=DATE, observe_le=DATE, valide_depuis=DATE)
    investigation = boucle.ouvrir_investigation(
        situation, id="inv-b-cross", titre="Comprendre B/C1")
    boucle.enregistrer_boucle(conn, TENANT, [situation, investigation])

    expression = construction.nouvelle_expression(
        situation, tenant_id=TENANT, formulation="Expression B")
    opportunity = construction.nouvelle_opportunite(
        expression, situation=situation, titre="Opportunité B")
    objets_exploitation.enregistrer_objets_exploitation(
        conn, TENANT, [expression, opportunity])

    parent = entreprise_depot.lire_objet(conn, TENANT, "sit-b-cross")
    marqueur = (parent.get("donnees") or {}).get("_pont")
    if not (isinstance(marqueur, dict) and marqueur.get("origine") == "exploitation"):
        pytest.skip(
            "B _persister_parent ne pose pas encore _pont.origine=exploitation : "
            "test croisé B → C1 en attente")
    assert marqueur["source"] == {
        "collection": "exploitation", "id": "sit-b-cross"}

    live = {
        "id": "sit-b-cross", "tenant_id": TENANT, "titre": "Situation B/C1",
        "resume": "Mise à jour C1", "statut": "en observation",
        "priorite": "haute", "maj_le": "2026-11-06T12:00:00+00:00",
        "cree_le": DATE, "jumeaux": ["paiements"],
    }
    resultat = pont_pg.appliquer_evenement(
        conn, pont.evenement_depuis_situation(
            live, source_event_id="c1-parent",
            maintenant="2026-11-06T12:00:00+00:00"))

    apres = entreprise_depot.lire_objet(conn, TENANT, "sit-b-cross")
    assert "sit-b-cross" in resultat["ecrits"]
    assert apres["donnees"]["expression_id"] == expression.id
    assert apres["donnees"]["statut"] == "OBSERVING"


@besoin_pg
def test_initiative_deja_materialisee_par_la_situation_est_compatible(conn):
    pont_pg.appliquer_evenement(conn, _evenement(_situation(), "maj-1"))
    initiative = {
        "id": "init-pg-autre", "tenant_id": TENANT, "titre": "Suite",
        "statut": "acceptee", "decision_id": "dec-sit-sit-pg-1-1",
        "maj_le": "2026-11-06T12:00:00+00:00", "cree_le": DATE,
    }

    resultat = pont_pg.appliquer_evenement(
        conn, pont.evenement_depuis_initiative(
            initiative, source_event_id="init-pg",
            maintenant="2026-11-06T12:00:00+00:00"))

    assert resultat["ecrits"] == ["ini-dec-sit-sit-pg-1-1"]
    assert entreprise_depot.lire_objet(
        conn, TENANT, "ini-dec-sit-sit-pg-1-1")["version"] == 2


@besoin_pg
def test_outcome_meme_quand_maj_le_croissant_est_applique(conn):
    """Deux Outcomes même `quand` : `maj_le` arbitre la correction, pas `mesure_le`."""
    pont_pg.appliquer_evenement(conn, _evenement(_situation(), "maj-1"))
    initiative_id = "ini-dec-sit-sit-pg-1-1"
    premier = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id=initiative_id,
        mesure={"metrique": "delai", "valeur_observee": 7}, metrique="delai",
        periode="2026-11", mesure_le="2026-11-05T09:00:00+00:00",
        maj_le="2026-11-05T09:01:00+00:00", interpretation="version 1",
        source_event_id="out-meme-quand-1")
    second = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id=initiative_id,
        mesure={"metrique": "delai", "valeur_observee": 8}, metrique="delai",
        periode="2026-11", mesure_le="2026-11-05T09:00:00+00:00",
        maj_le="2026-11-05T09:02:00+00:00", interpretation="version 2",
        source_event_id="out-meme-quand-2")

    pont_pg.appliquer_evenement(conn, premier)
    pont_pg.appliquer_evenement(conn, second)

    outcome = boucle.lire_boucle(conn, TENANT, premier["canonical_ids"][0])
    assert outcome["donnees"]["interpretation"] == "version 2"
    assert outcome["donnees"]["valeur_observee"] == 8
    assert outcome["donnees"]["_pont"]["source_maj_le"] \
        == "2026-11-05T09:02:00+00:00"


@besoin_pg
def test_outcome_sur_initiative_api_refuse_la_modification_du_parent(conn):
    """Un Outcome n'écrase pas un parent sans provenance fiable (legacy/migration/exploitation)."""
    from meridian.adapters.outbound.postgres import entreprise_depot

    initiative = {
        "id": "ini-api-1", "tenant_id": TENANT, "famille": "decision",
        "type": "INITIATIVE", "mode": "DECLARED", "titre": "Initiative API",
        "donnees": {"decision_id": "dec-api-1", "statut": "PLANNED"},
    }
    entreprise_depot.enregistrer_objet(conn, TENANT, initiative)
    outcome = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id="ini-api-1",
        mesure={"metrique": "delai", "valeur_observee": 4}, metrique="delai",
        periode="2026-11", maj_le="2026-11-06T12:00:00+00:00",
        source_event_id="out-api-parent")

    with pytest.raises(pont.ConflitCanonique):
        pont_pg.appliquer_evenement(conn, outcome)
