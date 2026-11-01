"""Stockage GridFS/Mongo, historique et valeur par défaut."""
from __future__ import annotations

from typing import Any, Callable

from bson import ObjectId
from bson.errors import InvalidId
from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

BUCKET = "pieces_fichiers"


def _oid(valeur):
    if isinstance(valeur, ObjectId):
        return valeur
    try:
        return ObjectId(str(valeur))
    except (InvalidId, TypeError):
        return valeur


class GridFSStockage:
    nom = "mongo"

    def __init__(self, db, bucket_name: str = BUCKET,
                 bucket_factory: Callable[[Any], Any] | None = None):
        self.db = db
        self.bucket_name = bucket_name
        self._bucket_factory = bucket_factory

    def _bucket(self):
        if self._bucket_factory is not None:
            return self._bucket_factory(self.db)
        return AsyncIOMotorGridFSBucket(self.db, bucket_name=self.bucket_name)

    async def ecrire(self, cle: str, data: bytes, metadata: dict[str, Any]) -> str:
        flux = self._bucket().open_upload_stream(cle, metadata=metadata)
        try:
            await flux.write(data)
            await flux.close()
        except Exception:
            try:
                await flux.abort()
            except Exception:
                pass
            raise
        return str(flux._id)

    async def lire(self, identifiant: str) -> bytes:
        try:
            flux = await self._bucket().open_download_stream(_oid(identifiant))
            try:
                return await flux.read()
            finally:
                flux.close()
        except NoFile as exc:
            raise FileNotFoundError("contenu de la pièce introuvable") from exc

    async def supprimer(self, identifiant: str) -> None:
        try:
            await self._bucket().delete(_oid(identifiant))
        except (NoFile, FileNotFoundError):
            pass

    async def deplacer(self, identifiants: list[str], case_id: str) -> None:
        if not identifiants:
            return
        await self.db[f"{self.bucket_name}.files"].update_many(
            {"metadata.piece_id": {"$in": identifiants}},
            {"$set": {"metadata.case_id": case_id}},
        )

    async def vider(self) -> None:
        for collection in (f"{self.bucket_name}.files", f"{self.bucket_name}.chunks"):
            try:
                await self.db.drop_collection(collection)
            except AttributeError:
                return
