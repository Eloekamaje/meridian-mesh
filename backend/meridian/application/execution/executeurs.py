"""Exécuteurs et registre minimal du runtime d'exécution.

Le registre reste indépendant de Strands, FastAPI et Postgres : la fabrique de
connexions, le dépôt et le service d'analyse sont injectés par l'adapter inbound.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Mapping

from meridian.application.execution.processus import ProcessManager


def executer_cognitif(
    run: Mapping[str, Any],
    *,
    analyse_service: Any,
    connect: Callable[[], Any],
    depot: Any,
) -> Mapping[str, Any]:
    """Exécute le cas d'usage cognitif hors requête HTTP, dans le worker."""
    payload = dict(run.get("payload") or {})
    analyse = payload.get("analyse") or payload
    acteur = str(run.get("acteur") or "demo")

    def annule():
        with connect() as conn:
            courant = depot.obtenir_run(
                conn, str(run["tenant_id"]), str(run["run_id"]))
        return bool(courant and courant.get("cancel_requested_at"))

    processus = ProcessManager(connect, run, verifier_annulation=annule, depot=depot)
    return asyncio.run(analyse_service.executer(
        tenant=str(run["tenant_id"]), acteur=acteur, payload=analyse,
        run_id=str(run["run_id"]), verifier_annulation=annule, processus=processus,
    ))


def creer_executeurs(
    *,
    analyse_service: Any,
    connect: Callable[[], Any],
    depot: Any,
) -> dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]:
    """Construit le registre des exécuteurs avec ses adapters injectés."""

    def cognitif_analyser(run: Mapping[str, Any]) -> Mapping[str, Any]:
        return executer_cognitif(
            run, analyse_service=analyse_service, connect=connect, depot=depot)

    return {"cognitif.analyser": cognitif_analyser}


def executeur_par_type(
    run: Mapping[str, Any],
    executeurs: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]],
) -> Mapping[str, Any]:
    type_ = str(run.get("type") or "")
    executeur = executeurs.get(type_)
    if executeur is None:
        raise LookupError(f"aucun exécuteur pour le type {type_!r}")
    return executeur(run)


__all__ = ["creer_executeurs", "executer_cognitif", "executeur_par_type"]
