"""Tests d'intégration Mongo réel (MongoDB 7) du lot D.

Ils ne s'exécutent que si ``MONGO_URL`` pointe vers un Mongo joignable ; sinon ils sont ignorés.
Ils couvrent les régressions que le faux Mongo ne peut pas voir : conflit d'opérateurs
``WriteError 40`` du dead-letter et starvation du curseur.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import uuid

import pytest

from meridian.adapters.outbound.mongo import mesure_auto as mongo_mesure
from meridian.tests.aides_mesure_auto import url_test_autorisee

MONGO_URL = os.environ.get("MONGO_TEST_URL") or os.environ.get("MONGO_URL")
pytestmark = pytest.mark.skipif(
    not MONGO_URL or not url_test_autorisee(MONGO_URL),
    reason="MONGO_TEST_URL/MONGO_URL de test absent ou refusé (URL de production)")

TENANT = "banque"


def _url_joignable() -> str:
    from pymongo import MongoClient

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
        client.admin.command("ping")
        client.close()
    except Exception:  # noqa: BLE001 - Mongo absent : test d'intégration ignoré
        pytest.skip("Mongo réel indisponible")
    return MONGO_URL


def _observation(identifiant, maj_le, **champs):
    base = {
        "id": identifiant,
        "tenant_id": TENANT,
        "initiative_id": "ini-dec-case-c1-1",
        "metrique": "delai",
        "attendu": 5,
        "observe": 7,
        "periode": "2026-11",
        "quand": "2026-11-05T09:00:00+00:00",
        "maj_le": maj_le,
    }
    base.update(champs)
    return base


def _scenario(callback):
    from motor.motor_asyncio import AsyncIOMotorClient

    url = _url_joignable()
    client = AsyncIOMotorClient(url)
    base = f"test_mesure_auto_{uuid.uuid4().hex[:10]}"

    async def execute():
        try:
            return await callback(client[base])
        finally:
            await client.drop_database(base)
            client.close()

    return asyncio.run(execute())


def test_dead_letter_reel_ne_produit_pas_write_error_et_persiste_dead():
    async def scenario(db):
        collection = db[mongo_mesure.REJETS]
        depot = mongo_mesure.DepotRejetsMesure(collection)
        permanent = _observation("obs-permanent", "2026-11-05T09:01:00+00:00")
        transitoire = _observation("obs-transitoire", "2026-11-05T09:02:00+00:00")

        assert await depot.enregistrer(
            TENANT, permanent, "schéma invalide", permanent=True) is True
        assert await depot.enregistrer(
            TENANT, transitoire, "timeout", permanent=False, tentatives_max=2) is False
        assert await depot.enregistrer(
            TENANT, transitoire, "timeout", permanent=False, tentatives_max=2) is True

        dead = await collection.find({"etat": "dead"}).to_list(10)
        assert {document["observation_id"] for document in dead} == {
            "obs-permanent", "obs-transitoire"}
        assert all(document["tentatives"] >= 1 for document in dead)

    _scenario(scenario)


def test_seek_index_reel_ne_starve_pas_les_nouveaux_documents():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        avant = [
            mongo_mesure.document_ingestion(_observation(
                f"old-{rang}",
                f"2026-11-05T08:{rang // 60:02d}:{rang % 60:02d}+00:00"))
            for rang in range(500)
        ]
        apres = [
            mongo_mesure.document_ingestion(_observation(
                f"new-{rang}", f"2026-11-05T09:0{rang + 1}:00+00:00"))
            for rang in range(5)
        ]
        await collection.insert_many(avant + apres)
        depot = mongo_mesure.DepotObservationsMesure(collection)
        curseur = mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00.000000+00:00", id="curseur")

        documents = await depot.lister_apres(TENANT, curseur, 10)

        assert [document["id"] for document in documents] == [
            "new-0", "new-1", "new-2", "new-3", "new-4"]

    _scenario(scenario)


def test_audit_reel_compte_tenant_non_normalise_et_maj_illisible():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        await collection.insert_many([
            _observation("obs-ok", "2026-11-05T09:00:00+00:00"),
            _observation("obs-tenant", "2026-11-05T09:00:00+00:00", tenant_id="Banque"),
            _observation("obs-maj", "hier"),
        ])
        depot = mongo_mesure.DepotObservationsMesure(collection)

        assert await depot.compter_non_conformes(TENANT) == 2

    _scenario(scenario)


def test_correction_legacy_apres_backfill_est_relue():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        await collection.insert_one(_observation(
            "obs-legacy", "2026-11-05T09:00:00+00:00"))
        depot = mongo_mesure.DepotObservationsMesure(collection)
        assert await depot.remplir_maj_le_utc(TENANT) == 1

        # Producteur legacy : seul `maj_le` avance, `maj_le_utc` reste à 09:00.
        await collection.update_one(
            {"id": "obs-legacy"}, {"$set": {"maj_le": "2026-11-05T10:00:00+00:00"}})
        curseur = mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00.000000+00:00", id="curseur")

        documents = await depot.lister_apres(TENANT, curseur, 10)

        assert [element["id"] for element in documents] == ["obs-legacy"]

    _scenario(scenario)


def test_audit_reel_ignore_les_autres_tenants():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        await collection.insert_many([
            _observation("obs-ok", "2026-11-05T09:00:00+00:00"),
            _observation("obs-banque-mal", "2026-11-05T09:00:00+00:00",
                         tenant_id="Banque"),
            _observation("obs-maj", "hier"),
            _observation("obs-assurance", "hier", tenant_id="assurance"),
        ])
        depot = mongo_mesure.DepotObservationsMesure(collection)

        assert await depot.compter_non_conformes(TENANT) == 2

    _scenario(scenario)


def test_sequence_int_avec_maj_le_utc_est_tiee_apres_curseur():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        documents = []
        for rang, sequence in enumerate((9, 10, 11)):
            document = _observation(
                f"obs-{sequence}", "2026-11-05T10:00:00+00:00")
            document["maj_le_utc"] = datetime(
                2026, 11, 5, 10, 0, tzinfo=timezone.utc)
            document["sequence"] = sequence
            documents.append(document)
        await collection.insert_many(documents)
        depot = mongo_mesure.DepotObservationsMesure(collection)
        tous = await depot.lister_apres(TENANT, None, 10)
        assert [element["id"] for element in tous] == ["obs-9", "obs-10", "obs-11"]
        curseur = mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T10:00:00.000000+00:00",
            sequence=mongo_mesure.sequence_canonique(10), id="obs-10")

        suite = await depot.lister_apres(TENANT, curseur, 10)

        assert [element["id"] for element in suite] == ["obs-11"]

    _scenario(scenario)


def test_audit_reel_tourne_apres_1000_documents():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        valides = [
            {**_observation(f"ok-{rang}", "2026-11-05T09:00:00+00:00"),
             "_id": f"{rang:04d}"}
            for rang in range(1000)
        ]
        mauvais = {**_observation("ko", "hier"), "_id": "1000"}
        await collection.insert_many(valides + [mauvais])
        depot = mongo_mesure.DepotObservationsMesure(collection)

        premier, dernier, lus = await depot.auditer_lot(TENANT, None, 1000)
        second, _dernier2, _lus2 = await depot.auditer_lot(TENANT, dernier, 1000)

        assert (premier, lus) == (0, 1000)
        assert second == 1

    _scenario(scenario)


def test_backfill_reel_ajoute_maj_le_utc_et_permet_le_seek():
    async def scenario(db):
        collection = db[mongo_mesure.OBSERVATIONS]
        await collection.insert_one(_observation(
            "obs-legacy", "2026-11-05T10:00:00+02:00"))
        depot = mongo_mesure.DepotObservationsMesure(collection)

        assert await depot.compter_sans_maj_le_utc(TENANT) == 1
        assert await depot.remplir_maj_le_utc(TENANT) == 1
        assert await depot.compter_sans_maj_le_utc(TENANT) == 0
        document = await collection.find_one({"id": "obs-legacy"})
        assert document["maj_le"] == "2026-11-05T08:00:00.000000+00:00"
        maj_utc = document["maj_le_utc"]
        if maj_utc.tzinfo is None:
            from datetime import timezone
            maj_utc = maj_utc.replace(tzinfo=timezone.utc)
        assert maj_utc.isoformat() == "2026-11-05T08:00:00+00:00"

        documents = await depot.lister_apres(TENANT, None, 10)
        assert [element["id"] for element in documents] == ["obs-legacy"]

    _scenario(scenario)
