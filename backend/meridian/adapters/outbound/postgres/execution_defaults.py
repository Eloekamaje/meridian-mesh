"""Câblage par défaut du runtime d'exécution, réservé aux adapters et aux tests historiques.

Le cœur (`application/execution`) ne dépend d'aucun adapter. Ce module fournit les
constructeurs pratiques qui branchent Postgres, le service d'analyse et le transport HTTP.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping, Sequence

import psycopg

from meridian.adapters.outbound.analyse_runtime import RuntimeAnalysePostgres
from meridian.adapters.outbound.connectors import http_adapter as _http
from meridian.adapters.outbound.connectors.http_adapter import (
    HTTPRefuse,
    STATUT_TIMEOUT,
    STATUT_TRANSPORT,
    creer_adaptateur_http,
)
from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application import analyse_service, outbox as _outbox
from meridian.application.execution import executeurs as _executeurs
from meridian.application.execution import moteur as _moteur
from meridian.application.execution import processus as _processus
from meridian.application.execution import tool_gateway as _tool_gateway
from meridian.application.outbox import (
    MODE_DIRECT,
    MODE_ENV,
    MODE_OUTBOX,
    MODES,
    mode_projection,
)
from meridian.application.execution.tool_gateway import (
    ECRITURE,
    ENV_ALLOWLIST,
    LECTURE,
    OutilHTTP,
    allowlist_depuis_env,
)


def _connecter():
    return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)


class MoteurExecution(_moteur.MoteurExecution):
    def __init__(self, connect: Callable[[], Any] | None = None,
                 executeur: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                 *, worker_id: str | None = None, bail_secondes: int = 30,
                 depot: Any = None):
        super().__init__(connect or _connecter, executeur, worker_id=worker_id,
                         bail_secondes=bail_secondes, depot=depot or _depot)


class ProcessManager(_processus.ProcessManager):
    def __init__(self, connect: Callable[[], Any], run: Mapping[str, Any],
                 *, verifier_annulation: Callable[[], bool] | None = None,
                 depot: Any = None):
        super().__init__(connect, run, verifier_annulation=verifier_annulation,
                         depot=depot or _depot)


class ToolGateway(_tool_gateway.ToolGateway):
    def __init__(self, connect: Callable[[], Any],
                 *, allowlist: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Sequence[str]]]]] | None = None,
                 outils: Mapping[str, OutilHTTP],
                 transport: Callable[..., Any] | None = None,
                 timeout_s: float = 5.0, depot: Any = None, http: Any = None):
        super().__init__(connect, allowlist=allowlist, outils=outils,
                         transport=transport, timeout_s=timeout_s,
                         depot=depot or _depot, http=http or _http)


class DispatcherOutbox(_outbox.DispatcherOutbox):
    def __init__(self, connect: Callable[[], Any],
                 publieurs: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
                 *, depot: Any = None):
        super().__init__(connect, publieurs, depot=depot or _depot)


def planifier_projection(conn, tenant_id: str, twins, relations, run_id: str = "graph",
                         *, depot: Any = None) -> int:
    return _outbox.planifier_projection(conn, tenant_id, twins, relations, run_id,
                                        depot=depot or _depot)


EXECUTEURS: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = _executeurs.creer_executeurs(
    analyse_service=analyse_service,
    runtime=RuntimeAnalysePostgres(),
    connect=_connecter,
    depot=_depot,
)
cognitif_analyser = EXECUTEURS["cognitif.analyser"]


def executeur_par_type(run: Mapping[str, Any]) -> Mapping[str, Any]:
    return _executeurs.executeur_par_type(run, EXECUTEURS)


__all__ = [
    "MODE_DIRECT", "MODE_ENV", "MODE_OUTBOX", "MODES", "mode_projection",
    "DispatcherOutbox", "planifier_projection", "EXECUTEURS", "cognitif_analyser",
    "executeur_par_type", "MoteurExecution", "ProcessManager", "ToolGateway",
    "OutilHTTP", "HTTPRefuse", "STATUT_TIMEOUT", "STATUT_TRANSPORT",
    "creer_adaptateur_http", "ECRITURE", "LECTURE", "ENV_ALLOWLIST", "allowlist_depuis_env",
]
