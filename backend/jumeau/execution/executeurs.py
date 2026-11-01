"""Compatibilité : les exécuteurs vivent dans :mod:`meridian.application.execution.executeurs`."""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

import psycopg

from jumeau import analyse_service
from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application.execution import executeurs as _module


def _connecter():
    return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)


EXECUTEURS: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = (
    _module.creer_executeurs(
        analyse_service=analyse_service,
        connect=_connecter,
        depot=_depot,
    )
)
cognitif_analyser = EXECUTEURS["cognitif.analyser"]


def executeur_par_type(run: Mapping[str, Any]) -> Mapping[str, Any]:
    return _module.executeur_par_type(run, EXECUTEURS)


__all__ = ["EXECUTEURS", "cognitif_analyser", "executeur_par_type"]
