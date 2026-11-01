"""Compatibilité : le moteur vit dans :mod:`meridian.application.execution.moteur`.

Le constructeur historique conserve sa fabrique de connexion par défaut et branche
le dépôt Postgres ; le nouveau code injecte explicitement ses adapters.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

import psycopg

from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application.execution import moteur as _module
from meridian.application.execution.modele import TransitionInvalide


def _dsn() -> str:
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise TransitionInvalide("JUMEAU_PG_DSN non configuré")
    return dsn


def _connexion_defaut():
    return psycopg.connect(_dsn(), autocommit=True)


class MoteurExecution(_module.MoteurExecution):
    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        executeur: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        *,
        worker_id: str | None = None,
        bail_secondes: int = 30,
        depot: Any = None,
    ):
        super().__init__(
            connect or _connexion_defaut,
            executeur,
            worker_id=worker_id,
            bail_secondes=bail_secondes,
            depot=depot or _depot,
        )


__all__ = ["MoteurExecution"]
