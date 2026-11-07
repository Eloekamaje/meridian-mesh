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
