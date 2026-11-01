"""Intégration minimale du journal d'étapes au run `cognitif.analyser`."""
import asyncio
import os
from types import SimpleNamespace

import psycopg
import pytest

from jumeau import analyse_service
from jumeau.execution import depot
from jumeau.execution.modele import CommandeExecution
from jumeau.execution.processus import ProcessManager
from jumeau.tests.conftest import besoin_pg

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


def test_run_cognitif_journalise_les_quatre_etapes(conn, monkeypatch):
    commande = CommandeExecution(
        tenant_id="banque", type="cognitif.analyser", idempotency_key="analyse-etapes",
        payload={"analyse": _payload()}, acteur="test",
    )
    run, _ = depot.creer_run(conn, commande)
    pris = depot.reclamer_run(conn, "w-test", 30)

    async def sans_specialiste(*args, **kwargs):
        return []

    async def sans_memoire(*args, **kwargs):
        return []

    monkeypatch.setattr(analyse_service, "_lancer_specialistes", sans_specialiste)
    monkeypatch.setattr(analyse_service, "_avec_connexion", sans_memoire)
    monkeypatch.setattr(analyse_service, "_proximite_graphe", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        analyse_service.resolveur_contexte, "resoudre",
        lambda *args, **kwargs: SimpleNamespace(
            entites=(), as_dict=lambda: {"tenant": "banque", "surface": "twin"}),
    )

    manager = ProcessManager(_factory(conn), pris)
    resultat = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="test", payload=_payload(),
        run_id=run["run_id"], processus=manager,
    ))

    assert resultat["evaluation"]
    etapes = {e["nom"]: e for e in depot.etapes_run(conn, "banque", run["run_id"])}
    assert list(etapes) == ["contexte", "specialistes", "reponse", "evaluation"]
    assert all(e["etat"] == "TERMINE" for e in etapes.values())
    assert etapes["specialistes"]["sortie"]["dossier"]["propositions"] == []
