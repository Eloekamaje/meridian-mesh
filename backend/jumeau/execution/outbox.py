"""Compatibilité : l'outbox vit dans :mod:`meridian.application.outbox`."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application import outbox as _module
from meridian.application.outbox import (
    MODE_DIRECT,
    MODE_ENV,
    MODE_OUTBOX,
    MODES,
    mode_projection,
)


class DispatcherOutbox(_module.DispatcherOutbox):
    def __init__(
        self,
        connect: Callable[[], Any],
        publieurs: Mapping[str, Callable[[Mapping[str, Any]], Any]] | None = None,
        *,
        depot: Any = None,
    ):
        super().__init__(connect, publieurs, depot=depot or _depot)


def planifier_projection(
    conn,
    tenant_id: str,
    twins,
    relations,
    run_id: str = "graph",
    *,
    depot: Any = None,
) -> int:
    return _module.planifier_projection(
        conn, tenant_id, twins, relations, run_id, depot=depot or _depot)


__all__ = [
    "MODE_DIRECT", "MODE_ENV", "MODE_OUTBOX", "MODES", "mode_projection",
    "DispatcherOutbox", "planifier_projection",
]
