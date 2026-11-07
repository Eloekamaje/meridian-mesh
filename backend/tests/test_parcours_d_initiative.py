"""Parcours D complet sans insertion manuelle de l'Initiative (Mongo et Postgres réels).

Ce test est opt-in : il exige ``MONGO_URL`` (Mongo de test) et ``JUMEAU_PG_DSN`` (Postgres
local). Il prouve la chaîne C3 → D → C1 :

    POST /initiatives/{iid}/repondre
      → initiative.maj dans l'outbox
      → worker C1 → SITUATION → INVESTIGATION → DECISION → INITIATIVE
    observation mesure_auto_observations
      → worker D → outcome.mesure
      → worker C1 → OUTCOME
      → GET /boucle/objets/{outcome}?historique=true contient 5 niveaux
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import uuid

import psycopg
import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

from meridian.adapters.inbound.http import boucle as boucle_http
from meridian.adapters.inbound.http import initiatives as initiatives_module
from meridian.adapters.inbound.worker import mesure_auto_worker, pont_worker
from meridian.adapters.outbound.mongo import mesure_auto as mongo_mesure
from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.adapters.outbound.postgres import boucle as pg_boucle
from meridian.adapters.outbound.postgres import depot as pg_depot
from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont
from meridian.application import tenant_context
from meridian.tests.aides_mesure_auto import url_test_autorisee

MONGO_URL = os.environ.get("MONGO_URL")
PG_DSN = os.environ.get("JUMEAU_PG_DSN")
_SERVICES_TEST = bool(
    MONGO_URL and PG_DSN and url_test_autorisee(MONGO_URL)
    and ("127.0.0.1" in PG_DSN or "localhost" in PG_DSN or "[::1]" in PG_DSN))
besoin_services = pytest.mark.skipif(
    not _SERVICES_TEST,
    reason="MONGO_URL et JUMEAU_PG_DSN locaux requis pour le parcours C3/D réel",
)


@pytest.fixture(autouse=True)
def _cle_pont(monkeypatch):
    """Le parcours réel doit passer avec seulement MONGO_URL et JUMEAU_PG_DSN."""
    monkeypatch.setenv(pont.PONT_KEY_ENV, "cle-de-test-pont-canonique-32")


IID = "init-parcours-c3"
SID = "sit-parcours-c3"
METRIQUE = "delai_moyen_jours"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _app_initiatives(db):
    async def journaler(*args, **kwargs):
        return None

    api = APIRouter(prefix="/api")
    api.include_router(initiatives_module.build_initiatives_router({
        "db": db,
        "resoudre_perimetre": lambda acteur, espace: (acteur, {"id": "perso"}),
        "autorisations": lambda espace, ids: set(ids),
        "journaler": journaler,
        "slugify": lambda texte: texte.lower().replace(" ", "-"),
        "NO_ID": {"_id": 0},
    }))
    app = FastAPI()
    app.include_router(api)
    return app


async def _scenario(tenant: str, base: str) -> dict:
    client_mongo = AsyncIOMotorClient(MONGO_URL)
    db = client_mongo[base]
    conn = psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5)
    try:
        pg_depot.appliquer_schema(conn)
        await db.situations.insert_one({
            "id": SID,
            "tenant_id": tenant,
            "titre": "Latence des paiements",
            "resume": "Le délai dépasse la cible.",
            "statut": "active",
            "priorite": "haute",
            "jumeaux": [],
            "cree_le": _maintenant(),
            "detectee": _maintenant(),
        })
        await db.initiatives.insert_one({
            "id": IID,
            "tenant_id": tenant,
            "titre": "Traiter la latence",
            "raison": "Le délai monte malgré l'automatisation",
            "statut": "en_attente",
            "genre": "a_confirmer",
            "jumeaux": [],
            "confiance": 70,
            "situation_id": SID,
            "quand": _maintenant(),
        })
        app = _app_initiatives(db)
        jeton = tenant_context.definir(tenant)
        try:
            async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test") as http:
                reponse = await http.post(
                    f"/api/initiatives/{IID}/repondre",
                    json={"choix": "Créer un nouveau travail"})
        finally:
            tenant_context.reinitialiser(jeton)
        assert reponse.status_code == 200, reponse.text

        outbox = pont_mongo.DepotPontCanonique(db[pont_mongo.COLLECTION])
        evenements = await db[pont_mongo.COLLECTION].find({}).to_list(10)
        assert [evenement["operation"] for evenement in evenements] == [
            pont.OPERATION_INITIATIVE]
        assert evenements[0]["payload"]["initiative"]["statut"] == "acceptee"
        assert evenements[0]["payload"]["situation"]["id"] == SID

        worker_c1 = pont_worker.WorkerPont(
            outbox,
            lambda evenement: pont_pg.appliquer_evenement(conn, evenement),
            worker_id="c3-c1", env={pont_worker.FLAG_ENV: "1"})
        premier = await worker_c1.une_passe(limite=10)
        assert premier["reussis"] == 1, premier

        initiative_id = pont.initiative_id(pont.decision_initiative_id(IID))
        ligne = pg_boucle.lire_boucle(conn, tenant, initiative_id, historique=True)
        assert ligne is not None
        assert [etape["type"] for etape in ligne["chaine"]] == [
            "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]

        observation = mongo_mesure.document_ingestion({
            "id": "obs-parcours-c3",
            "tenant_id": tenant,
            "initiative_id": initiative_id,
            "metrique": METRIQUE,
            "attendu": 5,
            "observe": 7,
            "effets_secondaires": [{"type": "rework", "observe": 3}],
            "periode": "2026-11",
            "quand": _maintenant(),
            "maj_le": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "source": {"type": "twin", "nom": "tbt"},
            "interpretation": "Le délai augmente malgré l'automatisation.",
        })
        await db[mongo_mesure.OBSERVATIONS].insert_one(observation)

        worker_d = mesure_auto_worker.WorkerMesureAuto(
            mongo_mesure.DepotObservationsMesure(db[mongo_mesure.OBSERVATIONS]),
            mongo_mesure.DepotCheckpointsMesure(db[mongo_mesure.CHECKPOINTS]),
            outbox.enfiler,
            rejets=mongo_mesure.DepotRejetsMesure(db[mongo_mesure.REJETS]),
            tenants=(tenant,), lot=10,
            env={mesure_auto_worker.FLAG_ENV: "1"},
            maintenant=_maintenant,
        )
        mesure = await worker_d.une_passe(10)
        assert mesure["actif"] is True
        assert mesure["outcomes"] == 1, mesure
        assert mesure["echecs"] == 0, mesure

        second = await worker_c1.une_passe(limite=10)
        assert second["reussis"] == 1, second

        outcome_id = pont.outcome_id(initiative_id, METRIQUE, "2026-11")
        assert pg_boucle.lire_boucle(conn, tenant, outcome_id) is not None

        app_boucle = FastAPI()
        app_boucle.include_router(boucle_http.router)
        async with AsyncClient(
                transport=ASGITransport(app=app_boucle),
                base_url="http://test") as http:
            trace = await http.get(
                f"/boucle/objets/{outcome_id}?historique=true",
                headers={"X-Tenant": tenant})
        assert trace.status_code == 200, trace.text
        corps = trace.json()
        return {
            "types": [etape["type"] for etape in corps["chaine"]],
            "ids": [etape["id"] for etape in corps["chaine"]],
            "outcome_id": outcome_id,
            "initiative_id": initiative_id,
        }
    finally:
        conn.close()
        client_mongo.close()


@besoin_services
def test_parcours_d_complet_sans_insertion_manuelle_de_l_initiative():
    tenant = f"c3-{uuid.uuid4().hex[:10]}"
    base = f"meridian_c3_{uuid.uuid4().hex[:10]}"
    try:
        resultat = asyncio.run(_scenario(tenant, base))
    finally:
        with MongoClient(MONGO_URL) as client:
            client.drop_database(base)
        with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
            conn.execute("DELETE FROM objet_entreprise WHERE tenant_id = %s", (tenant,))

    assert resultat["types"] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME"]
    assert resultat["ids"][0] == SID
    assert resultat["ids"][3] == resultat["initiative_id"]
    assert resultat["ids"][4] == resultat["outcome_id"]
