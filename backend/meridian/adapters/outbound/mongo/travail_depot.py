"""Adapter Mongo du port TravailStore : transition avant le store Travail canonique (ADR-0008)."""
from __future__ import annotations

from typing import Any


class TravailDepot:
    def __init__(self, collection):
        self.collection = collection

    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]:
        return await self.collection.find(filtre or {}, {"_id": 0}).to_list(limite)

    async def lire(self, cid: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"id": cid}, {"_id": 0})

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool:
        resultat = await self.collection.update_one({"id": cid}, {"$set": champs})
        return bool(getattr(resultat, "matched_count", 0))
