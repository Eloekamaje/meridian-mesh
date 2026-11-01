"""Moteur d'exécution : réclame un run, exécute, termine ou planifie un retry."""
from __future__ import annotations

import logging
import os
import random
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import psycopg

from jumeau.execution import depot
from jumeau.execution.processus import ProcessManager
from jumeau.execution.modele import (
    AnnulationExecution,
    ApprobationRequise,
    CommandeExecution,
    ErreurTransitoire,
    EtatRun,
    TransitionInvalide,
)

journal = logging.getLogger("meridian.execution")


def _dsn() -> str:
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise TransitionInvalide("JUMEAU_PG_DSN non configuré")
    return dsn


class MoteurExecution:
    """Ordonnanceur minimal, indépendant de FastAPI.

    `executeur` est une fonction synchrone `run -> dict`. Elle est appelée dans le
    worker, jamais dans le process HTTP. Un exécuteur asynchrone sera branché via un
    adapter dédié (ThreadPool ou worker agent) plutôt que par un `asyncio.run` local.
    """

    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        executeur: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        *,
        worker_id: str | None = None,
        bail_secondes: int = 30,
    ):
        self.connect = connect or (lambda: psycopg.connect(_dsn(), autocommit=True))
        self.executeur = executeur
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.bail_secondes = int(bail_secondes)

    def process_manager(self, run: Mapping[str, Any], *,
                        verifier_annulation: Callable[[], bool] | None = None) -> ProcessManager:
        """Construit le journal d'étapes d'un run avec la même fabrique de connexion."""
        return ProcessManager(self.connect, run, verifier_annulation=verifier_annulation)

    def _avec(self, action):
        conn = self.connect()
        try:
            return action(conn)
        finally:
            close = getattr(conn, "close", None)
            if close:
                close()

    def creer(self, commande: CommandeExecution) -> tuple[dict, bool]:
        run, cree = self._avec(lambda conn: depot.creer_run(conn, commande))
        return depot.run_public(run), cree

    def lire(self, tenant_id: str, run_id: str) -> dict | None:
        run = self._avec(lambda conn: depot.obtenir_run(conn, tenant_id, run_id))
        return depot.run_public(run)

    def evenements(self, tenant_id: str, run_id: str, apres_id: int = 0) -> list[dict]:
        return self._avec(lambda conn: [
            depot.evenement_public(e)
            for e in depot.evenements(conn, tenant_id, run_id, apres_id)
        ])

    def annuler(self, tenant_id: str, run_id: str) -> dict:
        run = self._avec(lambda conn: depot.demander_annulation(conn, tenant_id, run_id))
        return depot.run_public(run)

    def traiter_prochain(self) -> dict | None:
        if self.executeur is None:
            raise TransitionInvalide("aucun exécuteur configuré")

        def reclamer(conn):
            depot.reprendre_baux_expires(conn)
            depot.expirer_file(conn)
            depot.rearmer_timers(conn)
            return depot.reclamer_run(conn, self.worker_id, self.bail_secondes)

        run = self._avec(reclamer)
        if run is None:
            return None
        tenant, run_id, token = run["tenant_id"], run["run_id"], int(run["fencing_token"])

        try:
            with self._battre(tenant, run_id, token):
                if run.get("cancel_requested_at"):
                    return self._terminer(tenant, run_id, token, EtatRun.CANCELLED,
                                          erreur="annulé avant exécution")
                try:
                    resultat = self.executeur(run)
                    if resultat is None:
                        resultat = {}
                    if not isinstance(resultat, Mapping):
                        raise TypeError("l'exécuteur doit retourner un mapping JSON")
                except AnnulationExecution:
                    return self._terminer(tenant, run_id, token, EtatRun.CANCELLED,
                                          erreur="annulé pendant l'exécution")
                except ApprobationRequise as exc:
                    journal.info("run %s : en attente d'approbation (%s)", run_id, exc)
                    return self.lire(tenant, run_id) or {}
                except ErreurTransitoire as exc:
                    return self._retry(tenant, run_id, token, run, exc)
                except Exception as exc:  # erreur permanente de l'exécuteur
                    return self._echec(tenant, run_id, token, exc)

                actuel = self._avec(lambda conn: depot.obtenir_run(conn, tenant, run_id))
                if actuel and actuel.get("cancel_requested_at"):
                    return self._terminer(tenant, run_id, token, EtatRun.CANCELLED,
                                          resultat=dict(resultat),
                                          erreur="annulé pendant l'exécution")
                return self._terminer(tenant, run_id, token, EtatRun.SUCCEEDED, resultat=dict(resultat))
        except TransitionInvalide as exc:
            journal.warning("run %s : transition refusée : %s", run_id, exc)
            return self.lire(tenant, run_id)

    def _retry(self, tenant: str, run_id: str, token: int, run: Mapping[str, Any],
               exc: Exception) -> dict:
        tentative = max(1, int(run.get("tentative") or 1))
        maximum = max(1, int(run.get("max_tentatives") or 1))
        if tentative >= maximum:
            return self._echec(tenant, run_id, token, exc)
        delai = min(300.0, 5.0 * (2 ** (tentative - 1))) + random.uniform(0, 1)
        due = datetime.now(timezone.utc) + timedelta(seconds=delai)
        try:
            self._avec(lambda conn: depot.planifier_retry(
                conn, tenant, run_id, self.worker_id, token,
                f"{type(exc).__name__}: {exc}"[:2000], due_at=due,
            ))
        except TransitionInvalide as refus:
            journal.warning("run %s : retry refusé : %s", run_id, refus)
        except Exception:
            journal.exception("run %s : planification du retry impossible", run_id)
        return self.lire(tenant, run_id) or {}

    def _echec(self, tenant: str, run_id: str, token: int, exc: Exception) -> dict:
        try:
            return self._terminer(tenant, run_id, token, EtatRun.FAILED,
                                  erreur=f"{type(exc).__name__}: {exc}"[:2000])
        except TransitionInvalide as refus:
            journal.warning("run %s : échec final refusé : %s", run_id, refus)
            return self.lire(tenant, run_id) or {}

    @contextmanager
    def _battre(self, tenant: str, run_id: str, token: int):
        stop = threading.Event()
        intervalle = max(0.2, self.bail_secondes / 3.0)

        def battre():
            while not stop.wait(intervalle):
                try:
                    ok = self._avec(lambda conn: depot.renouveler_bail(
                        conn, tenant, run_id, self.worker_id, token, self.bail_secondes,
                    ))
                except Exception:
                    journal.exception("run %s : heartbeat impossible", run_id)
                    return
                if not ok:
                    journal.warning("run %s : bail perdu, arrêt du heartbeat", run_id)
                    return

        thread = threading.Thread(target=battre, name=f"heartbeat-{run_id[:8]}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=2)

    def _terminer(self, tenant: str, run_id: str, token: int, etat: EtatRun,
                  resultat: Mapping[str, Any] | None = None, erreur: str | None = None) -> dict:
        run = self._avec(lambda conn: depot.terminer(
            conn, tenant, run_id, self.worker_id, token, etat, resultat=resultat, erreur=erreur,
        ))
        return depot.run_public(run)
