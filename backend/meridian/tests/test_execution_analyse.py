"""Intégration minimale du journal d'étapes au run `cognitif.analyser`."""
import asyncio
import os

import psycopg
import pytest

from meridian.application import analyse_service
from meridian.adapters.outbound.postgres import execution_depot as depot
from meridian.application.execution.modele import CommandeExecution
from meridian.adapters.outbound.postgres.execution_defaults import ProcessManager
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def _payload():
    return {
        "question": "Où est la dépendance ?",
        "situation_id": None,
        "twin_id": None,
        "twin_ids": [],
        "application_id": "app-test",
        "claim_ids": [],
        "profondeur": 2,
        "specialistes": ["preuve", "impact"],
        "profil": None,
        "autorite_max": None,
        "scope": "application",
        "domaine": None,
        "surface": None,
        "date": None,
        "options": [],
        "changements": {},
        "criteres": [],
        "session_id": None,
        "decision_id": None,
        "confidence": None,
        "max_tokens": 500,
    }


class RuntimeFactice:
    """Runtime minimal : aucun Postgres, aucun graphe, aucun spécialiste concret."""

    def mode_auth(self):
        return "demo"

    def assainir(self, valeur):
        return valeur

    async def agreger_portefeuille(self, tenant, *, domaine=None, limite=100):
        return {"propositions": [], "limites": [], "valeur": None}

    async def lancer_specialistes(self, noms, base, tenant):
        return []

    def proximite_graphe(self, tenant, twin_ids):
        return {}

    async def recuperer_memoire(self, tenant, **kwargs):
        return []

    def enrichir_pack(self, pack, candidats, *, max_tokens=None):
        return {**dict(pack), "memoire": []}

    async def memoriser_session(self, tenant, session_id, question, resume, *,
                                acteur, donnees=None):
        return None

    async def lire_calibration(self, tenant, prediction_id):
        return None

    async def calibrer_decision(self, tenant, decision_support, **kwargs):
        return None

    def decision_support_enrichi(self, decision_support, **kwargs):
        return {**dict(decision_support or {}), "contrefactuel": None}


def test_run_cognitif_journalise_les_quatre_etapes(conn):
    commande = CommandeExecution(
        tenant_id="banque", type="cognitif.analyser", idempotency_key="analyse-etapes",
        payload={"analyse": _payload()}, acteur="test",
    )
    run, _ = depot.creer_run(conn, commande)
    pris = depot.reclamer_run(conn, "w-test", 30)

    manager = ProcessManager(_factory(conn), pris)
    resultat = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="test", payload=_payload(),
        runtime=RuntimeFactice(), run_id=run["run_id"], processus=manager,
    ))

    assert resultat["evaluation"]
    etapes = {e["nom"]: e for e in depot.etapes_run(conn, "banque", run["run_id"])}
    assert list(etapes) == ["contexte", "specialistes", "reponse", "evaluation"]
    assert all(e["etat"] == "TERMINE" for e in etapes.values())
    assert etapes["specialistes"]["sortie"]["dossier"]["propositions"] == []
