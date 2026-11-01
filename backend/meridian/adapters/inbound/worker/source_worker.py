"""Worker durable de l'alimentation pull-first des jumeaux.

    JUMEAU_WORKER_PG_DSN=... python -m jumeau.source_worker

La boucle lit les échéances Postgres, enfile au plus un run par source due, réclame les runs avec bail/fencing,
puis exécute ``gardien.veiller`` sur la seule source concernée. Un SIGTERM termine proprement la passe courante
et rend la main : les runs non terminés sont repris à l'expiration de leur bail. Aucun webhook n'est écouté.

Avec RLS actif, le worker refuse de démarrer s'il n'a ni liste de tenants
(``JUMEAU_WORKER_TENANTS``, une passe par tenant) ni rôle dédié ``BYPASSRLS``.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import logging
import os
import signal
import socket
import sys

import psycopg
from motor.motor_asyncio import AsyncIOMotorClient

from jumeau import depot, ingestion_runtime as runtime, rls

from .config import dsn_avec_tenant, dsn_worker, normaliser_tenants, tenants_worker

journal = logging.getLogger("meridian.ingestion.worker")

INTERVALLE_DEFAUT = 5
BAIL_DEFAUT = runtime.BAIL_DEFAUT


def _worker_id(defaut: str) -> str:
    return str(defaut or "").strip() or f"source-{socket.gethostname()}-{os.getpid()}"


@contextmanager
def _dsn_du_tenant(dsn: str, tenant: str):
    """Expose ``JUMEAU_PG_DSN`` scopé au tenant courant pour les connexions auxiliaires.

    Le gardien ouvre des connexions depuis l'environnement (rédaction, outils). Pendant
    une passe tenant, elles doivent porter le même tenant que la connexion principale ;
    la valeur précédente est restaurée en sortie.
    """
    precedent = os.environ.get("JUMEAU_PG_DSN")
    os.environ["JUMEAU_PG_DSN"] = dsn_avec_tenant(dsn, tenant)
    try:
        yield
    finally:
        if precedent is None:
            os.environ.pop("JUMEAU_PG_DSN", None)
        else:
            os.environ["JUMEAU_PG_DSN"] = precedent


def _renouveler(dsn: str, tenant: str, run_id: str, worker_id: str,
                fencing_token: int, bail: int) -> bool:
    """Heartbeat sur une connexion dédiée : la connexion du run reste utilisée par le gardien.

    La connexion est distincte : elle repose donc le tenant du run avant de toucher
    ``ingestion_run`` quand les policies sont actives.
    """
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            with rls.contexte_tenant(conn, tenant):
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
        if not await asyncio.to_thread(_renouveler, dsn, run["tenant_id"], run["id"], worker_id,
                                       int(run["fencing_token"]), int(bail)):
            journal.warning("ingestion run %s : bail perdu, la passe courante ne pourra pas committer",
                            run["id"])
            return await tache


async def _un_run(conn, db, dsn: str, *, worker_id: str, bail: int, limite: int):
    """Un tour complet sur la connexion courante : reprise, planification, enfilement, claim."""
    await asyncio.to_thread(runtime.reprendre_baux_expires, conn, limite)
    await asyncio.to_thread(runtime.planifier_sources, conn,
                            int(os.environ.get("JUMEAU_INGESTION_INTERVALLE_S", "300")))
    await asyncio.to_thread(runtime.enfiler_du, conn, limite)
    run = await asyncio.to_thread(runtime.reclamer_run, conn, worker_id, bail)
    if run is None:
        return None
    await _executer_run(dsn, conn, db, run, worker_id, bail)
    return run


async def _un_run_tenant(conn, db, dsn: str, tenant: str, *, worker_id: str,
                         bail: int, limite: int):
    """Un tour pour un tenant : transactions courtes, puis ingestion sous contexte de session.

    Les étapes de planification et de claim ouvrent leur propre transaction avec
    :func:`rls.contexte_tenant`. L'ingestion peut durer : elle utilise
    :func:`rls.contexte_tenant_session` pour ne pas garder une transaction ouverte
    pendant les appels réseau et ne pas bloquer le heartbeat sur la ligne du run.
    """
    with _dsn_du_tenant(dsn, tenant):
        with rls.contexte_tenant(conn, tenant):
            await asyncio.to_thread(runtime.reprendre_baux_expires, conn, limite)
        with rls.contexte_tenant(conn, tenant):
            await asyncio.to_thread(runtime.planifier_sources, conn,
                                    int(os.environ.get("JUMEAU_INGESTION_INTERVALLE_S", "300")))
        with rls.contexte_tenant(conn, tenant):
            await asyncio.to_thread(runtime.enfiler_du, conn, limite)
        with rls.contexte_tenant(conn, tenant):
            run = await asyncio.to_thread(runtime.reclamer_run, conn, worker_id, bail)
        if run is None:
            return None
        with rls.contexte_tenant_session(conn, tenant):
            await _executer_run(dsn, conn, db, run, worker_id, bail)
        return run


async def _boucle_tenants(conn, db, dsn: str, tenants: tuple[str, ...], *, worker_id: str,
                          intervalle: int, bail: int, limite: int, une_passe: bool,
                          arret: asyncio.Event) -> int:
    """Passe par tenant : chaque tour pose ``meridian.tenant_id`` avant tout accès.

    Sans ce contexte, un rôle ``NOBYPASSRLS`` ne verrait aucune source et ne
    réclamerait aucun run : on ne balaie jamais tous les tenants avec un setting unique.
    """
    traites = 0
    while not arret.is_set():
        actifs = 0
        for tenant in tenants:
            if arret.is_set():
                break
            run = await _un_run_tenant(
                conn, db, dsn, tenant, worker_id=worker_id, bail=bail, limite=limite)
            if run is not None:
                actifs += 1
                traites += 1
            if une_passe and traites >= limite:
                break
        if une_passe:
            if actifs == 0 or traites >= limite:
                break
            continue
        if actifs == 0:
            try:
                await asyncio.wait_for(arret.wait(), timeout=intervalle)
            except asyncio.TimeoutError:
                pass
    return 0 if une_passe and traites == 0 else traites


async def boucle(conn, db, dsn: str, *, worker_id: str, intervalle: int, bail: int,
                 limite: int, une_passe: bool, arret: asyncio.Event,
                 tenants: tuple[str, ...] | None = None) -> int:
    """Boucle durable : reprise des baux expirés, enfilement des échéances, exécution, puis attente.

    Sans ``tenants``, le comportement historique est conservé (un seul passage global).
    Avec ``tenants``, chaque passe est encadrée par :func:`rls.contexte_tenant`.
    """
    if tenants:
        return await _boucle_tenants(
            conn, db, dsn, tenants, worker_id=worker_id, intervalle=intervalle, bail=bail,
            limite=limite, une_passe=une_passe, arret=arret)

    traites = 0
    while not arret.is_set():
        run = await _un_run(conn, db, dsn, worker_id=worker_id, bail=bail, limite=limite)
        if run is None:
            if une_passe:
                break
            try:
                await asyncio.wait_for(arret.wait(), timeout=intervalle)
            except asyncio.TimeoutError:
                pass
            continue
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
    dsn = getattr(options, "dsn", None) or dsn_worker()
    mongo = os.environ.get("MONGO_URL")
    base = os.environ.get("DB_NAME")
    if not dsn:
        raise SystemExit(
            "JUMEAU_WORKER_PG_DSN ou JUMEAU_PG_DSN absent : worker d'ingestion impossible")
    if not mongo or not base:
        raise SystemExit("MONGO_URL et DB_NAME requis : le gardien publie situations et notifications")
    # Les connexions auxiliaires (rédaction, outils) lisent JUMEAU_PG_DSN : elles doivent
    # utiliser le DSN worker, puis le DSN scopé au tenant pendant chaque passe.
    os.environ["JUMEAU_PG_DSN"] = dsn
    client = AsyncIOMotorClient(mongo)
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            if not options.sans_schema:
                depot.appliquer_schema(conn)
            try:
                configuration = rls.configurer_worker(
                    conn, tenants=getattr(options, "tenants", ()), multi=True)
            except rls.ConfigurationWorker as exc:
                raise SystemExit(str(exc)) from exc
            if configuration["rls"] and configuration["mode"] == rls.MODE_WORKER_BYPASS:
                journal.warning(
                    "worker d'ingestion : rôle %s BYPASSRLS, les policies ne protègent pas "
                    "ce processus ; rôle dédié attendu", configuration["role"]["nom"])
            return await boucle(
                conn, client[base], dsn,
                worker_id=_worker_id(options.worker_id),
                intervalle=max(1, int(options.intervalle)),
                bail=max(1, int(options.bail)),
                limite=max(1, int(options.limite)),
                une_passe=bool(options.une_passe),
                arret=arret,
                tenants=configuration["tenants"] or None,
            )
    finally:
        client.close()


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m jumeau.source_worker",
        description="Boucle pull-first d'ingestion des sources (Postgres + Mongo, sans webhook).")
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--worker-id", default="", help="identité du worker (défaut : hôte-pid)")
    analyseur.add_argument("--tenant", action="append", default=None, metavar="SLUG",
                           help="tenant à traiter (répétable ; sinon JUMEAU_WORKER_TENANTS)")
    analyseur.add_argument("--intervalle", type=int, default=int(os.environ.get("JUMEAU_INGESTION_POLL_S", INTERVALLE_DEFAUT)),
                           help="secondes d'attente quand aucune source n'est due")
    analyseur.add_argument("--bail", type=int, default=int(os.environ.get("JUMEAU_INGESTION_BAIL_S", BAIL_DEFAUT)),
                           help="durée du bail d'un run, renouvelé pendant la passe")
    analyseur.add_argument("--limite", type=int, default=int(os.environ.get("JUMEAU_INGESTION_LIMITE", 20)),
                           help="sources enfilées/reprises par tour")
    analyseur.add_argument("--une-passe", action="store_true", help="traiter les runs dus puis sortir")
    analyseur.add_argument("--sans-schema", action="store_true", help="ne pas rejouer schema.sql au démarrage")
    options = analyseur.parse_args(argv)
    try:
        options.tenants = (normaliser_tenants(options.tenant) if options.tenant
                           else tenants_worker())
    except ValueError as exc:
        print(f"tenant invalide : {exc}", file=sys.stderr)
        return 2
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
