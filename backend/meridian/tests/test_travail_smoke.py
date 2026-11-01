"""Fumée locale : backfill réel Mongo -> Postgres, drapeau postgres, route Actualités.

Sautée si l'un des deux moteurs n'est pas configuré. Nettoie le cas Mongo et les lignes
du tenant de test.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest

from meridian.tests.aides_actualites import client_actualites

besoin_mongo_et_pg = pytest.mark.skipif(
    not os.environ.get("MONGO_URL") or not os.environ.get("JUMEAU_PG_DSN"),
    reason="MONGO_URL et JUMEAU_PG_DSN requis pour la fumée Travail",
)


@besoin_mongo_et_pg
def test_backfill_puis_lecture_actualites_en_postgres(monkeypatch):
    import psycopg
    from motor.motor_asyncio import AsyncIOMotorClient

    from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
    from meridian.adapters.outbound.postgres import depot as postgres_depot
    from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
    from meridian.application.travail_sync import remplir

    identifiant = f"smoke-travail-{uuid.uuid4().hex[:8]}"
    tenant = f"smoke-{uuid.uuid4().hex[:8]}"
    titre = f"Travail de fumée {identifiant}"
    maintenant = datetime.now(timezone.utc).isoformat()
    client_mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    base = client_mongo[os.environ.get("DB_NAME", "meridian_db")]

    async def preparer():
        await base.cases.insert_one({
            "id": identifiant, "titre": titre, "objectif": "Vérifier le chemin Postgres",
            "statut": "ouvert", "portee": "personnel", "responsable": "demo",
            "participants": ["demo"], "jumeaux": [], "conversation": [],
            "historique": [{"quand": maintenant, "texte": f"Travail conservé — {titre}"}],
            "cree_le": maintenant, "maj_le": maintenant,
        })
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            postgres_depot.appliquer_schema(conn)
            cible = TravailPostgres(conn=conn, tenant_id=tenant)
            bilan = await remplir(TravailMongo(base.cases), cible, limite=50)
            return bilan, await cible.compter()

    try:
        bilan, compter = asyncio.run(preparer())
        assert bilan.lus >= 1 and compter == bilan.lus

        monkeypatch.setenv("JUMEAU_TRAVAIL_STORE", "postgres")
        monkeypatch.setenv("JUMEAU_TENANT", tenant)
        client = client_actualites(monkeypatch)

        reponse = client.get("/api/actualites")
        assert reponse.status_code == 200, reponse.text
        histoires = {h["id"]: h for h in reponse.json()["histoires"]}
        assert f"case-{identifiant}" in histoires
        assert histoires[f"case-{identifiant}"]["titre"] == titre
    finally:
        client_mongo.close()

        async def nettoyer():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            try:
                await client[os.environ.get("DB_NAME", "meridian_db")].cases.delete_one(
                    {"id": identifiant})
            finally:
                client.close()

        asyncio.run(nettoyer())
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            conn.execute("DELETE FROM travail WHERE tenant_id = %s", (tenant,))
