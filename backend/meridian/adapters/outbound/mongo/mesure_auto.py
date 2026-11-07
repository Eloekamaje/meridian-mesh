"""Dépôts Mongo de la mesure automatique : observations et checkpoints durables.

Le worker lit une collection dédiée, ``mesure_auto_observations``, où chaque document porte
explicitement son ``tenant_id``, un ``id`` stable et un ``maj_le`` (date d'ingestion) qui sert de
curseur. Il avance ensuite un checkpoint par tenant dans ``mesure_auto_checkpoints``.

Aucun accès Postgres : les Outcomes sont seulement enfilés dans l'outbox ``pont_canonique``.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from meridian.application import pont_canonique as pont

__all__ = [
    "CHECKPOINTS",
    "OBSERVATIONS",
    "DepotCheckpointsMesure",
    "DepotObservationsMesure",
]

OBSERVATIONS = "mesure_auto_observations"
CHECKPOINTS = "mesure_auto_checkpoints"
_MAX_LOT = 1000


def _instant(valeur: Any = None) -> str:
    if valeur is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, datetime):
        horodatage = valeur
        if horodatage.tzinfo is None:
            horodatage = horodatage.replace(tzinfo=timezone.utc)
        return horodatage.astimezone(timezone.utc).isoformat(timespec="seconds")
    texte = str(valeur).strip()
    return texte or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


class DepotObservationsMesure:
    """Lecture incrémentale des observations d'un tenant, ordonnées par ``(maj_le, id)``."""

    def __init__(self, collection):
        if collection is None:
            raise ValueError("collection mesure_auto_observations obligatoire")
        self.collection = collection

    def _filtre(self, tenant: str, maj_le: Any = None, identifiant: Any = None) -> dict[str, Any]:
        tenant_normalise = pont.normaliser_tenant(tenant)
        filtre: dict[str, Any] = {"tenant_id": tenant_normalise}
        curseur = _texte(maj_le)
        dernier_id = _texte(identifiant)
        if curseur and dernier_id:
            filtre["$or"] = [
                {"maj_le": {"$gt": curseur}},
                {"$and": [{"maj_le": curseur}, {"id": {"$gt": dernier_id}}]},
            ]
        elif curseur:
            filtre["maj_le"] = {"$gt": curseur}
        elif dernier_id:
            filtre["id"] = {"$gt": dernier_id}
        else:
            filtre["maj_le"] = {"$exists": True}
            filtre["id"] = {"$exists": True}
        return filtre

    async def lister_apres(self, tenant: str, maj_le: Any = None, identifiant: Any = None,
                           limite: int = 100) -> list[dict[str, Any]]:
        borne = max(1, min(int(limite), _MAX_LOT))
        curseur = self.collection.find(self._filtre(tenant, maj_le, identifiant))
        curseur = curseur.sort([("maj_le", 1), ("id", 1)])
        curseur = curseur.limit(borne)
        documents = await curseur.to_list(borne)
        return [dict(document) for document in documents if isinstance(document, Mapping)]

    async def assurer_index(self) -> list[Any]:
        resultats = []
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), ("maj_le", 1), ("id", 1)],
            name="mesure_auto_observations_curseur",
        ))
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), ("id", 1)],
            name="mesure_auto_observations_tenant_id_unique",
            unique=True,
        ))
        return resultats


class DepotCheckpointsMesure:
    """Un checkpoint par tenant : dernier ``(maj_le, id)`` d'observation traitée."""

    def __init__(self, collection, *, horloge=None):
        if collection is None:
            raise ValueError("collection mesure_auto_checkpoints obligatoire")
        self.collection = collection
        self._horloge = horloge or _instant

    async def lire(self, tenant: str) -> dict[str, Any] | None:
        tenant_normalise = pont.normaliser_tenant(tenant)
        document = await self.collection.find_one({"_id": tenant_normalise})
        if not isinstance(document, Mapping):
            return None
        return {
            "dernier_maj_le": _texte(document.get("dernier_maj_le")),
            "dernier_id": _texte(document.get("dernier_id")),
        }

    async def ecrire(self, tenant: str, maj_le: Any, identifiant: Any) -> dict[str, Any]:
        tenant_normalise = pont.normaliser_tenant(tenant)
        curseur = _texte(maj_le)
        dernier_id = _texte(identifiant)
        if not curseur:
            raise ValueError("maj_le obligatoire pour avancer le checkpoint")
        if not dernier_id:
            raise ValueError("id d'observation obligatoire pour avancer le checkpoint")
        instant = _instant(self._horloge())
        document = {
            "tenant_id": tenant_normalise,
            "dernier_maj_le": curseur,
            "dernier_id": dernier_id,
            "maj_le": instant,
        }
        await self.collection.update_one(
            {"_id": tenant_normalise}, {"$set": document}, upsert=True)
        return document
