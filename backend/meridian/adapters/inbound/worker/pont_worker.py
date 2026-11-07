"""Worker de l'outbox ``pont_canonique``.

    JUMEAU_PONT_CANONIQUE=1 PYTHONPATH=. python -m meridian.adapters.inbound.worker.pont_worker --once

Le flag est **désactivé par défaut**. Le worker réclame un lot borné avec un bail, applique
chaque événement dans une transaction Postgres, puis marque ``done`` seulement après commit.
Une exception d'application est convertie en ``failed`` avec backoff borné : elle ne remonte
jamais vers l'appelant. Un bail expiré est repris par un autre worker ; le jeton de fencing
empêche l'ancien détenteur d'écraser l'état.

Métriques émises dans les logs : ``pont_events_pending``, ``pont_lag_seconds``,
``pont_failed_total``, ``pont_apply_duration_seconds``.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import os
import signal
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo

__all__ = [
    "BouclePont",
    "COLLECTION",
    "FLAG_ENV",
    "MetriquesPont",
    "PontWorker",
    "WorkerPont",
    "WorkerPontCanonique",
    "actif",
    "principal",
]

FLAG_ENV = "JUMEAU_PONT_CANONIQUE"
COLLECTION = pont_mongo.COLLECTION
_VALEURS_ACTIVES = {"1", "true", "vrai", "oui", "yes", "on"}

journal = logging.getLogger("meridian.pont_worker")


def actif(env: Mapping[str, str] | None = None) -> bool:
    """Flag opt-in : absent ou toute valeur autre que oui/true/1/on vaut désactivé."""
    source = os.environ if env is None else env
    return str(source.get(FLAG_ENV) or "").strip().lower() in _VALEURS_ACTIVES


def _instant(valeur: Any = None) -> str:
    if valeur is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, datetime):
        return valeur.astimezone(timezone.utc).isoformat(timespec="seconds")
    return str(valeur)


def _message(exc: BaseException) -> str:
    texte = str(exc).strip() or exc.__class__.__name__
    return texte[:500]


class MetriquesPont:
    """Compteurs minimaux, nommés comme les métriques attendues par l'exploitation."""

    def __init__(self) -> None:
        self.pont_failed_total = 0
        self.pont_events_pending = 0
        self.pont_events_failed = 0
        self.pont_lag_seconds = 0.0
        self._durees: list[float] = []

    def evenement(self, duree: float) -> None:
        self._durees.append(max(0.0, float(duree)))

    def lot(self, statistiques: Mapping[str, Any] | None) -> None:
        statistiques = statistiques or {}
        self.pont_events_pending = int(statistiques.get("pont_events_pending") or 0)
        self.pont_events_failed = int(statistiques.get("pont_events_failed") or 0)
        self.pont_lag_seconds = float(statistiques.get("pont_lag_seconds") or 0.0)

    def instantane(self) -> dict[str, Any]:
        total = sum(self._durees)
        return {
            "pont_events_pending": self.pont_events_pending,
            "pont_events_failed": self.pont_events_failed,
            "pont_lag_seconds": self.pont_lag_seconds,
            "pont_failed_total": self.pont_failed_total,
            "pont_apply_duration_seconds": {
                "count": len(self._durees),
                "total": total,
                "moyenne": (total / len(self._durees)) if self._durees else 0.0,
            },
        }


class WorkerPont:
    def __init__(self, depot, appliquer, *, worker_id: str | None = None,
                 lot: int = 20, bail_secondes: int = 60, intervalle: float = 2.0,
                 env: Mapping[str, str] | None = None, journal_=None,
                 metriques: MetriquesPont | None = None, maintenant=None):
        self.depot = depot
        self.appliquer = appliquer
        self.worker_id = worker_id or f"pont-{uuid.uuid4().hex[:8]}"
        self.lot = max(1, int(lot))
        self.bail_secondes = max(1, int(bail_secondes))
        self.intervalle = max(0.05, float(intervalle))
        self.env = env
        self.journal = journal_ or journal
        self.metriques = metriques or MetriquesPont()
        # Horloge injectable pour les tests ; le dépôt garde la sienne pour les baux.
        self.maintenant = maintenant
        self._arret = asyncio.Event()

    def actif(self) -> bool:
        return actif(self.env)

    def arreter(self) -> None:
        self._arret.set()

    async def _reprendre_expires(self) -> None:
        methode = getattr(self.depot, "reprendre_expires", None)
        if callable(methode):
            resultat = methode()
            if inspect.isawaitable(resultat):
                await resultat

    async def _statistiques(self) -> None:
        methode = getattr(self.depot, "statistiques", None)
        if not callable(methode):
            return
        try:
            resultat = methode()
            if inspect.isawaitable(resultat):
                resultat = await resultat
        except Exception:  # noqa: BLE001 - une métrique ne tue pas le worker
            self.journal.exception("pont : statistiques indisponibles")
            return
        self.metriques.lot(resultat if isinstance(resultat, Mapping) else None)

    async def traiter_lot(self, limite: int | None = None) -> dict[str, Any]:
        if not self.actif():
            return {"actif": False, "traites": 0, "reussis": 0, "echecs": 0, "ignores": 0}
        borne = min(self.lot, max(1, int(limite or self.lot)))
        try:
            await self._reprendre_expires()
        except Exception:  # noqa: BLE001 - la reprise est une optimisation, pas un prérequis
            self.journal.exception("pont : reprise des baux expirés en échec")
        methode = getattr(self.depot, "reclamer_lot", None) or self.depot.reclamer
        try:
            evenements = await methode(
                self.worker_id, limite=borne, bail_secondes=self.bail_secondes)
        except Exception:  # noqa: BLE001 - une panne de claim ne remonte jamais
            self.journal.exception("pont : claim en échec")
            await self._statistiques()
            return {"actif": True, "traites": 0, "reussis": 0, "echecs": 1, "ignores": 0}
        if isinstance(evenements, Mapping):
            evenements = [evenements]
        evenements = list(evenements or [])

        reussis = echecs = ignores = 0
        for evenement in evenements:
            identifiant = evenement.get("_id")
            jeton = evenement.get("lock_token")
            debut = time.perf_counter()
            try:
                resultat = self.appliquer(evenement)
                if inspect.isawaitable(resultat):
                    resultat = await resultat
            except Exception as exc:  # noqa: BLE001 - le worker ne remonte jamais vers le legacy
                echecs += 1
                self.metriques.pont_failed_total += 1
                message = _message(exc)
                self.journal.warning(
                    "pont_failed_total=%d evenement=%s : %s",
                    self.metriques.pont_failed_total, identifiant, message)
                try:
                    await self.depot.echouer(identifiant, jeton, message)
                except Exception:  # noqa: BLE001
                    self.journal.exception(
                        "pont : impossible de marquer l'échec evenement=%s", identifiant)
            else:
                canonical_ids = None
                if isinstance(resultat, Mapping):
                    canonical_ids = resultat.get("canonical_ids")
                try:
                    termine = await self.depot.terminer(
                        identifiant, jeton, canonical_ids=canonical_ids, resultat=resultat)
                except Exception:  # noqa: BLE001
                    termine = False
                    self.journal.exception(
                        "pont : impossible de terminer evenement=%s", identifiant)
                if termine:
                    reussis += 1
                else:
                    ignores += 1
                    self.journal.warning(
                        "pont : fencing perdu, résultat ignoré evenement=%s", identifiant)
            finally:
                duree = time.perf_counter() - debut
                self.metriques.evenement(duree)
                self.journal.info(
                    "pont_apply_duration_seconds=%.6f evenement=%s",
                    duree, identifiant)

        await self._statistiques()
        self.journal.info(
            "pont_events_pending=%d pont_lag_seconds=%.3f pont_failed_total=%d "
            "traites=%d reussis=%d echecs=%d ignores=%d",
            self.metriques.pont_events_pending, self.metriques.pont_lag_seconds,
            self.metriques.pont_failed_total, len(evenements), reussis, echecs, ignores)
        return {
            "actif": True,
            "traites": len(evenements),
            "reussis": reussis,
            "echecs": echecs,
            "ignores": ignores,
        }

    async def une_passe(self, limite: int | None = None) -> dict[str, Any]:
        return await self.traiter_lot(limite)

    async def tourner(self) -> None:
        while not self._arret.is_set():
            try:
                await self.traiter_lot()
            except Exception:  # noqa: BLE001 - une passe ne tue pas le worker
                self.journal.exception("pont : passe en échec")
            try:
                await asyncio.wait_for(self._arret.wait(), timeout=self.intervalle)
            except asyncio.TimeoutError:
                pass


BouclePont = WorkerPont
WorkerPontCanonique = WorkerPont
PontWorker = WorkerPont


def _depuis_environnement(arguments) -> tuple[str | None, str | None, str | None]:
    mongo_url = arguments.mongo_url or os.environ.get("MONGO_URL")
    base = arguments.db_name or os.environ.get("DB_NAME") or "meridian_db"
    dsn = (arguments.dsn or os.environ.get("JUMEAU_WORKER_PG_DSN")
           or os.environ.get("JUMEAU_PG_DSN"))
    return mongo_url, base, dsn


def principal(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Worker du pont Travail → canonique")
    parseur.add_argument("--once", "--une-passe", dest="une_passe", action="store_true",
                         help="traite un lot borné puis quitte")
    parseur.add_argument("--intervalle", type=float, default=2.0)
    parseur.add_argument("--lot", type=int, default=20)
    parseur.add_argument("--mongo-url", default=None, help="URL Mongo (défaut : MONGO_URL)")
    parseur.add_argument("--db-name", default=None, help="base Mongo (défaut : DB_NAME)")
    parseur.add_argument("--dsn", default=None,
                         help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    arguments = parseur.parse_args(argv)

    if not actif():
        print(f"{FLAG_ENV} désactivé : aucun événement ne sera traité")
        return 0

    mongo_url, base, dsn = _depuis_environnement(arguments)
    if not mongo_url:
        print("MONGO_URL (ou --mongo-url) requis", file=sys.stderr)
        return 2
    if not dsn:
        print("JUMEAU_WORKER_PG_DSN ou JUMEAU_PG_DSN (ou --dsn) requis", file=sys.stderr)
        return 2

    import psycopg
    from motor.motor_asyncio import AsyncIOMotorClient

    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    logging.basicConfig(level=logging.INFO)
    client = AsyncIOMotorClient(mongo_url)

    async def scenario() -> int:
        collection = client[base][COLLECTION]
        depot = pont_mongo.DepotPontCanonique(collection)
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
            worker = WorkerPont(
                depot,
                lambda evenement: pont_pg.appliquer_evenement(conn, evenement),
                lot=arguments.lot,
                intervalle=arguments.intervalle,
            )

            def arreter(signum, frame):
                worker.arreter()

            signal.signal(signal.SIGTERM, arreter)
            signal.signal(signal.SIGINT, arreter)
            if arguments.une_passe:
                bilan = await worker.une_passe()
                journal.info("pont : une passe terminée %s", bilan)
            else:
                journal.info("pont worker démarré (lot=%d)", worker.lot)
                await worker.tourner()
        return 0

    try:
        return asyncio.run(scenario())
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(principal())
