"""Worker de mesure automatique : observations Mongo → Outcomes dans l'outbox C1.

Il est **distinct** du worker du pont C1 : il ne lit ni n'écrit Postgres. Il lit la collection
``mesure_auto_observations`` par tenant, transforme chaque observation complète en Outcome
canonique avec :mod:`meridian.application.mesure_auto`, puis enfile l'événement signé dans
l'outbox ``pont_canonique``. C'est le worker C1 qui applique ensuite les Outcomes.

    JUMEAU_MESURE_AUTO=1 PONT_KEY=... MONGO_URL=... DB_NAME=... \
        python -m meridian.adapters.inbound.worker.mesure_auto_worker --once

Le flag ``JUMEAU_MESURE_AUTO`` est **désactivé par défaut** : sans lui, le worker ne lit rien et
le reste du système est inchangé.

Idempotence et reprise :

- le checkpoint est un document par tenant dans ``mesure_auto_checkpoints`` (dernier
  ``maj_le`` et dernier ``id`` traités) ;
- un rejeu ré-enfile les mêmes événements, que l'outbox C1 déduplique par ``_id`` déterministe ;
- une observation mise à jour (nouveau ``maj_le``) est relue ; son empreinte change, donc elle
  produit un nouvel événement qui met à jour le même Outcome canonique ;
- une observation incomplète est ignorée avec sa raison dans les logs, et le checkpoint avance :
  elle ne bloque pas le flux tant qu'elle n'est pas corrigée avec un nouveau ``maj_le`` ;
- une panne d'enfilage n'avance pas le checkpoint : l'observation sera rejouée.

Métriques de log : ``mesure_auto_lues``, ``mesure_auto_outcomes``, ``mesure_auto_doublons``,
``mesure_auto_ignores``, ``mesure_auto_echecs``.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import inspect
import logging
import os
import signal
import sys
from collections.abc import Mapping
from typing import Any

from meridian.adapters.outbound.mongo import mesure_auto as mongo_mesure
from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.application import mesure_auto
from meridian.application import pont_canonique as pont

__all__ = [
    "FLAG_ENV",
    "MetriquesMesureAuto",
    "WorkerMesureAuto",
    "actif",
    "principal",
]

FLAG_ENV = "JUMEAU_MESURE_AUTO"
_VALEURS_ACTIVES = {"1", "true", "vrai", "oui", "yes", "on"}
_TENANTS_ENV = "JUMEAU_WORKER_TENANTS"
_TENANT_ENV = "JUMEAU_WORKER_TENANT"

journal = logging.getLogger("meridian.mesure_auto.worker")


def actif(env: Mapping[str, str] | None = None) -> bool:
    """Flag opt-in : absent ou toute valeur autre que oui/true/1/on vaut désactivé."""
    source = os.environ if env is None else env
    return str(source.get(FLAG_ENV) or "").strip().lower() in _VALEURS_ACTIVES


def _instant(valeur: Any = None) -> str:
    if valeur is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, datetime):
        horodatage = valeur
        if horodatage.tzinfo is None:
            horodatage = horodatage.replace(tzinfo=timezone.utc)
        return horodatage.astimezone(timezone.utc).isoformat(timespec="seconds")
    texte = str(valeur).strip()
    return texte or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _tenants(explicites: Any = None, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Tenants du worker : CLI prioritaire, puis environnement, puis ``local`` (un seul tenant)."""
    source = os.environ if env is None else env
    bruts: list[str] = []
    if explicites:
        if isinstance(explicites, str):
            explicites = [explicites]
        bruts.extend(str(valeur).strip() for valeur in explicites if str(valeur).strip())
    if not bruts:
        liste = str(source.get(_TENANTS_ENV) or "").strip()
        if liste:
            bruts.extend(element.strip() for element in liste.split(",") if element.strip())
        else:
            unique = str(source.get(_TENANT_ENV) or "").strip()
            if unique:
                bruts.append(unique)
    if not bruts:
        bruts.append("local")
    resultat: list[str] = []
    for brut in bruts:
        try:
            tenant = pont.normaliser_tenant(brut)
        except pont.PontInvalide as exc:
            raise ValueError(f"tenant invalide : {exc}") from exc
        if tenant not in resultat:
            resultat.append(tenant)
    return tuple(resultat)


class MetriquesMesureAuto:
    """Compteurs minimaux, nommés comme les métriques de log attendues."""

    def __init__(self) -> None:
        self.mesure_auto_lues = 0
        self.mesure_auto_outcomes = 0
        self.mesure_auto_doublons = 0
        self.mesure_auto_ignores = 0
        self.mesure_auto_echecs = 0

    def ajouter(self, compteurs: Mapping[str, Any]) -> None:
        self.mesure_auto_lues += int(compteurs.get("lues") or 0)
        self.mesure_auto_outcomes += int(compteurs.get("outcomes") or 0)
        self.mesure_auto_doublons += int(compteurs.get("doublons") or 0)
        self.mesure_auto_ignores += int(compteurs.get("ignores") or 0)
        self.mesure_auto_echecs += int(compteurs.get("echecs") or 0)

    def instantane(self) -> dict[str, int]:
        return {
            "mesure_auto_lues": self.mesure_auto_lues,
            "mesure_auto_outcomes": self.mesure_auto_outcomes,
            "mesure_auto_doublons": self.mesure_auto_doublons,
            "mesure_auto_ignores": self.mesure_auto_ignores,
            "mesure_auto_echecs": self.mesure_auto_echecs,
        }


class WorkerMesureAuto:
    """Une passe par tenant ; aucun état partagé entre tenants."""

    def __init__(self, observations, checkpoints, enfiler, *, tenants: Any = None,
                 tenant: Any = None, lot: int = 100, intervalle: float = 5.0,
                 env: Mapping[str, str] | None = None, journal_=None,
                 maintenant: Any = None, depuis: Any = None,
                 mesurer=None):
        self.observations = observations
        self.checkpoints = checkpoints
        self.enfiler = enfiler
        self.env = env
        self.journal = journal_ or journal
        self.lot = max(1, int(lot))
        self.intervalle = max(0.05, float(intervalle))
        self.maintenant = maintenant
        self.depuis = _texte(depuis) or None
        self.mesurer = mesurer or mesure_auto.mesurer_observation
        candidats = tenants if tenants is not None else tenant
        if candidats is None:
            candidats = _tenants(None, env)
        elif isinstance(candidats, str):
            candidats = [candidats]
        normalises: list[str] = []
        for candidat in candidats:
            texte = _texte(candidat)
            if not texte:
                continue
            normalise = pont.normaliser_tenant(texte)
            if normalise not in normalises:
                normalises.append(normalise)
        self.tenants = tuple(normalises) or ("local",)
        self.metriques = MetriquesMesureAuto()
        self._arret = asyncio.Event()

    # -- cycle de vie -------------------------------------------------------

    def actif(self) -> bool:
        return actif(self.env)

    def arreter(self) -> None:
        self._arret.set()

    def _maintenant(self) -> str:
        valeur = self.maintenant() if callable(self.maintenant) else self.maintenant
        return _instant(valeur)

    # -- traitement ---------------------------------------------------------

    async def _avancer(self, tenant: str, document: Mapping[str, Any]) -> bool:
        maj_le = _texte(document.get("maj_le"))
        identifiant = _texte(document.get("id"))
        if not maj_le or not identifiant:
            self.journal.warning(
                "mesure_auto : observation sans maj_le/id, checkpoint non avancé tenant=%s",
                tenant)
            return False
        try:
            await self.checkpoints.ecrire(tenant, maj_le, identifiant)
        except Exception:  # noqa: BLE001 - le rejeu est idempotent, on réessaiera
            self.journal.exception(
                "mesure_auto : checkpoint non écrit tenant=%s observation=%s",
                tenant, identifiant)
            return False
        return True

    async def _traiter_tenant(self, tenant: str, borne: int) -> dict[str, Any]:
        compteurs = {"lues": 0, "outcomes": 0, "doublons": 0, "ignores": 0, "echecs": 0}
        checkpoint = await self.checkpoints.lire(tenant) or {}
        maj_le = _texte(checkpoint.get("dernier_maj_le")) or self.depuis
        identifiant = _texte(checkpoint.get("dernier_id"))
        documents = await self.observations.lister_apres(
            tenant, maj_le, identifiant, borne)
        for document in documents:
            compteurs["lues"] += 1
            resultat = self.mesurer(
                document, tenant_id=tenant, maintenant=self._maintenant())
            if not resultat.produit:
                compteurs["ignores"] += 1
                self.journal.warning(
                    "mesure_auto : observation ignorée tenant=%s observation=%s raison=%s",
                    tenant, _texte(document.get("id")), resultat.raison)
                if not await self._avancer(tenant, document):
                    compteurs["echecs"] += 1
                    break
                continue
            try:
                reponse = self.enfiler(resultat.evenement)
                if inspect.isawaitable(reponse):
                    reponse = await reponse
            except Exception as exc:  # noqa: BLE001 - une panne d'enfilage ne tue pas le worker
                compteurs["echecs"] += 1
                self.journal.warning(
                    "mesure_auto : enfilage en échec tenant=%s observation=%s : %s",
                    tenant, _texte(document.get("id")), str(exc)[:300])
                break
            if reponse is None:
                compteurs["echecs"] += 1
                self.journal.warning(
                    "mesure_auto : enfilage best-effort sans réponse tenant=%s observation=%s",
                    tenant, _texte(document.get("id")))
                break
            if isinstance(reponse, Mapping) and reponse.get("cree"):
                compteurs["outcomes"] += 1
            else:
                compteurs["doublons"] += 1
            if not await self._avancer(tenant, document):
                compteurs["echecs"] += 1
                break
        return compteurs

    async def traiter_lot(self, limite: int | None = None) -> dict[str, Any]:
        if not self.actif():
            return {
                "actif": False, "lues": 0, "outcomes": 0, "doublons": 0,
                "ignores": 0, "echecs": 0, "tenants": {},
            }
        borne = min(self.lot, max(1, int(limite or self.lot)))
        total = {"lues": 0, "outcomes": 0, "doublons": 0, "ignores": 0, "echecs": 0}
        par_tenant: dict[str, dict[str, Any]] = {}
        for tenant in self.tenants:
            try:
                compteurs = await self._traiter_tenant(tenant, borne)
            except Exception:  # noqa: BLE001 - un tenant en panne ne bloque pas les autres
                self.journal.exception("mesure_auto : passe en échec tenant=%s", tenant)
                compteurs = {"lues": 0, "outcomes": 0, "doublons": 0, "ignores": 0,
                             "echecs": 1}
            par_tenant[tenant] = compteurs
            for cle in total:
                total[cle] += compteurs[cle]
        self.metriques.ajouter(total)
        self.journal.info(
            "mesure_auto_lues=%d mesure_auto_outcomes=%d mesure_auto_doublons=%d "
            "mesure_auto_ignores=%d mesure_auto_echecs=%d tenants=%s",
            total["lues"], total["outcomes"], total["doublons"], total["ignores"],
            total["echecs"], ",".join(self.tenants))
        return {"actif": True, **total, "tenants": par_tenant}

    async def une_passe(self, limite: int | None = None) -> dict[str, Any]:
        return await self.traiter_lot(limite)

    async def tourner(self) -> None:
        while not self._arret.is_set():
            try:
                await self.traiter_lot()
            except Exception:  # noqa: BLE001 - une passe ne tue pas le worker
                self.journal.exception("mesure_auto : passe en échec")
            try:
                await asyncio.wait_for(self._arret.wait(), timeout=self.intervalle)
            except asyncio.TimeoutError:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _analyseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="python -m meridian.adapters.inbound.worker.mesure_auto_worker",
        description="Mesure automatique : observations Mongo → Outcomes dans l'outbox C1.")
    parseur.add_argument("--once", "--une-passe", dest="une_passe", action="store_true",
                         help="traite un lot borné puis quitte")
    parseur.add_argument("--intervalle", type=float, default=5.0,
                         help="secondes entre deux passes (défaut : 5)")
    parseur.add_argument("--lot", type=int, default=100,
                         help="observations par tenant et par passe (défaut : 100)")
    parseur.add_argument("--tenant", action="append", default=None, metavar="SLUG",
                         help="tenant à traiter (répétable ; sinon JUMEAU_WORKER_TENANTS)")
    parseur.add_argument("--mongo-url", default=None, help="URL Mongo (défaut : MONGO_URL)")
    parseur.add_argument("--db-name", default=None, help="base Mongo (défaut : DB_NAME)")
    parseur.add_argument("--depuis", default=None,
                         help="reprendre après ce maj_le ISO si aucun checkpoint n'existe")
    return parseur


def _mongo(arguments) -> tuple[str, str]:
    url = arguments.mongo_url or os.environ.get("MONGO_URL")
    base = arguments.db_name or os.environ.get("DB_NAME") or "meridian_db"
    return url, base


def principal(argv: list[str] | None = None) -> int:
    arguments = _analyseur().parse_args(argv)

    if not actif():
        print(f"{FLAG_ENV} désactivé : aucun Outcome ne sera produit")
        return 0
    try:
        pont.cle_pont()
    except pont.SignatureInvalide as exc:
        print(str(exc), file=sys.stderr)
        return 2
    mongo_url, base = _mongo(arguments)
    if not mongo_url:
        print("MONGO_URL (ou --mongo-url) requis", file=sys.stderr)
        return 2
    try:
        tenants = _tenants(arguments.tenant)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    from motor.motor_asyncio import AsyncIOMotorClient

    logging.basicConfig(level=logging.INFO)
    client = AsyncIOMotorClient(mongo_url)

    async def scenario() -> int:
        try:
            database = client[base]
            observations = mongo_mesure.DepotObservationsMesure(
                database[mongo_mesure.OBSERVATIONS])
            checkpoints = mongo_mesure.DepotCheckpointsMesure(
                database[mongo_mesure.CHECKPOINTS])
            outbox = pont_mongo.DepotPontCanonique(database[pont_mongo.COLLECTION])
            for depot in (observations, outbox):
                try:
                    await depot.assurer_index()
                except Exception:  # noqa: BLE001 - un index est une optimisation
                    journal.exception("mesure_auto : création d'index impossible")
            worker = WorkerMesureAuto(
                observations, checkpoints, outbox.enfiler_best_effort,
                tenants=tenants, lot=arguments.lot, intervalle=arguments.intervalle,
                depuis=arguments.depuis)

            def arreter(signum, frame):
                worker.arreter()

            signal.signal(signal.SIGTERM, arreter)
            signal.signal(signal.SIGINT, arreter)
            if arguments.une_passe:
                bilan = await worker.une_passe()
                journal.info("mesure_auto : une passe terminée %s", bilan)
                return 1 if bilan.get("echecs") else 0
            journal.info("mesure_auto worker démarré (lot=%d, tenants=%s)",
                         worker.lot, ",".join(worker.tenants))
            await worker.tourner()
            return 0
        finally:
            client.close()

    try:
        return asyncio.run(scenario())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(principal())
