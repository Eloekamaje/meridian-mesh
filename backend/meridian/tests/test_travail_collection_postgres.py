"""La collection Travail Postgres interprète le sous-ensemble Mongo utilisé par l'API."""
import asyncio
import os

import pytest
from pymongo import InsertOne, UpdateOne

from meridian.application import tenant_context
from meridian.adapters.outbound.postgres.travail_collection import (
    PostgresTravailCollection, _appliquer, _correspond,
)


class DepotFaux:
    tenant_id = "local"

    def __init__(self, documents=None):
        self.documents = {document["id"]: dict(document) for document in documents or []}

    async def lister_recents(self, limite=None):
        return [dict(document) for document in self.documents.values()]

    async def upsert(self, document):
        self.documents[str(document["id"])] = dict(document)
        return True

    async def supprimer_plusieurs(self, ids):
        return sum(1 for cid in ids if self.documents.pop(str(cid), None) is not None)


def _collection(documents):
    return PostgresTravailCollection(depot=DepotFaux(documents))


def test_filtres_mongo_utilises_par_les_cas():
    document = {"id": "c1", "pieces_count": 2, "statut": "ouvert", "origine": {"histoire_id": "h1"}}
    assert _correspond(document, {"origine.histoire_id": "h1"})
    assert _correspond(document, {"$or": [{"pieces_count": {"$lt": 3}},
                                          {"pieces_count": {"$exists": False}}]})
    assert not _correspond(document, {"pieces_count": {"$exists": False}})
    assert _correspond(document, {"statut": {"$ne": "clos"}})
    assert _correspond(document, {"statut": {"$in": ["ouvert", "clos"]}})


def test_mises_a_jour_nested_push_addtoset_inc_max_unset_pull():
    document = {"id": "c1", "pieces_count": 1, "jumeaux": ["a"],
                "conversation": [{"role": "user"}], "maj_le": "2026-01-01"}
    _appliquer(document, {
        "$inc": {"pieces_count": 2},
        "$max": {"maj_le": "2026-02-01"},
        "$push": {"conversation": {"$each": [{"role": "flore"}]},
                  "historique": {"quand": "2026-02-01", "texte": "fait"}},
        "$addToSet": {"jumeaux": {"$each": ["a", "b"]}},
        "$set": {"conversation.0.retour": "ok"},
        "$unset": {"temporaire": ""},
        "$pull": {"jumeaux": "a"},
    })
    assert document["pieces_count"] == 3
    assert document["maj_le"] == "2026-02-01"
    assert document["conversation"] == [{"role": "user", "retour": "ok"}, {"role": "flore"}]
    assert document["jumeaux"] == ["b"]
    assert document["historique"][0]["texte"] == "fait"
    assert "temporaire" not in document


def test_find_projection_et_tri():
    collection = _collection([
        {"id": "c1", "num": 1, "statut": "ouvert"},
        {"id": "c2", "num": 3, "statut": "clos"},
        {"id": "c3", "num": 2, "statut": "ouvert"},
    ])
    documents = asyncio.run(collection.find({"statut": "ouvert"}, {"_id": 0, "id": 1})
                            .sort("num", -1).to_list(None))
    assert [document["id"] for document in documents] == ["c3", "c1"]


def test_find_one_and_update_reserve_le_quota():
    collection = _collection([{"id": "c1", "pieces_count": 2}])
    place = asyncio.run(collection.find_one_and_update(
        {"id": "c1", "$or": [{"pieces_count": {"$lt": 3}},
                             {"pieces_count": {"$exists": False}}]},
        {"$inc": {"pieces_count": 1}}, {"_id": 1}))
    assert place == {"_id": "c1"}
    assert asyncio.run(collection.find_one({"id": "c1"}))["pieces_count"] == 3
    assert not asyncio.run(collection.find_one_and_update(
        {"id": "c1", "$or": [{"pieces_count": {"$lt": 3}},
                             {"pieces_count": {"$exists": False}}]},
        {"$inc": {"pieces_count": 1}}, {"_id": 1}))


def test_insert_replace_delete_et_bulk():
    collection = _collection([])
    resultat = asyncio.run(collection.insert_one({"_id": "x", "id": "c1", "titre": "Un"}))
    assert resultat.inserted_id == "c1"
    assert asyncio.run(collection.find_one({"id": "c1"}))["titre"] == "Un"

    remplace = asyncio.run(collection.replace_one({"id": "c1"}, {"titre": "Deux"}))
    assert remplace.modified_count == 1
    assert asyncio.run(collection.find_one({"id": "c1"}))["titre"] == "Deux"

    asyncio.run(collection.bulk_write([
        InsertOne({"id": "c2", "titre": "Trois"}),
        UpdateOne({"id": "c2"}, {"$set": {"titre": "Quatre"}}),
    ]))
    assert asyncio.run(collection.find_one({"id": "c2"}))["titre"] == "Quatre"

    assert asyncio.run(collection.delete_one({"id": "c1"})).deleted_count == 1
    assert asyncio.run(collection.delete_many({})).deleted_count == 1


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"),
                    reason="JUMEAU_PG_DSN requis pour la lecture Postgres")
def test_lecture_des_cas_demo_depuis_postgres():
    jeton = tenant_context.definir("demo")
    try:
        collection = PostgresTravailCollection(os.environ["JUMEAU_PG_DSN"], "demo")
        documents = asyncio.run(collection.find({}, {"_id": 0, "id": 1}).to_list(None))
    finally:
        tenant_context.reinitialiser(jeton)
    assert len(documents) == 3


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"),
                    reason="JUMEAU_PG_DSN requis pour le verrou Postgres")
def test_quota_concurrent_serialise_par_advisory_lock():
    import uuid
    tenant = f"test-lock-{uuid.uuid4().hex[:8]}"
    jeton = tenant_context.definir(tenant)
    try:
        premiere = PostgresTravailCollection(os.environ["JUMEAU_PG_DSN"], tenant)
        seconde = PostgresTravailCollection(os.environ["JUMEAU_PG_DSN"], tenant)
        asyncio.run(premiere.insert_one({"id": "c1", "pieces_count": 0}))

        async def reserver(collection):
            return await collection.find_one_and_update(
                {"id": "c1", "pieces_count": {"$lt": 1}},
                {"$inc": {"pieces_count": 1}}, {"_id": 1})

        async def scenario():
            return await asyncio.gather(reserver(premiere), reserver(seconde))

        resultats = asyncio.run(scenario())
        assert sum(1 for resultat in resultats if resultat) == 1
        assert asyncio.run(premiere.find_one({"id": "c1"}))["pieces_count"] == 1
        asyncio.run(premiere.delete_many({}))
    finally:
        tenant_context.reinitialiser(jeton)
