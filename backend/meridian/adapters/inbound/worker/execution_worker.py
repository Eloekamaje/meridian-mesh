"""Boucle worker et point d'entrée local.

    JUMEAU_WORKER_PG_DSN=... PYTHONPATH=. python -m jumeau.execution.worker

Le worker ne dépend pas de FastAPI. Il réclame des runs, exécute le registre
d'exécuteurs et termine ou planifie un retry.

Avec RLS actif, un rôle ``NOBYPASSRLS`` exige exactement un tenant
(``JUMEAU_WORKER_TENANTS``) par processus, posé sur la session ; le balayage global
utilise le rôle dédié ``meridian_worker`` (``BYPASSRLS``).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import threading

import psycopg

from jumeau import rls
from meridian.adapters.inbound.worker.config import (
    dsn_avec_tenant,
    dsn_worker,
    option_connexion_tenant,
    tenants_worker,
)
from meridian.adapters.outbound.postgres import execution_depot
from meridian.application.execution.executeurs import creer_executeurs, executeur_par_type
from meridian.application.execution.moteur import MoteurExecution

journal = logging.getLogger("meridian.execution.worker")


def _connexion(dsn: str, tenant: str | None = None):
    """Connexion du moteur ; le tenant est posé au niveau session quand fourni."""
    option = option_connexion_tenant(tenant)
    supplements = {"options": option} if option else {}
    return psycopg.connect(dsn, autocommit=True, **supplements)


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
    parseur.add_argument("--dsn", default=None,
                         help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    parseur.add_argument("--worker-id", default=None)
    parseur.add_argument("--intervalle", type=float, default=0.5)
    args = parseur.parse_args()
    dsn = args.dsn or dsn_worker()
    if not dsn:
        raise SystemExit("JUMEAU_WORKER_PG_DSN ou JUMEAU_PG_DSN (ou --dsn) requis")
    logging.basicConfig(level=logging.INFO)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            configuration = rls.configurer_worker(
                conn, tenants=tenants_worker(), multi=False)
    except rls.ConfigurationWorker as exc:
        raise SystemExit(str(exc)) from exc
    if configuration["rls"] and configuration["mode"] == rls.MODE_WORKER_BYPASS:
        journal.warning(
            "worker d'exécution : rôle %s BYPASSRLS, lecture globale des tenants ; "
            "rôle dédié attendu", configuration["role"]["nom"])
    tenant = (configuration["tenants"][0]
              if configuration["rls"] and configuration["mode"] != rls.MODE_WORKER_BYPASS
              else None)
    # Le service d'analyse et l'exécuteur cognitif ouvrent leurs propres connexions depuis
    # JUMEAU_PG_DSN : en mode un-tenant, elles doivent porter le tenant de session.
    os.environ["JUMEAU_PG_DSN"] = dsn_avec_tenant(dsn, tenant) if tenant else dsn

    from jumeau import analyse_service

    def connecter_analyse():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)

    executeurs = creer_executeurs(
        analyse_service=analyse_service,
        connect=connecter_analyse,
        depot=execution_depot,
    )
    moteur = MoteurExecution(
        connect=lambda: _connexion(dsn, tenant),
        executeur=lambda run: executeur_par_type(run, executeurs),
        worker_id=args.worker_id,
        depot=execution_depot,
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
