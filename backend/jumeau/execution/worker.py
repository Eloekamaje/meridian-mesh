"""Boucle worker et point d'entrée local.

    JUMEAU_PG_DSN=... PYTHONPATH=. python -m jumeau.execution.worker

Le worker ne dépend pas de FastAPI. Il réclame des runs, exécute le registre
d'exécuteurs et termine ou planifie un retry.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time
from typing import Any

import psycopg

from jumeau.execution.executeurs import executeur_par_type
from jumeau.execution.moteur import MoteurExecution

journal = logging.getLogger("meridian.execution.worker")


class BoucleWorker:
    def __init__(self, moteur: MoteurExecution, intervalle: float = 0.5):
        self.moteur = moteur
        self.intervalle = max(0.05, float(intervalle))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def demarrer(self) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop.clear()
        self._thread = threading.Thread(target=self.tourner, name="meridian-execution-worker", daemon=True)
        self._thread.start()
        return self._thread

    def tourner(self) -> None:
        while not self._stop.is_set():
            try:
                traite = self.moteur.traiter_prochain()
            except Exception:  # noqa: BLE001 - la boucle ne doit jamais mourir sur un run
                journal.exception("worker : run en échec inattendu")
                traite = None
            if traite is None:
                self._stop.wait(self.intervalle)

    def arreter(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)


def principal() -> None:
    parseur = argparse.ArgumentParser(description="Worker d'exécution Méridian")
    parseur.add_argument("--dsn", default=os.environ.get("JUMEAU_PG_DSN"))
    parseur.add_argument("--worker-id", default=None)
    parseur.add_argument("--intervalle", type=float, default=0.5)
    args = parseur.parse_args()
    if not args.dsn:
        raise SystemExit("JUMEAU_PG_DSN ou --dsn requis")
    # Le service d'analyse lit la même configuration que le moteur.
    os.environ["JUMEAU_PG_DSN"] = args.dsn
    logging.basicConfig(level=logging.INFO)
    moteur = MoteurExecution(
        connect=lambda: psycopg.connect(args.dsn, autocommit=True),
        executeur=executeur_par_type,
        worker_id=args.worker_id,
    )
    boucle = BoucleWorker(moteur, args.intervalle)

    def arreter(signum, frame):
        journal.info("worker %s : arrêt demandé", moteur.worker_id)
        boucle.arreter()

    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    journal.info("worker %s démarré", moteur.worker_id)
    boucle.demarrer().join()


if __name__ == "__main__":
    principal()
