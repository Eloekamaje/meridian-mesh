"""Double écriture ou écriture Postgres du Travail.

Par défaut, Mongo reste la référence et Postgres est tenu à jour. Avec
`JUMEAU_TRAVAIL_WRITE=postgres`, `db.cases` est remplacé par la collection Postgres :
Mongo n'est plus écrit pour les cas.

`TravailCollection` enveloppe la collection Motor `cases`. Toutes les lectures sont
déléguées telles quelles à Mongo ; les écritures y passent d'abord, puis le ou les
documents résultants sont upsertés dans le read model Postgres (`travail`). Une
suppression retire du read model les identifiants effectivement supprimés.

Le miroir est volontairement tolérant : si Postgres échoue après une écriture Mongo
réussie, l'erreur est journalisée et l'écriture Mongo reste acquise. Le worker de
rattrapage peut alors reprendre la synchronisation depuis `maj_le`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from types import SimpleNamespace
from typing import Any

import psycopg

from meridian.adapters.outbound.postgres.depot import appliquer_schema
from meridian.adapters.outbound.postgres.travail_collection import PostgresTravailCollection
from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
from meridian.application import tenant_context

logger = logging.getLogger("meridian")

FLAG_ENV = "JUMEAU_TRAVAIL_DUAL_WRITE"
WRITE_ENV = "JUMEAU_TRAVAIL_WRITE"
DSN_ENV = "JUMEAU_PG_DSN"
TENANT_ENV = "JUMEAU_TRAVAIL_TENANT"
DEFAUT_TENANT = "local"
VALEURS_ACTIVES = {"1", "true", "yes", "on"}


def double_ecriture_active() -> bool:
    return str(os.environ.get(FLAG_ENV) or "").strip().lower() in VALEURS_ACTIVES


def ecriture_postgres() -> bool:
    return str(os.environ.get(WRITE_ENV) or "").strip().lower() == "postgres"


def installer(db, dsn: str | None = None, tenant: str | None = None):
    """Enveloppe `db.cases` quand le drapeau est actif et qu'un DSN Postgres existe.

    Le schéma `travail` est appliqué avant le premier miroir. Sans DSN, rien n'est
    câblé : les écritures restent purement Mongo. Idempotent si déjà installé.
    """
    dsn = dsn or os.environ.get(DSN_ENV)
    defaut = tenant or os.environ.get(TENANT_ENV) or DEFAUT_TENANT
    actuel = db.cases
    if ecriture_postgres():
        if not dsn:
            logger.warning("%s=postgres mais %s absent : écritures Travail Mongo seules",
                           WRITE_ENV, DSN_ENV)
            return None
        if isinstance(actuel, PostgresTravailCollection):
            return actuel
        with psycopg.connect(dsn, autocommit=True) as conn:
            appliquer_schema(conn)
        collection = PostgresTravailCollection(dsn=dsn, tenant_defaut=defaut)
        db.cases = collection
        logger.info("Écriture Travail Postgres active (tenant par requête, défaut %s)",
                    defaut)
        return collection
    if not double_ecriture_active():
        return None
    if not dsn:
        logger.warning("%s actif mais %s absent : écritures Travail Mongo seules",
                       FLAG_ENV, DSN_ENV)
        return None
    if isinstance(actuel, TravailCollection):
        return actuel
    with psycopg.connect(dsn, autocommit=True) as conn:
        appliquer_schema(conn)
    cible = TravailPostgres(dsn=dsn, tenant_id=defaut)
    proxy = TravailCollection(actuel, cible, dsn=dsn, tenant_defaut=defaut)
    db.cases = proxy
    logger.info("Double écriture Travail active (tenant Postgres par requête, défaut %s)",
                proxy.tenant_defaut)
    return proxy


class TravailCollection:
    """Proxy de la collection `cases` : lectures Mongo, écritures Mongo puis miroir Postgres."""

    def __init__(self, collection, cible=None, *, dsn: str | None = None,
                 tenant_defaut: str = DEFAUT_TENANT):
        self._collection = collection
        self._cible = cible
        self.dsn = dsn
        self.tenant_defaut = tenant_defaut

    def _cible_courante(self):
        tenant = tenant_context.courant_explicite()
        if self._cible is not None and (tenant is None or tenant == getattr(self._cible, "tenant_id", tenant)):
            return self._cible
        return TravailPostgres(dsn=self.dsn, tenant_id=tenant or self.tenant_defaut)

    def __getattr__(self, nom: str):
        return getattr(self._collection, nom)

    def find(self, *args, **kwargs):
        return self._collection.find(*args, **kwargs)

    async def find_one(self, *args, **kwargs):
        return await self._collection.find_one(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        return self._collection.aggregate(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return await self._collection.count_documents(*args, **kwargs)

    async def _identifiants(self, filtre: dict[str, Any], limite: int | None = None,
                            tri=None) -> list[Any]:
        curseur = self._collection.find(filtre, {"_id": 1})
        if tri is not None:
            curseur = curseur.sort(tri)
        if limite is not None:
            curseur = curseur.limit(limite)
        return [document["_id"] for document in await curseur.to_list(None)]

    async def _cibles(self, filtre: dict[str, Any], limite: int | None = None,
                      tri=None) -> list[tuple[Any, str]]:
        curseur = self._collection.find(filtre, {"_id": 1, "id": 1})
        if tri is not None:
            curseur = curseur.sort(tri)
        if limite is not None:
            curseur = curseur.limit(limite)
        documents = await curseur.to_list(None)
        return [(d["_id"], str(d.get("id") or d["_id"])) for d in documents]

    async def _reessayer(self, operation, *args):
        """Réessaie un miroir ; le worker de synchronisation reste le filet final."""
        derniere = None
        for tentative in range(3):
            try:
                return await operation(*args)
            except Exception as exc:  # noqa: BLE001 - on retente puis on alerte
                derniere = exc
                if tentative < 2:
                    await asyncio.sleep(0.05 * (2 ** tentative))
        raise derniere

    async def _miroiter(self, identifiants: list[Any]) -> None:
        identifiants = list(dict.fromkeys(identifiants))
        if not identifiants:
            return
        cible = self._cible_courante()
        async def ecrire():
            curseur = self._collection.find({"_id": {"$in": identifiants}})
            for document in await curseur.to_list(None):
                await cible.upsert(document)
        try:
            await self._reessayer(ecrire)
        except Exception:  # noqa: BLE001 - Mongo reste la référence, le worker rattrapera
            logger.exception("Miroir Postgres du Travail impossible après une écriture Mongo")

    async def _supprimer(self, cibles: list[tuple[Any, str]], supprimes: int) -> None:
        if not supprimes or not cibles:
            return
        cles = [cle for _, cle in cibles]
        cible = self._cible_courante()
        try:
            if supprimes < len(cibles):
                identifiants = [identifiant for identifiant, _ in cibles]
                survivants = await self._collection.find(
                    {"_id": {"$in": identifiants}}, {"_id": 1}).to_list(None)
                restants = {document["_id"] for document in survivants}
                cles = [cle for identifiant, cle in cibles if identifiant not in restants]
            if cles:
                await self._reessayer(cible.supprimer_plusieurs, cles)
        except Exception:  # noqa: BLE001 - même politique que l'upsert : ne pas casser Mongo
            logger.exception("Suppression Postgres du Travail impossible après une suppression Mongo")

    async def insert_one(self, document, *args, **kwargs):
        if isinstance(document, dict):
            document.setdefault("tenant_id", tenant_context.courant(self.tenant_defaut))
        resultat = await self._collection.insert_one(document, *args, **kwargs)
        identifiant = getattr(resultat, "inserted_id", None)
        if identifiant is None:
            identifiant = document.get("_id")
        if identifiant is not None:
            await self._miroiter([identifiant])
        return resultat

    async def update_one(self, filtre, modification, *args, **kwargs):
        identifiants = await self._identifiants(filtre, 1)
        resultat = await self._collection.update_one(filtre, modification, *args, **kwargs)
        if getattr(resultat, "upserted_id", None) is not None:
            identifiants.append(resultat.upserted_id)
        await self._miroiter(identifiants)
        return resultat

    async def update_many(self, filtre, modification, *args, **kwargs):
        identifiants = await self._identifiants(filtre)
        resultat = await self._collection.update_many(filtre, modification, *args, **kwargs)
        if getattr(resultat, "upserted_id", None) is not None:
            identifiants.append(resultat.upserted_id)
        await self._miroiter(identifiants)
        return resultat

    async def find_one_and_update(self, filtre, modification, *args, **kwargs):
        tri = args[1] if len(args) >= 2 else kwargs.get("sort")
        upsert = bool(args[2]) if len(args) >= 3 else bool(kwargs.get("upsert"))
        identifiants = await self._identifiants(filtre, 1, tri=tri)
        resultat = await self._collection.find_one_and_update(
            filtre, modification, *args, **kwargs)
        if isinstance(resultat, dict) and resultat.get("_id") is not None:
            identifiants.append(resultat["_id"])
        if not identifiants and upsert:
            insere = await self._collection.find_one(filtre, {"_id": 1})
            if insere is not None:
                identifiants.append(insere["_id"])
        await self._miroiter(identifiants)
        return resultat

    async def delete_one(self, filtre, *args, **kwargs):
        cibles = await self._cibles(filtre, 1)
        resultat = await self._collection.delete_one(filtre, *args, **kwargs)
        await self._supprimer(cibles, int(getattr(resultat, "deleted_count", 0) or 0))
        return resultat

    async def delete_many(self, filtre, *args, **kwargs):
        cibles = await self._cibles(filtre)
        resultat = await self._collection.delete_many(filtre, *args, **kwargs)
        await self._supprimer(cibles, int(getattr(resultat, "deleted_count", 0) or 0))
        return resultat

    async def replace_one(self, filtre, remplacement, *args, **kwargs):
        if isinstance(remplacement, dict):
            remplacement.setdefault("tenant_id", tenant_context.courant(self.tenant_defaut))
        identifiants = await self._identifiants(filtre, 1)
        resultat = await self._collection.replace_one(filtre, remplacement, *args, **kwargs)
        if getattr(resultat, "upserted_id", None) is not None:
            identifiants.append(resultat.upserted_id)
        await self._miroiter(identifiants)
        return resultat

    async def bulk_write(self, operations, *args, **kwargs):
        """Miroir des opérations Mongo utilisées par les cas ; aucune n'est utilisée aujourd'hui."""
        compteurs = {"inserted": 0, "matched": 0, "modified": 0, "deleted": 0, "upserted": 0}
        for operation in operations:
            nom = type(operation).__name__
            filtre = getattr(operation, "_filter", None)
            document = getattr(operation, "_doc", getattr(operation, "document", None))
            upsert = bool(getattr(operation, "_upsert", False))
            if nom == "InsertOne":
                resultat = await self.insert_one(document)
                compteurs["inserted"] += int(getattr(resultat, "acknowledged", 1))
            elif nom == "UpdateOne":
                resultat = await self.update_one(filtre, document, upsert=upsert)
                compteurs["matched"] += int(getattr(resultat, "matched_count", 0) or 0)
                compteurs["modified"] += int(getattr(resultat, "modified_count", 0) or 0)
                compteurs["upserted"] += int(getattr(resultat, "upserted_id", None) is not None)
            elif nom == "UpdateMany":
                resultat = await self.update_many(filtre, document, upsert=upsert)
                compteurs["matched"] += int(getattr(resultat, "matched_count", 0) or 0)
                compteurs["modified"] += int(getattr(resultat, "modified_count", 0) or 0)
                compteurs["upserted"] += int(getattr(resultat, "upserted_id", None) is not None)
            elif nom == "ReplaceOne":
                resultat = await self.replace_one(filtre, document, upsert=upsert)
                compteurs["matched"] += int(getattr(resultat, "matched_count", 0) or 0)
                compteurs["modified"] += int(getattr(resultat, "modified_count", 0) or 0)
                compteurs["upserted"] += int(getattr(resultat, "upserted_id", None) is not None)
            elif nom == "DeleteOne":
                resultat = await self.delete_one(filtre)
                compteurs["deleted"] += int(getattr(resultat, "deleted_count", 0) or 0)
            elif nom == "DeleteMany":
                resultat = await self.delete_many(filtre)
                compteurs["deleted"] += int(getattr(resultat, "deleted_count", 0) or 0)
            else:
                raise NotImplementedError(f"opération bulk non mirée : {nom}")
        return SimpleNamespace(
            inserted_count=compteurs["inserted"], matched_count=compteurs["matched"],
            modified_count=compteurs["modified"], deleted_count=compteurs["deleted"],
            upserted_count=compteurs["upserted"], bulk_api_result={})
