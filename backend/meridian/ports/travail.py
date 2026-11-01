"""Port du store Travail : le fil Aujourd'hui et l'Atlas ne doivent pas connaître Mongo."""
from __future__ import annotations

from typing import Any, Protocol


class TravailStore(Protocol):
    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]: ...

    async def lister_recents(self, limite: int | None = 500) -> list[dict[str, Any]]: ...

    async def lire(self, cid: str) -> dict[str, Any] | None: ...

    async def compter(self) -> int: ...

    async def upsert(self, travail: dict[str, Any]) -> bool: ...

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool: ...


class TravailSource(Protocol):
    """Source de synchronisation : les cas Mongo, lus par lots stables."""

    async def lister_par_id(self, apres_id: str | None, limite: int) -> list[dict[str, Any]]: ...

    async def lister_apres(self, maj_le: str | None, apres_id: str | None,
                           limite: int) -> list[dict[str, Any]]: ...
