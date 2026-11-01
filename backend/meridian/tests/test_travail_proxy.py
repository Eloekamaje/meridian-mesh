"""Double écriture Travail : fakes pour chaque écriture et fumée réelle Mongo -> Postgres."""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from meridian.adapters.outbound.mongo.travail_proxy import (
    DSN_ENV, FLAG_ENV, TENANT_ENV, TravailCollection, installer,
)
from meridian.application import tenant_context

besoin_mongo_et_pg = pytest.mark.skipif(
    not os.environ.get("MONGO_URL") or not os.environ.get("JUMEAU_PG_DSN"),
    reason="MONGO_URL et JUMEAU_PG_DSN requis pour la fumée Travail",
)


def _valeur(document, chemin):
    valeur = document
    for morceau in chemin.split("."):
        if not isinstance(valeur, dict):
            return None
        valeur = valeur.get(morceau)
    return valeur


def _correspond(document, filtre):
    for cle, attendu in (filtre or {}).items():
        valeur = _valeur(document, cle)
        if isinstance(attendu, dict):
            if "$in" in attendu and valeur not in attendu["$in"]:
                return False
            if "$gt" in attendu and not (valeur is not None and valeur > attendu["$gt"]):
                return False
            if "$ne" in attendu and valeur == attendu["$ne"]:
                return False
        elif valeur != attendu:
            return False
    return True


def _appliquer(document, modification):
    for operateur, champs in modification.items():
        if operateur == "$set":
            document.update(champs)
        elif operateur == "$unset":
            for cle in champs:
                document.pop(cle, None)
        elif operateur == "$inc":
            for cle, valeur in champs.items():
                document[cle] = document.get(cle, 0) + valeur
        elif operateur == "$push":
            for cle, valeur in champs.items():
                document.setdefault(cle, []).append(valeur)
        elif operateur == "$pull":
            for cle, valeur in champs.items():
                document[cle] = [e for e in document.get(cle, []) if e != valeur]
        else:
            raise AssertionError(f"opérateur non simulé : {operateur}")


class CurseurFaux:
    def __init__(self, documents):
        self.documents = [dict(d) for d in documents]

    def sort(self, tri):
        if isinstance(tri, str):
            tri = [(tri, 1)]
        elif isinstance(tri, tuple):
            tri = [tri]
        for champ, sens in reversed(list(tri)):
            self.documents.sort(key=lambda d: d.get(champ) or "", reverse=sens < 0)
        return self

    def limit(self, nombre):
        self.documents = self.documents[:int(nombre)]
        return self

    async def to_list(self, nombre=None):
        documents = self.documents if nombre is None else self.documents[:int(nombre)]
        return [dict(d) for d in documents]

    def __aiter__(self):
        self._iter = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class CollectionFaux:
    def __init__(self, documents=None):
        self.documents = [dict(d) for d in documents or []]
        self.appels = []
        self._sequence = 0

    def _id(self):
        self._sequence += 1
        return f"oid-{self._sequence}"

    def find(self, filtre=None, projection=None):
        self.appels.append(("find", filtre, projection))
        return CurseurFaux([d for d in self.documents if _correspond(d, filtre)])

    async def find_one(self, filtre=None, projection=None):
        self.appels.append(("find_one", filtre, projection))
        return next((dict(d) for d in self.documents if _correspond(d, filtre)), None)

    def aggregate(self, pipeline):
        self.appels.append(("aggregate", pipeline))
        return CurseurFaux(self.documents)

    async def count_documents(self, filtre):
        self.appels.append(("count_documents", filtre))
        return sum(1 for d in self.documents if _correspond(d, filtre))

    async def insert_one(self, document):
        self.appels.append(("insert_one", dict(document)))
        document.setdefault("_id", self._id())
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id=document["_id"])

    async def update_one(self, filtre, modification, upsert=False):
        self.appels.append(("update_one", filtre, modification))
        for document in self.documents:
            if _correspond(document, filtre):
                _appliquer(document, modification)
                return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        if upsert:
            document = {cle: valeur for cle, valeur in (filtre or {}).items()
                        if not isinstance(valeur, dict)}
            document.setdefault("_id", self._id())
            _appliquer(document, modification)
            self.documents.append(document)
            return SimpleNamespace(matched_count=0, modified_count=0,
                                   upserted_id=document["_id"])
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def update_many(self, filtre, modification, upsert=False):
        self.appels.append(("update_many", filtre, modification))
        touches = 0
        for document in self.documents:
            if _correspond(document, filtre):
                _appliquer(document, modification)
                touches += 1
        if touches:
            return SimpleNamespace(matched_count=touches, modified_count=touches,
                                   upserted_id=None)
        return await self.update_one(filtre, modification, upsert=upsert)

    async def find_one_and_update(self, filtre, modification, projection=None, sort=None,
                                  upsert=False, return_document=False):
        self.appels.append(("find_one_and_update", filtre, modification))
        documents = [d for d in self.documents if _correspond(d, filtre)]
        if sort:
            documents = CurseurFaux(documents).sort(sort).documents
        if documents:
            document = documents[0]
            avant = dict(document)
            _appliquer(document, modification)
            resultat = dict(document) if return_document else avant
            return {cle: resultat.get(cle) for cle in projection} if projection else resultat
        if upsert:
            document = {cle: valeur for cle, valeur in (filtre or {}).items()
                        if not isinstance(valeur, dict)}
            document.setdefault("_id", self._id())
            _appliquer(document, modification)
            self.documents.append(document)
            return dict(document) if return_document else None
        return None

    async def delete_one(self, filtre):
        self.appels.append(("delete_one", filtre))
        for index, document in enumerate(self.documents):
            if _correspond(document, filtre):
                del self.documents[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def delete_many(self, filtre):
        self.appels.append(("delete_many", filtre))
        gardes = [d for d in self.documents if not _correspond(d, filtre)]
        supprimes = len(self.documents) - len(gardes)
        self.documents = gardes
        return SimpleNamespace(deleted_count=supprimes)


class CibleFaux:
    def __init__(self):
        self.documents = {}
        self.appels = []
        self.panne = None

    def _cle(self, document):
        return str(document.get("id") or document.get("_id"))

    async def upsert(self, document):
        self.appels.append(("upsert", dict(document)))
        if self.panne:
            raise self.panne
        self.documents[self._cle(document)] = dict(document)
        return True

    async def supprimer(self, cid):
        self.appels.append(("supprimer", cid))
        if self.panne:
            raise self.panne
        return self.documents.pop(str(cid), None) is not None

    async def supprimer_plusieurs(self, ids):
        self.appels.append(("supprimer_plusieurs", list(ids)))
        if self.panne:
            raise self.panne
        return sum(1 for cid in ids if self.documents.pop(str(cid), None) is not None)


def _document(cid="c1", **champs):
    return {"_id": f"mongo-{cid}", "id": cid, "titre": f"Travail {cid}",
            "maj_le": "2026-01-01T00:00:00+00:00", **champs}


class BaseFaux:
    def __init__(self, collection):
        self.cases = collection


def test_les_lectures_sont_deleguees_telles_quelles():
    collection = CollectionFaux([_document("c1"), _document("c2", statut="clos")])
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    async def scenario():
        assert [d["id"] for d in await proxy.find({}, {"_id": 0}).to_list(None)] == ["c1", "c2"]
        assert (await proxy.find_one({"id": "c2"}))["statut"] == "clos"
        assert await proxy.count_documents({}) == 2
        assert len(await proxy.aggregate([]).to_list(None)) == 2

    asyncio.run(scenario())
    assert cible.appels == []


def test_insert_one_miroite_le_document_et_rend_le_resultat_mongo():
    collection = CollectionFaux()
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)
    document = _document("c1")

    resultat = asyncio.run(proxy.insert_one(document))

    assert resultat.inserted_id == "mongo-c1"
    assert cible.documents["c1"]["titre"] == "Travail c1"


def test_update_one_miroite_le_document_resultant():
    collection = CollectionFaux([_document("c1")])
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.update_one(
        {"id": "c1"}, {"$set": {"titre": "Après", "maj_le": "2026-01-02T00:00:00+00:00"}}))

    assert resultat.matched_count == 1
    assert cible.documents["c1"]["titre"] == "Après"


def test_update_many_miroite_tous_les_documents_touches():
    collection = CollectionFaux([
        _document("c1", statut="ouvert"), _document("c2", statut="ouvert"),
        _document("c3", statut="clos"),
    ])
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.update_many(
        {"statut": "ouvert"}, {"$set": {"statut": "en_cours"}}))

    assert resultat.modified_count == 2
    assert set(cible.documents) == {"c1", "c2"}
    assert all(d["statut"] == "en_cours" for d in cible.documents.values())


def test_find_one_and_update_rend_la_vue_mongo_et_miroite_apres():
    collection = CollectionFaux([_document("c1")])
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    avant = asyncio.run(proxy.find_one_and_update(
        {"id": "c1"}, {"$set": {"titre": "Après"}}))
    assert avant["titre"] == "Travail c1"
    assert cible.documents["c1"]["titre"] == "Après"

    apres = asyncio.run(proxy.find_one_and_update(
        {"id": "c1"}, {"$set": {"titre": "Encore"}}, return_document=True))
    assert apres["titre"] == "Encore"
    assert cible.documents["c1"]["titre"] == "Encore"


def test_find_one_and_update_upsert_miroite_le_document_cree():
    collection = CollectionFaux()
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.find_one_and_update(
        {"id": "nouveau"}, {"$set": {"titre": "Créé"}}, upsert=True))

    assert resultat is None
    assert cible.documents["nouveau"]["titre"] == "Créé"


def test_find_one_and_update_upsert_positionnel_miroite_le_document_cree():
    collection = CollectionFaux()
    cible = CibleFaux()
    proxy = TravailCollection(collection, cible)

    asyncio.run(proxy.find_one_and_update(
        {"id": "nouveau"}, {"$set": {"titre": "Créé"}}, None, None, True))

    assert cible.documents["nouveau"]["titre"] == "Créé"


def test_delete_one_retire_l_identifiant_postgres():
    collection = CollectionFaux([_document("c1"), _document("c2")])
    cible = CibleFaux()
    cible.documents = {"c1": _document("c1"), "c2": _document("c2")}
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.delete_one({"id": "c1"}))

    assert resultat.deleted_count == 1
    assert set(cible.documents) == {"c2"}


def test_delete_many_retire_les_identifiants_touches():
    collection = CollectionFaux([
        _document("c1", statut="ouvert"), _document("c2", statut="ouvert"),
        _document("c3", statut="clos"),
    ])
    cible = CibleFaux()
    cible.documents = {"c1": _document("c1"), "c2": _document("c2"), "c3": _document("c3")}
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.delete_many({"statut": "ouvert"}))

    assert resultat.deleted_count == 2
    assert set(cible.documents) == {"c3"}


def test_une_panne_postgres_ne_casse_pas_l_ecriture_mongo():
    collection = CollectionFaux()
    cible = CibleFaux()
    cible.panne = RuntimeError("Postgres indisponible")
    proxy = TravailCollection(collection, cible)

    resultat = asyncio.run(proxy.insert_one(_document("c1")))

    assert resultat.inserted_id == "mongo-c1"
    assert [d["id"] for d in collection.documents] == ["c1"]


def test_le_drapeau_absent_laisse_la_collection_mongo_intacte(monkeypatch):
    monkeypatch.delenv(FLAG_ENV, raising=False)
    monkeypatch.setenv(DSN_ENV, "postgresql://x/y")
    collection = CollectionFaux()
    base = BaseFaux(collection)

    assert installer(base) is None
    assert base.cases is collection


def test_le_drapeau_actif_sans_dsn_ne_cable_rien(monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    monkeypatch.delenv(DSN_ENV, raising=False)
    collection = CollectionFaux()
    base = BaseFaux(collection)

    assert installer(base) is None
    assert base.cases is collection


def test_le_drapeau_actif_avec_dsn_applique_le_schema_et_cable_le_proxy(monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    monkeypatch.setenv(TENANT_ENV, "banque")
    monkeypatch.delenv(DSN_ENV, raising=False)
    collection = CollectionFaux()
    base = BaseFaux(collection)
    schema, cibles = [], []

    class CibleWiring(CibleFaux):
        def __init__(self, dsn, tenant_id):
            super().__init__()
            self.dsn, self.tenant_id = dsn, tenant_id
            cibles.append(self)

    monkeypatch.setattr("meridian.adapters.outbound.mongo.travail_proxy.psycopg",
                        SimpleNamespace(connect=lambda dsn, autocommit: nullcontext(object())))
    monkeypatch.setattr("meridian.adapters.outbound.mongo.travail_proxy.appliquer_schema",
                        lambda conn: schema.append(conn))
    monkeypatch.setattr("meridian.adapters.outbound.mongo.travail_proxy.TravailPostgres",
                        CibleWiring)

    proxy = installer(base, dsn="postgresql://x/y")

    assert isinstance(base.cases, TravailCollection)
    assert base.cases is proxy
    assert schema
    assert cibles[0].tenant_id == "banque"
    assert installer(base, dsn="postgresql://x/y") is proxy  # idempotent


@besoin_mongo_et_pg
def test_fumee_double_ecriture_mongo_postgres():
    import psycopg
    from motor.motor_asyncio import AsyncIOMotorClient

    from meridian.adapters.outbound.postgres import depot as postgres_depot
    from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres

    identifiant = f"proxy-smoke-{uuid.uuid4().hex[:8]}"
    tenant = f"proxy-smoke-{uuid.uuid4().hex[:8]}"
    maintenant = datetime.now(timezone.utc).isoformat()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    base = client[os.environ.get("DB_NAME", "meridian_db")]
    conn = psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)

    try:
        postgres_depot.appliquer_schema(conn)
        cible = TravailPostgres(conn=conn, tenant_id=tenant)
        proxy = TravailCollection(base.cases, cible)

        async def scenario():
            await proxy.insert_one({"id": identifiant, "titre": "A", "statut": "ouvert",
                                    "maj_le": maintenant, "cree_le": maintenant})
            assert (await cible.lire(identifiant))["titre"] == "A"

            await proxy.update_one({"id": identifiant},
                                   {"$set": {"titre": "B", "maj_le": maintenant}})
            assert (await cible.lire(identifiant))["titre"] == "B"

            await proxy.delete_one({"id": identifiant})
            assert await cible.lire(identifiant) is None

        try:
            asyncio.run(scenario())
        finally:
            client.close()

            async def nettoyer():
                client_nettoyage = AsyncIOMotorClient(os.environ["MONGO_URL"])
                try:
                    await client_nettoyage[os.environ.get("DB_NAME", "meridian_db")].cases.delete_one(
                        {"id": identifiant})
                finally:
                    client_nettoyage.close()

            asyncio.run(nettoyer())
            conn.execute("DELETE FROM travail WHERE tenant_id = %s", (tenant,))
    finally:
        conn.close()


def test_insert_one_ajoute_le_tenant_de_la_requete():
    collection = CollectionFaux()
    cible = CibleFaux()
    cible.tenant_id = "tenant-a"
    proxy = TravailCollection(collection, cible)
    jeton = tenant_context.definir("tenant-a")
    try:
        resultat = asyncio.run(proxy.insert_one({"id": "c1", "titre": "Tenant"}))
    finally:
        tenant_context.reinitialiser(jeton)
    assert resultat.inserted_id
    assert collection.documents[0]["tenant_id"] == "tenant-a"
    assert cible.documents["c1"]["tenant_id"] == "tenant-a"
