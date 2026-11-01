"""Adapter Mongo du port CommandesStore : aucune règle métier."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

NO_ID = {"_id": 0}

Connexions = Callable[[], Awaitable[list[dict[str, Any]]]]


class CommandesDepot:
    def __init__(self, collection, connexions: Connexions | None = None):
        self.collection = collection
        self._connexions = connexions

    async def lire(self, cid: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"id": cid}, NO_ID)

    async def lister(self, *, etat: str = "brouillon", limite: int = 50) -> list[dict[str, Any]]:
        return await self.collection.find({"etat": etat}, NO_ID).to_list(limite)

    async def creer(self, doc: dict[str, Any]) -> None:
        await self.collection.insert_one(dict(doc))

    async def mettre_a_jour(
        self, cid: str, patch: dict[str, Any], *, etat: str = "brouillon"
    ) -> bool:
        res = await self.collection.update_one({"id": cid, "etat": etat}, {"$set": patch})
        return res.matched_count > 0

    async def connexions(self) -> list[dict[str, Any]]:
        if self._connexions is None:
            return []
        return await self._connexions()
