"""Adapter Mongo du port TravailStore : transition avant le store Travail canonique (ADR-0008)."""
from __future__ import annotations

from typing import Any

try:  # pymongo est une dépendance de l'application ; le CLI et les tests peuvent s'en passer.
    from bson import ObjectId
    from bson.errors import InvalidId
except ImportError:  # pragma: no cover - dépendance toujours présente en production
    ObjectId = None  # type: ignore[assignment]
    InvalidId = ValueError  # type: ignore[assignment]


def _oid(valeur):
    """Identifiant Mongo comparable ; une chaîne non-ObjectId reste une chaîne (fakes, tests)."""
    if valeur is None or ObjectId is None or isinstance(valeur, ObjectId):
        return valeur
    try:
        return ObjectId(str(valeur))
    except (InvalidId, TypeError):
        return valeur


class TravailDepot:
    def __init__(self, collection):
        self.collection = collection

    async def lister(self, filtre: dict[str, Any] | None = None,
                     limite: int = 200) -> list[dict[str, Any]]:
        return await self.collection.find(filtre or {}, {"_id": 0}).to_list(limite)

    async def lister_recents(self, limite: int | None = 500) -> list[dict[str, Any]]:
        curseur = self.collection.find({}, {"_id": 0}).sort([("maj_le", -1), ("id", -1)])
        if limite:
            curseur = curseur.limit(int(limite))
        return await curseur.to_list(None)

    async def lire(self, cid: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"id": cid}, {"_id": 0})

    async def compter(self) -> int:
        return await self.collection.count_documents({})

    async def upsert(self, travail: dict[str, Any]) -> bool:
        """Écrit un cas Mongo identifié par `id` ; chemin de compatibilité, jamais utilisé par la lecture."""
        document = {k: v for k, v in travail.items() if k != "_id"}
        resultat = await self.collection.replace_one({"id": document["id"]}, document, upsert=True)
        return bool(getattr(resultat, "upserted_id", None) or getattr(resultat, "modified_count", 0))

    async def mettre_a_jour(self, cid: str, champs: dict[str, Any]) -> bool:
        resultat = await self.collection.update_one({"id": cid}, {"$set": champs})
        return bool(getattr(resultat, "matched_count", 0))

    # --- Source de synchronisation (Mongo -> Postgres) -------------------------------------------

    async def lister_par_id(self, apres_id: str | None, limite: int) -> list[dict[str, Any]]:
        filtre = {"_id": {"$gt": _oid(apres_id)}} if apres_id is not None else {}
        curseur = (self.collection.find(filtre)
                   .sort("_id", 1).limit(int(limite)))
        return await curseur.to_list(int(limite))

    async def lister_apres(self, maj_le: str | None, apres_id: str | None,
                           limite: int) -> list[dict[str, Any]]:
        if maj_le is None:
            filtre = {}
        elif apres_id is None:
            filtre = {"maj_le": {"$gt": maj_le}}
        else:
            filtre = {"$or": [
                {"maj_le": {"$gt": maj_le}},
                {"maj_le": maj_le, "_id": {"$gt": _oid(apres_id)}},
            ]}
        curseur = (self.collection.find(filtre)
                   .sort([("maj_le", 1), ("_id", 1)]).limit(int(limite)))
        return await curseur.to_list(int(limite))
