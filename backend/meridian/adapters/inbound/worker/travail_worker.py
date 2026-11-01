"""Backfill et synchronisation incrémentale Travail (Mongo -> Postgres).

Backfill complet (dry-run par défaut) :

    python -m meridian.adapters.inbound.worker.travail_worker --tenant local
    python -m meridian.adapters.inbound.worker.travail_worker --tenant local --apply

Worker de rattrapage (les écritures restent Mongo) :

    python -m meridian.adapters.inbound.worker.travail_worker --une-passe
    python -m meridian.adapters.inbound.worker.travail_worker --intervalle 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

import psycopg
from motor.motor_asyncio import AsyncIOMotorClient

from meridian.domain.tenant import normaliser_slug
from meridian.adapters.inbound.worker.config import dsn_worker
from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
from meridian.adapters.outbound.postgres import depot as postgres_depot
from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
from meridian.application.travail_sync import Curseur, remplir, synchroniser

journal = logging.getLogger("meridian.travail.sync")


def _tenant(valeur: str | None) -> str:
    return normaliser_slug(valeur or os.environ.get("JUMEAU_TENANT") or "local")


def _mongo(args) -> tuple[AsyncIOMotorClient, str]:
    url = args.mongo_url or os.environ.get("MONGO_URL")
    base = args.db_name or os.environ.get("DB_NAME") or "meridian_db"
    if not url:
        raise SystemExit("MONGO_URL (ou --mongo-url) requis")
    return AsyncIOMotorClient(url), base


def _dsn(args) -> str:
    valeur = args.dsn or dsn_worker()
    if not valeur:
        raise SystemExit("JUMEAU_PG_DSN (ou --dsn) requis")
    return valeur


def _analyseur(prog: str, worker: bool) -> argparse.ArgumentParser:
    analyseur = argparse.ArgumentParser(
        prog=prog,
        description=("Synchronisation du read model Travail (Mongo -> Postgres)" if worker
                     else "Backfill idempotent des cas Mongo vers la table Postgres travail"))
    analyseur.add_argument("--tenant", default=None,
                           help="tenant Postgres (défaut : JUMEAU_TENANT puis local)")
    analyseur.add_argument("--mongo-url", default=None, help="URL Mongo (défaut : MONGO_URL)")
    analyseur.add_argument("--db-name", default=None, help="base Mongo (défaut : DB_NAME)")
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--limite", type=int, default=500,
                           help="documents par lot (défaut : 500)")
    analyseur.add_argument("--sans-schema", action="store_true",
                           help="ne pas rejouer schema.sql avant d'écrire")
    if worker:
        analyseur.add_argument("--intervalle", type=float, default=5.0,
                               help="secondes entre deux passes (défaut : 5)")
        analyseur.add_argument("--max-lots", type=int, default=100,
                               help="lots maximum par passe (défaut : 100)")
        analyseur.add_argument("--reconcilier-suppressions", action="store_true",
                               help="au démarrage, retirer du read model les cas absents de Mongo")
        analyseur.add_argument("--depuis", default=None,
                               help="reprendre après ce maj_le ISO au lieu du dernier curseur Postgres")
        analyseur.add_argument("--une-passe", action="store_true",
                               help="rattraper puis sortir")
    else:
        groupe = analyseur.add_mutually_exclusive_group()
        groupe.add_argument("--dry-run", dest="appliquer", action="store_false",
                            help="compter sans écrire (défaut)")
        groupe.add_argument("--apply", dest="appliquer", action="store_true",
                            help="écrire dans Postgres")
        analyseur.set_defaults(appliquer=False)
        analyseur.add_argument("--max-lots", type=int, default=None,
                               help="lots maximum (défaut : aucun)")
    return analyseur


def main_backfill(argv=None) -> int:
    args = _analyseur("python -m meridian.adapters.inbound.worker.travail_worker", worker=False).parse_args(argv)
    tenant = _tenant(args.tenant)
    dsn = _dsn(args) if args.appliquer else None
    client, base = _mongo(args)

    async def scenario():
        try:
            source = TravailMongo(client[base].cases)
            if not args.appliquer:
                bilan = await remplir(source, None, limite=max(1, args.limite),
                                      appliquer=False, max_lots=args.max_lots)
                return bilan
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


def _arreter(arret: asyncio.Event):
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(signum, arret.set)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - plateformes sans signaux
            pass


async def _boucle(source, cible, *, curseur: Curseur, intervalle: float, limite: int,
                  max_lots: int, une_passe: bool) -> None:
    arret = asyncio.Event()
    if not une_passe:
        _arreter(arret)
    while not arret.is_set():
        bilan = await synchroniser(source, cible, curseur=curseur, limite=max(1, limite),
                                   appliquer=True, max_lots=max(1, max_lots))
        curseur = bilan.curseur
        journal.info("travail sync : %d lus, %d écrits, curseur maj_le=%s id=%s",
                     bilan.lus, bilan.ecrits, curseur.maj_le, curseur.id)
        if une_passe:
            return
        try:
            await asyncio.wait_for(arret.wait(), timeout=max(0.1, intervalle))
        except asyncio.TimeoutError:
            pass


def main(argv=None) -> int:
    args = _analyseur("python -m meridian.adapters.inbound.worker.travail_worker",
                      worker=True).parse_args(argv)
    tenant = _tenant(args.tenant)
    dsn = _dsn(args)
    client, base = _mongo(args)
    logging.basicConfig(
        level=os.environ.get("JUMEAU_TRAVAIL_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    async def scenario():
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                if not args.sans_schema:
                    postgres_depot.appliquer_schema(conn)
                cible = TravailPostgres(conn=conn, tenant_id=tenant)
                source = TravailMongo(client[base].cases)
                curseur = (Curseur(maj_le=args.depuis) if args.depuis
                           else cible.dernier_curseur())
                journal.info("travail sync : tenant=%s curseur initial maj_le=%s id=%s",
                             tenant, curseur.maj_le, curseur.id)
                if args.reconcilier_suppressions:
                    from meridian.application.travail_sync import supprimer_absents
                    supprimees = await supprimer_absents(source, cible)
                    journal.info("travail sync : %d cas absents supprimés", supprimees)
                await _boucle(source, cible, curseur=curseur,
                              intervalle=args.intervalle, limite=args.limite,
                              max_lots=args.max_lots, une_passe=args.une_passe)
        finally:
            client.close()

    try:
        asyncio.run(scenario())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
