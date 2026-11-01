"""Boucle locale du dispatcher outbox et du projecteur graphe.

    JUMEAU_WORKER_PG_DSN=... GRAPH_STORE=neo4j ... PYTHONPATH=. python -m meridian.adapters.inbound.worker.outbox_worker

Les événements `graph.synchroniser` sont projetés dans le GraphStore ; les autres types
sont marqués publiés sans consommateur local. `--une-passe` traite une file bornée puis
quitte ; sans cette option, la boucle tourne jusqu'à SIGTERM/SIGINT (supervision systemd).

Avec RLS actif, un rôle ``NOBYPASSRLS`` exige exactement un tenant
(``JUMEAU_WORKER_TENANTS``) par processus ; le balayage global utilise le rôle dédié
``meridian_worker`` (``BYPASSRLS``).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import threading

import psycopg

from meridian.adapters.outbound.neo4j import graph_store
from meridian.adapters.outbound.postgres import rls
from meridian.adapters.outbound.postgres.execution_defaults import DispatcherOutbox
from meridian.adapters.outbound.neo4j.projecteur_graphe import ProjecteurGraphe

from .config import dsn_worker, option_connexion_tenant, tenants_worker

journal = logging.getLogger("meridian.execution.outbox_worker")


def _connexion(dsn: str, tenant: str | None = None):
    """Connexion du dispatcher ; le tenant est posé au niveau session quand fourni."""
    option = option_connexion_tenant(tenant)
    supplements = {"options": option} if option else {}
    return psycopg.connect(dsn, autocommit=True, connect_timeout=5, **supplements)


class BoucleOutbox:
    def __init__(self, dispatcher: DispatcherOutbox, intervalle: float = 0.5):
        self.dispatcher = dispatcher
        self.intervalle = max(0.05, float(intervalle))
        self._stop = threading.Event()
        self._thread = None

    def demarrer(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self.tourner, name="meridian-outbox", daemon=True)
        self._thread.start()
        return self._thread

    def tourner(self):
        while not self._stop.is_set():
            try:
                self.dispatcher.traiter()
            except Exception:  # noqa: BLE001
                journal.exception("outbox : cycle en échec")
            self._stop.wait(self.intervalle)

    def arreter(self, timeout: float = 5.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)


def principal() -> None:
    parseur = argparse.ArgumentParser(description="Dispatcher outbox Méridian")
    parseur.add_argument("--dsn", default=None,
                         help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    parseur.add_argument("--intervalle", type=float, default=0.5)
    parseur.add_argument("--une-passe", action="store_true",
                         help="traite une file bornée puis quitte")
    args = parseur.parse_args()
    dsn = args.dsn or dsn_worker()
    if not dsn:
        raise SystemExit("JUMEAU_WORKER_PG_DSN ou JUMEAU_PG_DSN (ou --dsn) requis")
    logging.basicConfig(level=logging.INFO)
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            configuration = rls.configurer_worker(
                conn, tenants=tenants_worker(), multi=False)
    except rls.ConfigurationWorker as exc:
        raise SystemExit(str(exc)) from exc
    if configuration["rls"] and configuration["mode"] == rls.MODE_WORKER_BYPASS:
        journal.warning(
            "outbox worker : rôle %s BYPASSRLS, lecture globale des tenants ; "
            "rôle dédié attendu", configuration["role"]["nom"])
    tenant = (configuration["tenants"][0]
              if configuration["rls"] and configuration["mode"] != rls.MODE_WORKER_BYPASS
              else None)
    graphe = graph_store.ouvrir()
    try:
        if graphe["mode"] != graph_store.MODE_NEO4J:
            raise SystemExit(
                "worker outbox : GRAPH_STORE=neo4j requis (un store mémoire perdrait les projections)")
        projecteur = ProjecteurGraphe(graphe["store"])
        publieurs = {"graph.synchroniser": projecteur.traiter, "graph.sync": projecteur.traiter}
        if os.environ.get("JUMEAU_SQS_QUEUE_URL") or os.environ.get("JUMEAU_EVENTBRIDGE_BUS") \
                or os.environ.get("JUMEAU_EVENTBRIDGE_BUS_NAME"):
            from meridian.adapters.outbound.aws.adapters import publieur_depuis_env
            publieurs["*"] = publieur_depuis_env().publier_ligne
        dispatcher = DispatcherOutbox(
            lambda: _connexion(dsn, tenant),
            publieurs,
        )
        if args.une_passe:
            journal.info("outbox worker : %s événement(s) traité(s)", dispatcher.traiter())
            return
        boucle = BoucleOutbox(dispatcher, args.intervalle)

        def arreter(signum, frame):
            boucle.arreter()

        signal.signal(signal.SIGTERM, arreter)
        signal.signal(signal.SIGINT, arreter)
        journal.info("outbox worker démarré (%s)", graphe["mode"])
        boucle.demarrer().join()
    finally:
        graphe["fermer"]()


if __name__ == "__main__":
    principal()
