"""Port de persistance des commandes de jumeau."""
from __future__ import annotations

from typing import Any, Protocol


class CommandesStore(Protocol):
    async def lire(self, cid: str) -> dict[str, Any] | None: ...

    async def lister(self, *, etat: str = "brouillon", limite: int = 50) -> list[dict[str, Any]]: ...

    async def creer(self, doc: dict[str, Any]) -> None: ...

    async def mettre_a_jour(
        self, cid: str, patch: dict[str, Any], *, etat: str = "brouillon"
    ) -> bool: ...

    async def connexions(self) -> list[dict[str, Any]]: ...
