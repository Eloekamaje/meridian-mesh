"""Boucle locale du dispatcher outbox et du projecteur graphe.

    JUMEAU_PG_DSN=... GRAPH_STORE=neo4j ... PYTHONPATH=. python -m jumeau.execution.outbox_worker

Les événements `graph.synchroniser` sont projetés dans le GraphStore ; les autres types
sont marqués publiés sans consommateur local.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time

import psycopg

from jumeau import graph_store
from jumeau.execution.outbox import DispatcherOutbox
from jumeau.execution.projecteur_graphe import ProjecteurGraphe

journal = logging.getLogger("meridian.execution.outbox_worker")


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
    parseur.add_argument("--dsn", default=os.environ.get("JUMEAU_PG_DSN"))
    parseur.add_argument("--intervalle", type=float, default=0.5)
    args = parseur.parse_args()
    if not args.dsn:
        raise SystemExit("JUMEAU_PG_DSN ou --dsn requis")
    logging.basicConfig(level=logging.INFO)
    graphe = graph_store.ouvrir()
    projecteur = ProjecteurGraphe(graphe["store"])
    dispatcher = DispatcherOutbox(
        lambda: psycopg.connect(args.dsn, autocommit=True, connect_timeout=5),
        {"graph.synchroniser": projecteur.traiter, "graph.sync": projecteur.traiter},
    )
    boucle = BoucleOutbox(dispatcher, args.intervalle)

    def arreter(signum, frame):
        boucle.arreter()

    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    journal.info("outbox worker démarré (%s)", graphe["mode"])
    try:
        boucle.demarrer().join()
    finally:
        graphe["fermer"]()


if __name__ == "__main__":
    principal()
