"""Câblage par défaut du runtime d'exécution, réservé aux adapters et aux tests historiques.

Le cœur (`application/execution`) ne dépend d'aucun adapter. Ce module fournit les
constructeurs pratiques qui branchent Postgres, le service d'analyse et le transport HTTP.
"""
from __future__ import annotations

import json
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


def outils_depuis_env(valeur: str | None = None) -> dict[str, OutilHTTP]:
    """Déclare les outils HTTP depuis `EXECUTION_TOOLS` (JSON) — aucune URL hardcodée.

    Forme : ``{"outil": {"base_url": "https://...", "operations": {"lire": ["GET", "/objets/{cible}"]}}}``.
    Sans variable, aucun outil n'est exposé : le ToolGateway refuse alors tout appel.
    """
    brut = os.environ.get("EXECUTION_TOOLS") if valeur is None else valeur
    if brut is None or not str(brut).strip():
        return {}
    try:
        donnees = json.loads(brut)
    except json.JSONDecodeError as exc:
        raise ValueError("EXECUTION_TOOLS n'est pas un JSON valide") from exc
    if not isinstance(donnees, Mapping):
        raise ValueError("EXECUTION_TOOLS doit être un objet JSON")
    outils: dict[str, OutilHTTP] = {}
    for nom, definition in donnees.items():
        if not isinstance(nom, str) or not nom.strip() or not isinstance(definition, Mapping):
            raise ValueError("EXECUTION_TOOLS : outil et définition attendus")
        base_url = definition.get("base_url")
        operations = definition.get("operations")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError(f"EXECUTION_TOOLS.{nom}.base_url doit être HTTP(S)")
        if not isinstance(operations, Mapping) or not operations:
            raise ValueError(f"EXECUTION_TOOLS.{nom}.operations doit être un objet non vide")
        normalisees = {}
        for operation, valeur in operations.items():
            if (not isinstance(operation, str) or not isinstance(valeur, Sequence)
                    or len(valeur) != 2):
                raise ValueError(f"EXECUTION_TOOLS.{nom}.{operation} : [méthode, chemin] attendu")
            methode, chemin = valeur
            if not isinstance(methode, str) or not isinstance(chemin, str):
                raise ValueError(f"EXECUTION_TOOLS.{nom}.{operation} : chaînes attendues")
            normalisees[operation] = (methode, chemin)
        hosts = definition.get("allowlist_hosts") or ()
        if not isinstance(hosts, Sequence) or isinstance(hosts, str):
            raise ValueError(f"EXECUTION_TOOLS.{nom}.allowlist_hosts doit être une liste")
        try:
            timeout = float(definition.get("timeout_s", 5.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"EXECUTION_TOOLS.{nom}.timeout_s invalide") from exc
        outils[nom] = OutilHTTP(
            base_url=base_url.rstrip("/"),
            operations=normalisees,
            allowlist_hosts=tuple(str(h) for h in hosts),
            timeout_s=timeout,
        )
    return outils


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
    "outils_depuis_env",
]
