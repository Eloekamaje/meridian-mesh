"""Exécuteurs de démonstration et registre minimal.

Le worker réel branchera ici les cas d'usage agentiques et les connecteurs. Le
registre garde le runtime indépendant de Strands et de FastAPI.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Mapping

import psycopg

from jumeau.execution.processus import ProcessManager


def cognitif_analyser(run: Mapping[str, Any]) -> Mapping[str, Any]:
    """Exécute le cas d'usage cognitif hors requête HTTP, dans le worker."""
    from jumeau import analyse_service

    payload = dict(run.get("payload") or {})
    analyse = payload.get("analyse") or payload
    acteur = str(run.get("acteur") or "demo")
    dsn = os.environ["JUMEAU_PG_DSN"]

    def connecter():
        return psycopg.connect(dsn, autocommit=True)

    def annule():
        from jumeau.execution import depot as depot_execution
        with psycopg.connect(dsn, autocommit=True) as conn:
            courant = depot_execution.obtenir_run(conn, str(run["tenant_id"]), str(run["run_id"]))
        return bool(courant and courant.get("cancel_requested_at"))

    processus = ProcessManager(connecter, run, verifier_annulation=annule)
    return asyncio.run(analyse_service.executer(
        tenant=str(run["tenant_id"]), acteur=acteur, payload=analyse,
        run_id=str(run["run_id"]), verifier_annulation=annule, processus=processus,
    ))


EXECUTEURS: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {
    "cognitif.analyser": cognitif_analyser,
}


def executeur_par_type(run: Mapping[str, Any]) -> Mapping[str, Any]:
    type_ = str(run.get("type") or "")
    executeur = EXECUTEURS.get(type_)
    if executeur is None:
        raise LookupError(f"aucun exécuteur pour le type {type_!r}")
    return executeur(run)
