"""Backfill Mongo -> Postgres du read model Travail.

    python -m meridian.adapters.outbound.postgres.migrer_travail --tenant local --dry-run
    python -m meridian.adapters.outbound.postgres.migrer_travail --tenant local --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os

import psycopg
from motor.motor_asyncio import AsyncIOMotorClient

from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
from meridian.adapters.outbound.postgres import depot as postgres_depot
from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
from meridian.application.travail_sync import remplir
from meridian.domain.tenant import normaliser_slug


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m meridian.adapters.outbound.postgres.migrer_travail",
        description="Backfill idempotent des cas Mongo vers la table Postgres travail")
    analyseur.add_argument("--tenant", default=None,
                           help="tenant Postgres (défaut : JUMEAU_TENANT puis local)")
    analyseur.add_argument("--mongo-url", default=None, help="URL Mongo (défaut : MONGO_URL)")
    analyseur.add_argument("--db-name", default=None, help="base Mongo (défaut : DB_NAME)")
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--limite", type=int, default=500)
    analyseur.add_argument("--sans-schema", action="store_true")
    groupe = analyseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", dest="appliquer", action="store_false")
    groupe.add_argument("--apply", dest="appliquer", action="store_true")
    analyseur.set_defaults(appliquer=False)
    analyseur.add_argument("--max-lots", type=int, default=None)
    args = analyseur.parse_args(argv)

    tenant = normaliser_slug(args.tenant or os.environ.get("JUMEAU_TENANT") or "local")
    url = args.mongo_url or os.environ.get("MONGO_URL")
    base = args.db_name or os.environ.get("DB_NAME") or "meridian_db"
    if not url:
        raise SystemExit("MONGO_URL (ou --mongo-url) requis")
    dsn = args.dsn or os.environ.get("JUMEAU_WORKER_PG_DSN") or os.environ.get("JUMEAU_PG_DSN")
    client = AsyncIOMotorClient(url)

    async def scenario():
        try:
            source = TravailMongo(client[base].cases)
            if not args.appliquer:
                return await remplir(source, None, limite=max(1, args.limite),
                                     appliquer=False, max_lots=args.max_lots)
            if not dsn:
                raise SystemExit("JUMEAU_PG_DSN (ou --dsn) requis avec --apply")
            with psycopg.connect(dsn, autocommit=True) as conn:
                if not args.sans_schema:
                    postgres_depot.appliquer_schema(conn)
                cible = TravailPostgres(conn=conn, tenant_id=tenant)
                return await remplir(source, cible, limite=max(1, args.limite),
                                     appliquer=True, max_lots=args.max_lots)
        finally:
            client.close()

    bilan = asyncio.run(scenario())
    if args.appliquer:
        print(f"backfill travail : {bilan.lus} lus, {bilan.ecrits} écrits, "
              f"tenant={tenant!r}, {bilan.lots} lot(s)")
    else:
        print(f"backfill travail (dry-run) : {bilan.lus} document(s) à écrire, "
              f"tenant={tenant!r} ; relancer avec --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
