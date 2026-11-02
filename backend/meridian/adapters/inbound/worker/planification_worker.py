"""Synchronisation des sources de pilotage (travail, people, finance, incidents).

Une passe :
    python -m meridian.adapters.inbound.worker.planification_worker --tenant demo --tous
Daemon :
    python -m meridian.adapters.inbound.worker.planification_worker --tenant demo --tous --intervalle 300
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
import time

import psycopg

from meridian.adapters.inbound.worker.config import dsn_worker
from meridian.adapters.outbound.postgres import depot, planification, rls
from meridian.adapters.outbound.travail import (
    source_finance, source_incidents, source_people, source_travail,
)
from meridian.application.planification import sync

journal = logging.getLogger("meridian.planification.sync")


def _sources(conn, tenant: str, source_id: str | None, tous: bool) -> list[dict]:
    if source_id:
        source = planification.lire_source(conn, tenant, source_id)
        return [source] if source else []
    if tous:
        return planification.lister_sources(conn, tenant)
    raise SystemExit("--source-id ou --tous requis")


def _fabrique(usage: str):
    fabriques = {"travail": source_travail, "people": source_people,
                 "finance": source_finance, "incidents": source_incidents}
    if usage not in fabriques:
        raise ValueError(f"usage de source inconnu : {usage!r}")
    return fabriques[usage]


def _une_passe(conn, tenant: str, source_id: str | None, tous: bool) -> list[dict]:
    resultats = []
    sources = _sources(conn, tenant, source_id, tous)
    for source in sources:
        try:
            usage = source.get("usage") or "travail"
            resultats.append({"source": source["id"],
                              **sync.synchroniser(depot, conn, source, _fabrique(usage)(source))})
        except Exception as erreur:  # noqa: BLE001 - le CLI continue les autres sources
            journal.warning("source %s en échec : %s", source["id"], erreur)
            resultats.append({"source": source["id"], "ok": False, "erreur": str(erreur)})
    return resultats


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description="Synchronisation des sources de pilotage")
    parseur.add_argument("--tenant", required=True)
    parseur.add_argument("--source-id")
    parseur.add_argument("--tous", action="store_true")
    parseur.add_argument("--dsn", default=None)
    parseur.add_argument("--sans-schema", action="store_true")
    parseur.add_argument("--intervalle", type=float, default=0.0,
                         help="daemon : secondes entre deux passes (0 = une seule passe)")
    args = parseur.parse_args(argv)
    dsn = args.dsn or dsn_worker()
    if not dsn:
        raise SystemExit("JUMEAU_WORKER_PG_DSN ou JUMEAU_PG_DSN requis")
    logging.basicConfig(level=logging.INFO)
    arret = threading.Event()
    if args.intervalle > 0:
        signal.signal(signal.SIGTERM, lambda *_: arret.set())
        signal.signal(signal.SIGINT, lambda *_: arret.set())
    with psycopg.connect(dsn, autocommit=True) as conn:
        if not args.sans_schema:
            depot.appliquer_schema(conn)
        while not arret.is_set():
            contexte = rls.contexte_tenant(conn, args.tenant) if rls.est_actif() else None
            if contexte is not None:
                contexte.__enter__()
            try:
                resultats = _une_passe(conn, args.tenant, args.source_id, args.tous)
            finally:
                if contexte is not None:
                    contexte.__exit__(None, None, None)
            print(json.dumps(resultats, ensure_ascii=False, default=str), flush=True)
            if args.intervalle <= 0:
                break
            arret.wait(max(1.0, args.intervalle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
