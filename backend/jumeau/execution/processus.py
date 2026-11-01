"""Compatibilité : le process manager vit dans :mod:`meridian.application.execution.processus`."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from meridian.adapters.outbound.postgres import execution_depot as _depot
from meridian.application.execution import processus as _module


class ProcessManager(_module.ProcessManager):
    def __init__(
        self,
        connect: Callable[[], Any],
        run: Mapping[str, Any],
        *,
        verifier_annulation: Callable[[], bool] | None = None,
        depot: Any = None,
    ):
        super().__init__(
            connect,
            run,
            verifier_annulation=verifier_annulation,
            depot=depot or _depot,
        )


__all__ = ["ProcessManager"]
