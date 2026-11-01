"""Compatibilité : la passerelle d'outils vit dans :mod:`meridian.application.execution.tool_gateway`."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from jumeau import http_adapter as _http
from jumeau.http_adapter import (
    HTTPRefuse,
    STATUT_TIMEOUT,
    STATUT_TRANSPORT,
    creer_adaptateur_http,
)
from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application.execution import tool_gateway as _module
from meridian.application.execution.tool_gateway import (
    ECRITURE,
    ENV_ALLOWLIST,
    LECTURE,
    OutilHTTP,
    allowlist_depuis_env,
)


class ToolGateway(_module.ToolGateway):
    def __init__(
        self,
        connect: Callable[[], Any],
        *,
        allowlist: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Sequence[str]]]]] | None = None,
        outils: Mapping[str, OutilHTTP],
        transport: Callable[..., Any] | None = None,
        timeout_s: float = 5.0,
        depot: Any = None,
        http: Any = None,
    ):
        super().__init__(
            connect,
            allowlist=allowlist,
            outils=outils,
            transport=transport,
            timeout_s=timeout_s,
            depot=depot or _depot,
            http=http or _http,
        )


__all__ = [
    "ECRITURE", "LECTURE", "ENV_ALLOWLIST", "allowlist_depuis_env", "OutilHTTP",
    "ToolGateway", "HTTPRefuse", "STATUT_TIMEOUT", "STATUT_TRANSPORT",
    "creer_adaptateur_http",
]
