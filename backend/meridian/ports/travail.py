"""Port du store Travail : le fil Aujourd'hui et l'Atlas ne doivent pas connaître Mongo."""
from __future__ import annotations

from typing import Any, Protocol


class TravailStore(Protocol):
    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]: ...

    async def lire(self, cid: str) -> dict[str, Any] | None: ...

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool: ...
