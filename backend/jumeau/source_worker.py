"""Worker durable de l'alimentation pull-first des jumeaux.

    python -m jumeau.source_worker

La boucle lit les échéances Postgres, enfile au plus un run par source due, réclame les runs avec bail/fencing,
puis exécute ``gardien.veiller`` sur la seule source concernée. Un SIGTERM termine proprement la passe courante
et rend la main : les runs non terminés sont repris à l'expiration de leur bail. Aucun webhook n'est écouté.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket

import psycopg
from motor.motor_asyncio import AsyncIOMotorClient

from jumeau import depot, ingestion_runtime as runtime

journal = logging.getLogger("meridian.ingestion.worker")

INTERVALLE_DEFAUT = 5
BAIL_DEFAUT = runtime.BAIL_DEFAUT


def _worker_id(defaut: str) -> str:
    return str(defaut or "").strip() or f"source-{socket.gethostname()}-{os.getpid()}"


def _renouveler(dsn: str, run_id: str, worker_id: str, fencing_token: int, bail: int) -> bool:
    """Heartbeat sur une connexion dédiée : la connexion du run reste utilisée par le gardien."""
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            return runtime.renouveler_bail(conn, run_id, worker_id, fencing_token, bail)
    except Exception:  # noqa: BLE001 - un heartbeat manqué sera couvert par le fencing
        journal.warning("ingestion run %s : renouvellement de bail impossible", run_id, exc_info=True)
        return False


async def _executer_run(dsn: str, conn, db, run, worker_id: str, bail: int) -> dict:
    """Exécute un run tout en prolongeant son bail ; le fencing rend l'ancien worker inoffensif s'il perd."""
    tache = asyncio.create_task(runtime.ingerer_run(conn, db, run, worker_id, run["fencing_token"]))
    battement = max(1, int(bail) // 3)
    while True:
        fini, _ = await asyncio.wait({tache}, timeout=battement)
        if fini:
            return tache.result()
        if not await asyncio.to_thread(_renouveler, dsn, run["id"], worker_id,
                                       int(run["fencing_token"]), int(bail)):
            journal.warning("ingestion run %s : bail perdu, la passe courante ne pourra pas committer",
                            run["id"])
            return await tache


async def boucle(conn, db, dsn: str, *, worker_id: str, intervalle: int, bail: int,
                 limite: int, une_passe: bool, arret: asyncio.Event) -> int:
    """Boucle durable : reprise des baux expirés, enfilement des échéances, exécution, puis attente."""
    traites = 0
    while not arret.is_set():
        await asyncio.to_thread(runtime.reprendre_baux_expires, conn, limite)
        await asyncio.to_thread(runtime.planifier_sources, conn,
                                int(os.environ.get("JUMEAU_INGESTION_INTERVALLE_S", "300")))
        await asyncio.to_thread(runtime.enfiler_du, conn, limite)
        run = await asyncio.to_thread(runtime.reclamer_run, conn, worker_id, bail)
        if run is None:
            if une_passe:
                break
            try:
                await asyncio.wait_for(arret.wait(), timeout=intervalle)
            except asyncio.TimeoutError:
                pass
            continue
        await _executer_run(dsn, conn, db, run, worker_id, bail)
        traites += 1
        if une_passe and traites >= limite:
            break
    if une_passe and traites == 0:
        return 0
    return traites


def _installer_signaux(arret: asyncio.Event) -> None:
    boucle_ = asyncio.get_running_loop()

    def _arreter(*_):
        arret.set()

    for numero in (signal.SIGTERM, signal.SIGINT):
        try:
            boucle_.add_signal_handler(numero, _arreter)
        except (NotImplementedError, RuntimeError):  # plateforme sans add_signal_handler
            signal.signal(numero, _arreter)


async def _main_async(options) -> int:
    arret = asyncio.Event()
    _installer_signaux(arret)
    dsn = os.environ.get("JUMEAU_PG_DSN")
    mongo = os.environ.get("MONGO_URL")
    base = os.environ.get("DB_NAME")
    if not dsn:
        raise SystemExit("JUMEAU_PG_DSN absent : worker d'ingestion impossible")
    if not mongo or not base:
        raise SystemExit("MONGO_URL et DB_NAME requis : le gardien publie situations et notifications")
    client = AsyncIOMotorClient(mongo)
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            if not options.sans_schema:
                depot.appliquer_schema(conn)
            return await boucle(
                conn, client[base], dsn,
                worker_id=_worker_id(options.worker_id),
                intervalle=max(1, int(options.intervalle)),
                bail=max(1, int(options.bail)),
                limite=max(1, int(options.limite)),
                une_passe=bool(options.une_passe),
                arret=arret,
            )
    finally:
        client.close()


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m jumeau.source_worker",
        description="Boucle pull-first d'ingestion des sources (Postgres + Mongo, sans webhook).")
    analyseur.add_argument("--worker-id", default="", help="identité du worker (défaut : hôte-pid)")
    analyseur.add_argument("--intervalle", type=int, default=int(os.environ.get("JUMEAU_INGESTION_POLL_S", INTERVALLE_DEFAUT)),
                           help="secondes d'attente quand aucune source n'est due")
    analyseur.add_argument("--bail", type=int, default=int(os.environ.get("JUMEAU_INGESTION_BAIL_S", BAIL_DEFAUT)),
                           help="durée du bail d'un run, renouvelé pendant la passe")
    analyseur.add_argument("--limite", type=int, default=int(os.environ.get("JUMEAU_INGESTION_LIMITE", 20)),
                           help="sources enfilées/reprises par tour")
    analyseur.add_argument("--une-passe", action="store_true", help="traiter les runs dus puis sortir")
    analyseur.add_argument("--sans-schema", action="store_true", help="ne pas rejouer schema.sql au démarrage")
    options = analyseur.parse_args(argv)
    logging.basicConfig(
        level=os.environ.get("JUMEAU_INGESTION_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        return asyncio.run(_main_async(options))
    except KeyboardInterrupt:
        return 0
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        print(exc.code)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
