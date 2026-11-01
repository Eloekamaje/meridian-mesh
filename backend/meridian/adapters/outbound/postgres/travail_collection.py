"""Collection `cases` adossée à Postgres, compatible avec le sous-ensemble Mongo utilisé.

Le store Travail peut ainsi fonctionner sans Mongo pour les cas : les filtres, projections,
tris et opérateurs de mise à jour réellement utilisés par les routes sont interprétés en
Python sur les documents JSONB. Les pièces jointes (`db.pieces`) restent dans Mongo.

Les écritures sont sérialisées par tenant avec un advisory lock Postgres (et un verrou
asyncio local). Le store reste volontairement petit (work store), et le read model
`travail` est la source Postgres.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
from meridian.application import tenant_context

MANQUANT = object()


def _valeur(document: dict[str, Any], chemin: str):
    valeur = document
    for morceau in chemin.split("."):
        if isinstance(valeur, dict):
            valeur = valeur.get(morceau, MANQUANT)
        elif isinstance(valeur, list):
            try:
                valeur = valeur[int(morceau)]
            except (ValueError, IndexError):
                return MANQUANT
        else:
            return MANQUANT
        if valeur is MANQUANT:
            return MANQUANT
    return valeur


def _correspond(document: dict[str, Any], filtre: dict[str, Any] | None) -> bool:
    for cle, attendu in (filtre or {}).items():
        if cle == "$or":
            if not any(_correspond(document, option) for option in attendu):
                return False
            continue
        if cle == "$and":
            if not all(_correspond(document, option) for option in attendu):
                return False
            continue
        valeur = _valeur(document, cle)
        if isinstance(attendu, dict) and any(str(k).startswith("$") for k in attendu):
            if "$exists" in attendu and (valeur is not MANQUANT) != bool(attendu["$exists"]):
                return False
            if "$ne" in attendu and valeur == attendu["$ne"]:
                return False
            if "$in" in attendu and valeur not in attendu["$in"]:
                return False
            if "$nin" in attendu and valeur in attendu["$nin"]:
                return False
            if "$gt" in attendu and not (valeur is not MANQUANT and valeur > attendu["$gt"]):
                return False
            if "$gte" in attendu and not (valeur is not MANQUANT and valeur >= attendu["$gte"]):
                return False
            if "$lt" in attendu and not (valeur is not MANQUANT and valeur < attendu["$lt"]):
                return False
            if "$lte" in attendu and not (valeur is not MANQUANT and valeur <= attendu["$lte"]):
                return False
            if "$regex" in attendu:
                options = attendu.get("$options", "")
                if valeur is MANQUANT or not re.search(attendu["$regex"], str(valeur),
                                                       re.I if "i" in options else 0):
                    return False
        elif valeur is MANQUANT or valeur != attendu:
            return False
    return True


def _poser(document: dict[str, Any], chemin: str, valeur: Any) -> None:
    morceaux = chemin.split(".")
    courant: Any = document
    for morceau in morceaux[:-1]:
        suivant = courant.get(morceau) if isinstance(courant, dict) else None
        if isinstance(courant, dict):
            if not isinstance(suivant, (dict, list)):
                suivant = {}
                courant[morceau] = suivant
        elif isinstance(courant, list):
            indice = int(morceau)
            while len(courant) <= indice:
                courant.append({})
            if not isinstance(courant[indice], (dict, list)):
                courant[indice] = {}
            suivant = courant[indice]
        else:
            raise TypeError(f"chemin non posable : {chemin}")
        courant = suivant
    if isinstance(courant, dict):
        courant[morceaux[-1]] = valeur
    elif isinstance(courant, list):
        indice = int(morceaux[-1])
        while len(courant) <= indice:
            courant.append(None)
        courant[indice] = valeur
    else:
        raise TypeError(f"chemin non posable : {chemin}")


def _retirer(document: dict[str, Any], chemin: str) -> None:
    morceaux = chemin.split(".")
    courant: Any = document
    for morceau in morceaux[:-1]:
        if isinstance(courant, dict):
            courant = courant.get(morceau)
        elif isinstance(courant, list):
            try:
                courant = courant[int(morceau)]
            except (ValueError, IndexError):
                return
        else:
            return
    if isinstance(courant, dict):
        courant.pop(morceaux[-1], None)
    elif isinstance(courant, list):
        try:
            del courant[int(morceaux[-1])]
        except (ValueError, IndexError):
            pass


def _appliquer(document: dict[str, Any], modification: dict[str, Any]) -> None:
    for operateur, champs in modification.items():
        if operateur == "$set":
            for cle, valeur in champs.items():
                _poser(document, cle, valeur)
        elif operateur == "$unset":
            for cle in champs:
                _retirer(document, cle)
        elif operateur == "$inc":
            for cle, valeur in champs.items():
                actuelle = _valeur(document, cle)
                _poser(document, cle, (0 if actuelle is MANQUANT else actuelle) + valeur)
        elif operateur == "$max":
            for cle, valeur in champs.items():
                actuelle = _valeur(document, cle)
                if actuelle is MANQUANT or valeur > actuelle:
                    _poser(document, cle, valeur)
        elif operateur == "$push":
            for cle, valeur in champs.items():
                actuelle = _valeur(document, cle)
                liste = actuelle if isinstance(actuelle, list) else []
                if isinstance(valeur, dict) and "$each" in valeur:
                    liste.extend(valeur["$each"])
                else:
                    liste.append(valeur)
                _poser(document, cle, liste)
        elif operateur == "$addToSet":
            for cle, valeur in champs.items():
                actuelle = _valeur(document, cle)
                liste = actuelle if isinstance(actuelle, list) else []
                ajouts = valeur.get("$each", []) if isinstance(valeur, dict) else [valeur]
                for ajout in ajouts:
                    if ajout not in liste:
                        liste.append(ajout)
                _poser(document, cle, liste)
        elif operateur == "$pull":
            for cle, valeur in champs.items():
                actuelle = _valeur(document, cle)
                if isinstance(actuelle, list):
                    _poser(document, cle, [element for element in actuelle if element != valeur])
        else:
            raise NotImplementedError(f"opérateur de mise à jour non supporté : {operateur}")


def _projeter(document: dict[str, Any], projection: dict[str, Any] | None):
    if not projection:
        return dict(document)
    inclusions = [cle for cle, actif in projection.items() if actif and cle != "_id"]
    if not inclusions and projection.get("_id") and set(projection) == {"_id"}:
        return {"_id": document["_id"]} if "_id" in document else {}
    if inclusions:
        resultat = {cle: document[cle] for cle in inclusions if cle in document}
        if projection.get("_id", 1) and "_id" in document:
            resultat["_id"] = document["_id"]
        return resultat
    resultat = dict(document)
    for cle, actif in projection.items():
        if not actif:
            resultat.pop(cle, None)
    return resultat


def _trier(documents: list[dict[str, Any]], tri) -> list[dict[str, Any]]:
    if not tri:
        return documents
    if isinstance(tri, str):
        tri = [(tri, 1)]
    elif isinstance(tri, tuple):
        tri = [tri]
    for champ, sens in reversed(list(tri)):
        def cle(document):
            valeur = _valeur(document, champ)
            return (valeur is MANQUANT, valeur if valeur is not MANQUANT else None)
        try:
            documents.sort(key=cle, reverse=sens < 0)
        except TypeError:
            documents.sort(key=lambda d: str(cle(d)[1]), reverse=sens < 0)
    return documents


def _base_upsert(filtre: dict[str, Any]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for cle, valeur in (filtre or {}).items():
        if cle in {"$or", "$and"} or (isinstance(valeur, dict) and
                                       any(str(k).startswith("$") for k in valeur)):
            continue
        _poser(document, cle, valeur)
    return document


class Curseur:
    def __init__(self, collection: "PostgresTravailCollection", filtre, projection):
        self.collection = collection
        self.filtre = filtre or {}
        self.projection = projection
        self.tri = None
        self.limite = None
        self.saut = 0

    def sort(self, tri, direction=None):
        self.tri = [(tri, direction or 1)] if isinstance(tri, str) else tri
        return self

    def limit(self, nombre):
        self.limite = int(nombre)
        return self

    def skip(self, nombre):
        self.saut = int(nombre)
        return self

    async def _documents(self):
        documents = await self.collection._documents(self.filtre)
        documents = _trier(documents, self.tri)
        documents = documents[self.saut:]
        if self.limite is not None:
            documents = documents[:self.limite]
        return [_projeter(document, self.projection) for document in documents]

    async def to_list(self, nombre=None):
        documents = await self._documents()
        return documents if nombre is None else documents[:int(nombre)]

    def __aiter__(self):
        self._iter = None
        return self

    async def __anext__(self):
        if self._iter is None:
            self._iter = iter(await self._documents())
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class PostgresTravailCollection:
    """Collection `cases` minimale, compatible avec les appels Mongo utilisés par l'API."""

    def __init__(self, dsn: str | None = None, tenant_defaut: str = "local", depot=None):
        self.dsn = dsn
        self.tenant_defaut = tenant_defaut
        self._depot = depot
        self._verrou = asyncio.Lock()

    def _depot_courant(self):
        tenant = tenant_context.courant_explicite()
        if self._depot is not None and (tenant is None or tenant == getattr(self._depot, "tenant_id", tenant)):
            return self._depot
        return TravailPostgres(dsn=self.dsn, tenant_id=tenant or self.tenant_defaut)

    def _tenant(self):
        return tenant_context.courant(self.tenant_defaut)

    @contextmanager
    def _verrou_postgres(self):
        depot = self._depot_courant()
        verrou = getattr(depot, "verrou", None)
        if verrou is None:
            yield depot
            return
        with verrou() as verrouille:
            yield verrouille

    async def _documents(self, filtre=None, depot=None):
        depot = depot or self._depot_courant()
        documents = await depot.lister_recents(None)
        resultat = []
        for document in documents:
            propre = dict(document)
            propre.setdefault("_id", str(propre.get("id") or ""))
            if _correspond(propre, filtre):
                resultat.append(propre)
        return resultat

    def find(self, filtre=None, projection=None, *args, **kwargs):
        return Curseur(self, filtre, projection)

    async def find_one(self, filtre=None, projection=None, *args, **kwargs):
        if kwargs.get("sort"):
            documents = await Curseur(self, filtre, projection).sort(
                kwargs["sort"]).limit(1)._documents()
        else:
            documents = await self._documents(filtre)
            documents = [_projeter(document, projection) for document in documents[:1]]
        return documents[0] if documents else None

    async def count_documents(self, filtre=None, *args, **kwargs):
        return len(await self._documents(filtre))

    async def insert_one(self, document, *args, **kwargs):
        async with self._verrou:
            with self._verrou_postgres() as depot:
                propre = dict(document)
                cid = str(propre.get("id") or propre.get("_id") or uuid.uuid4().hex)
                propre["id"] = cid
                propre["_id"] = cid
                propre.setdefault("tenant_id", self._tenant())
                await depot.upsert(propre)
                return SimpleNamespace(inserted_id=cid, acknowledged=True)

    async def _modifier(self, filtre, modification, *, upsert=False, plusieurs=False):
        async with self._verrou:
            with self._verrou_postgres() as depot:
                documents = await self._documents(filtre, depot)
            if not plusieurs:
                documents = documents[:1]
                avant = [dict(document) for document in documents]
                for document in documents:
                    _appliquer(document, modification)
                    document.setdefault("tenant_id", self._tenant())
                    document.setdefault("_id", str(document.get("id") or ""))
                    await depot.upsert(document)
                if not documents and upsert:
                    document = _base_upsert(filtre)
                    _appliquer(document, modification)
                    document["id"] = str(document.get("id") or uuid.uuid4().hex)
                    document.setdefault("_id", document["id"])
                    document.setdefault("tenant_id", self._tenant())
                    await depot.upsert(document)
                    return SimpleNamespace(matched_count=0, modified_count=0,
                                           upserted_id=document["id"])
                modifies = sum(1 for initial, final in zip(avant, documents) if initial != final)
                return SimpleNamespace(matched_count=len(documents), modified_count=modifies,
                                       upserted_id=None)

    async def update_one(self, filtre, modification, *args, **kwargs):
        upsert = bool(kwargs.get("upsert", args[0] if args else False))
        return await self._modifier(filtre, modification, upsert=upsert)

    async def update_many(self, filtre, modification, *args, **kwargs):
        upsert = bool(kwargs.get("upsert", args[0] if args else False))
        return await self._modifier(filtre, modification, upsert=upsert, plusieurs=True)

    async def find_one_and_update(self, filtre, modification, projection=None, sort=None,
                                  upsert=False, return_document=False, *args, **kwargs):
        async with self._verrou:
            with self._verrou_postgres() as depot:
                documents = await self._documents(filtre, depot)
                documents = _trier(documents, sort)[:1]
                if documents:
                    avant = dict(documents[0])
                    _appliquer(documents[0], modification)
                    documents[0].setdefault("tenant_id", self._tenant())
                    documents[0].setdefault("_id", str(documents[0].get("id") or ""))
                    await depot.upsert(documents[0])
                    resultat = dict(documents[0]) if return_document else avant
                    return _projeter(resultat, projection)
                if upsert:
                    document = _base_upsert(filtre)
                    _appliquer(document, modification)
                    document["id"] = str(document.get("id") or uuid.uuid4().hex)
                    document.setdefault("_id", document["id"])
                    document.setdefault("tenant_id", self._tenant())
                    await depot.upsert(document)
                    return _projeter(document, projection) if return_document else None
                return None

    async def replace_one(self, filtre, remplacement, *args, **kwargs):
        upsert = bool(kwargs.get("upsert", args[0] if args else False))
        async with self._verrou:
            with self._verrou_postgres() as depot:
                documents = (await self._documents(filtre, depot))[:1]
                if documents:
                    ancien = documents[0]
                    propre = dict(remplacement)
                    propre.setdefault("id", ancien.get("id"))
                    propre.setdefault("_id", ancien.get("_id") or propre.get("id"))
                    propre.setdefault("tenant_id", self._tenant())
                    await depot.upsert(propre)
                    return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
                if upsert:
                    propre = dict(remplacement)
                    propre["id"] = str(propre.get("id") or uuid.uuid4().hex)
                    propre.setdefault("_id", propre["id"])
                    propre.setdefault("tenant_id", self._tenant())
                    await depot.upsert(propre)
                    return SimpleNamespace(matched_count=0, modified_count=0,
                                           upserted_id=propre["id"])
                return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def delete_one(self, filtre, *args, **kwargs):
        async with self._verrou:
            with self._verrou_postgres() as depot:
                documents = (await self._documents(filtre, depot))[:1]
                if documents:
                    await depot.supprimer_plusieurs([documents[0]["id"]])
                return SimpleNamespace(deleted_count=len(documents), acknowledged=True)

    async def delete_many(self, filtre, *args, **kwargs):
        async with self._verrou:
            with self._verrou_postgres() as depot:
                documents = await self._documents(filtre, depot)
                ids = [document["id"] for document in documents]
                if ids:
                    await depot.supprimer_plusieurs(ids)
                return SimpleNamespace(deleted_count=len(ids), acknowledged=True)

    async def bulk_write(self, operations, *args, **kwargs):
        compteurs = {"inserted": 0, "matched": 0, "modified": 0, "deleted": 0, "upserted": 0}
        for operation in operations:
            nom = type(operation).__name__
            filtre = getattr(operation, "_filter", None)
            document = getattr(operation, "_doc", getattr(operation, "document", None))
            upsert = bool(getattr(operation, "_upsert", False))
            if nom == "InsertOne":
                await self.insert_one(document)
                compteurs["inserted"] += 1
            elif nom in {"UpdateOne", "UpdateMany"}:
                resultat = await (self.update_many if nom == "UpdateMany" else self.update_one)(
                    filtre, document, upsert=upsert)
                compteurs["matched"] += resultat.matched_count
                compteurs["modified"] += resultat.modified_count
                compteurs["upserted"] += int(resultat.upserted_id is not None)
            elif nom == "ReplaceOne":
                resultat = await self.replace_one(filtre, document, upsert=upsert)
                compteurs["matched"] += resultat.matched_count
                compteurs["modified"] += resultat.modified_count
                compteurs["upserted"] += int(resultat.upserted_id is not None)
            elif nom in {"DeleteOne", "DeleteMany"}:
                resultat = await (self.delete_many if nom == "DeleteMany" else self.delete_one)(filtre)
                compteurs["deleted"] += resultat.deleted_count
            else:
                raise NotImplementedError(f"opération bulk non supportée : {nom}")
        return SimpleNamespace(inserted_count=compteurs["inserted"],
                               matched_count=compteurs["matched"],
                               modified_count=compteurs["modified"],
                               deleted_count=compteurs["deleted"],
                               upserted_count=compteurs["upserted"], bulk_api_result={})

    def create_index(self, *args, **kwargs):
        return "index-logique"

    def aggregate(self, *args, **kwargs):
        raise NotImplementedError("aggregate n'est pas utilisé sur les cas Travail")
