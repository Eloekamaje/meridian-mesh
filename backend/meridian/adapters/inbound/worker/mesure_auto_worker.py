"""Worker de mesure automatique : observations Mongo → Outcomes dans l'outbox C1.

Il est **distinct** du worker du pont C1 : il ne lit ni n'écrit Postgres. Il lit la collection
``mesure_auto_observations`` par tenant, transforme chaque observation complète en Outcome
canonique avec :mod:`meridian.application.mesure_auto`, puis enfile l'événement signé dans
l'outbox ``pont_canonique``. C'est le worker C1 qui applique ensuite les Outcomes.

    JUMEAU_MESURE_AUTO=1 PONT_KEY=... MONGO_URL=... DB_NAME=... \
        python -m meridian.adapters.inbound.worker.mesure_auto_worker --once

Le flag ``JUMEAU_MESURE_AUTO`` est **désactivé par défaut** : sans lui, le worker ne lit rien et
le reste du système est inchangé.

Idempotence, corrections et reprise :

- le checkpoint est un document par tenant dans ``mesure_auto_checkpoints`` (dernier
  ``(maj_le, sequence, id)`` traité), avancé par CAS ; la lecture principale seeke l'index
  canonique ``maj_le_utc`` et backfille les documents legacy par lots bornés ;
- un rejeu ré-enfile les mêmes événements, que l'outbox C1 déduplique par ``_id`` déterministe ;
- une observation mise à jour (nouveau ``maj_le``) est relue ; l'empreinte du payload complet
  change, donc elle produit un nouvel événement qui met à jour le même Outcome canonique sans
  collision d'idempotence ;
- une erreur **permanente** (schéma, taille, collision, erreur inattendue) va en dead-letter
  dans ``mesure_auto_rejets`` et le checkpoint avance ;
- une erreur **transitoire** d'infrastructure (Mongo, signature) n'avance pas le checkpoint et est
  retentée ; après ``tentatives_max`` elle est dead-letterée ;
- une erreur d'**horloge** (``quand``/``maj_le`` futur) n'est jamais dead-letterée : elle attend
  que l'horloge rattrape, sans consommer les tentatives ;
- un document sans ``id``/``maj_le`` n'est pas lu (filtre Mongo) et est compté par l'audit à
  chaque passe : il ne bloque jamais le tenant ;
- si le dead-letter est indisponible sur une erreur permanente, le lot échoue explicitement :
  aucun checkpoint n'avance en silence.

Métriques de log : ``mesure_auto_lues``, ``mesure_auto_outcomes``, ``mesure_auto_doublons``,
``mesure_auto_rejets``, ``mesure_auto_echecs``, ``mesure_auto_non_conformes``.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import inspect
import logging
import os
import re
import signal
import sys
from collections.abc import Mapping
from typing import Any

from meridian.adapters.inbound.worker.pont_worker import _est_permanent
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


_JETON_SENSIBLE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9_.~+/=-]{8,}|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{10,}|\bxox[baprs]-[A-Za-z0-9-]{10,})"
)
_URL_SECRET = re.compile(r"(?i)(://[^/\s:@]+:)[^@/\s]+@")


def rediger_message(valeur: Any, limite: int = 300) -> str:
    """Message d'erreur borné et expurgé avant tout log ou dead-letter."""
    texte = _texte(valeur)
    texte = _URL_SECRET.sub(r"\1[redacted]@", texte)
    texte = _JETON_SENSIBLE.sub("[redacted]", texte)
    return texte[:limite]


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
        self.mesure_auto_echecs = 0
        self.mesure_auto_rejets = 0
        self.mesure_auto_non_conformes = 0
        self.mesure_auto_dead_letter_echecs = 0

    def ajouter(self, compteurs: Mapping[str, Any]) -> None:
        self.mesure_auto_lues += int(compteurs.get("lues") or 0)
        self.mesure_auto_outcomes += int(compteurs.get("outcomes") or 0)
        self.mesure_auto_doublons += int(compteurs.get("doublons") or 0)
        self.mesure_auto_echecs += int(compteurs.get("echecs") or 0)
        self.mesure_auto_rejets += int(compteurs.get("rejets") or 0)

    def instantane(self) -> dict[str, int]:
        return {
            "mesure_auto_lues": self.mesure_auto_lues,
            "mesure_auto_outcomes": self.mesure_auto_outcomes,
            "mesure_auto_doublons": self.mesure_auto_doublons,
            "mesure_auto_echecs": self.mesure_auto_echecs,
            "mesure_auto_rejets": self.mesure_auto_rejets,
            "mesure_auto_non_conformes": self.mesure_auto_non_conformes,
            "mesure_auto_dead_letter_echecs": self.mesure_auto_dead_letter_echecs,
        }


class WorkerMesureAuto:
    """Une passe par tenant ; aucun état partagé entre tenants."""

    def __init__(self, observations, checkpoints, enfiler, *, rejets=None,
                 tenants: Any = None, tenant: Any = None, lot: int = 100,
                 intervalle: float = 5.0, env: Mapping[str, str] | None = None,
                 journal_=None, maintenant: Any = None, depuis: Any = None,
                 mesurer=None, tentatives_max: int = 5):
        self.observations = observations
        self.checkpoints = checkpoints
        self.enfiler = enfiler
        self.rejets = rejets
        self.env = env
        self.journal = journal_ or journal
        self.tentatives_max = max(1, int(tentatives_max))
        self.lot = max(1, int(lot))
        self.intervalle = max(0.05, float(intervalle))
        self.maintenant = maintenant
        self.depuis = (mongo_mesure.canoniser_instant(depuis)
                       if _texte(depuis) else None)
        if _texte(depuis) and self.depuis is None:
            raise ValueError("depuis invalide : date ISO attendue")
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
        self._audit_curseurs: dict[str, Any] = {}
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

    async def auditer(self) -> int:
        """Audit borné et rotatif par tenant ; métrique d'alerte à chaque passe."""
        methode = getattr(self.observations, "auditer_lot", None)
        total = 0
        for tenant in self.tenants:
            try:
                if callable(methode):
                    apres = self._audit_curseurs.get(tenant)
                    nombre, dernier, lus = await methode(
                        tenant, apres, mongo_mesure.AUDIT_LIMITE)
                    self._audit_curseurs[tenant] = (
                        dernier if lus >= mongo_mesure.AUDIT_LIMITE else None)
                else:
                    nombre = int(await self.observations.compter_non_conformes(tenant))
            except Exception as exc:  # noqa: BLE001 - l'audit ne bloque pas le worker
                self.journal.warning(
                    "mesure_auto : audit des documents non conformes impossible tenant=%s : %s",
                    tenant, rediger_message(exc))
                continue
            total += int(nombre)
            if nombre:
                self.journal.warning(
                    "mesure_auto_documents_non_conformes=%d tenant=%s", nombre, tenant)
        self.metriques.mesure_auto_non_conformes = total
        return total

    async def _avancer(self, tenant: str, curseur: "mongo_mesure.CurseurObservation") -> bool:
        try:
            retour = await self.checkpoints.ecrire(tenant, curseur)
        except Exception as exc:  # noqa: BLE001 - le rejeu est idempotent, on réessaiera
            self.journal.warning(
                "mesure_auto : checkpoint non écrit tenant=%s observation=%s : %s",
                tenant, curseur.id, rediger_message(exc))
            return False
        if retour is not None and retour < curseur:
            self.journal.warning(
                "mesure_auto : checkpoint non avancé tenant=%s demandé=%s obtenu=%s",
                tenant, curseur, retour)
            return False
        return True

    async def _rejeter(self, tenant: str, document: Mapping[str, Any], raison: Any, *,
                       permanent: bool, compter_tentative: bool = True) -> bool:
        """Enregistre un rejet ; rend ``True`` si l'observation peut être dépassée.

        Un dead-letter indisponible ne doit **jamais** faire avancer le checkpoint en
        silence : on rend ``False`` et le worker échoue explicitement le lot.
        """
        raison_propre = rediger_message(raison)
        if self.rejets is None:
            self.journal.warning(
                "mesure_auto_dead_letter_echecs=1 tenant=%s observation=%s raison=%s",
                tenant, _texte(document.get("id")), raison_propre)
            self.metriques.mesure_auto_dead_letter_echecs += 1
            return False
        try:
            return bool(await self.rejets.enregistrer(
                tenant, document, raison_propre, permanent=permanent,
                tentatives_max=self.tentatives_max,
                compter_tentative=compter_tentative))
        except Exception as exc:  # noqa: BLE001 - journal de secours, pas d'avancement
            self.journal.warning(
                "mesure_auto_dead_letter_echecs=1 tenant=%s observation=%s raison=%s : %s",
                tenant, _texte(document.get("id")), raison_propre, rediger_message(exc))
            self.metriques.mesure_auto_dead_letter_echecs += 1
            return False

    async def _traiter_tenant(self, tenant: str, borne: int) -> dict[str, Any]:
        compteurs = {
            "lues": 0, "outcomes": 0, "doublons": 0, "echecs": 0, "rejets": 0,
        }
        checkpoint = await self.checkpoints.lire(tenant)
        if checkpoint is None and self.depuis:
            checkpoint = mongo_mesure.CurseurObservation(maj_le=self.depuis)
        # Backfill borné : les documents legacy sans `maj_le_utc` rejoignent le seek d'index.
        remplir = getattr(self.observations, "remplir_maj_le_utc", None)
        if callable(remplir):
            try:
                await remplir(tenant, mongo_mesure.BACKFILL_LOT)
            except Exception as exc:  # noqa: BLE001 - le fallback legacy reste disponible
                self.journal.warning(
                    "mesure_auto : backfill maj_le_utc en échec tenant=%s : %s",
                    tenant, rediger_message(exc))
        compter = getattr(self.observations, "compter_a_migrer", None)
        if callable(compter):
            try:
                a_migrer = int(await compter(tenant))
            except Exception as exc:  # noqa: BLE001 - l'audit ne bloque pas le worker
                a_migrer = 0
                self.journal.warning(
                    "mesure_auto : comptage des documents à migrer impossible tenant=%s : %s",
                    tenant, rediger_message(exc))
            if a_migrer:
                # Garde de migration : on ne fait pas avancer le checkpoint tant que des
                # corrections legacy ne sont pas backfillées dans les champs canoniques.
                sans_utc = getattr(self.observations, "compter_sans_maj_le_utc", None)
                if callable(sans_utc):
                    try:
                        nombre_sans_utc = int(await sans_utc(tenant))
                    except Exception:  # noqa: BLE001
                        nombre_sans_utc = -1
                    self.journal.warning(
                        "mesure_auto_documents_sans_maj_le_utc=%d tenant=%s",
                        nombre_sans_utc, tenant)
                self.journal.warning(
                    "mesure_auto_documents_a_migrer=%d tenant=%s", a_migrer, tenant)
                compteurs["echecs"] += 1
                return compteurs
        documents = await self.observations.lister_apres(tenant, checkpoint, borne)
        for document in documents:
            compteurs["lues"] += 1
            identifiant = _texte(document.get("id"))
            try:
                curseur = mongo_mesure.curseur_document(document)
            except ValueError as exc:
                # L'adaptateur filtre déjà ces documents ; on n'arrête pas les autres.
                compteurs["echecs"] += 1
                self.journal.warning(
                    "mesure_auto : document sans curseur lisible tenant=%s : %s",
                    tenant, rediger_message(exc))
                continue
            resultat = self.mesurer(
                document, tenant_id=tenant, maintenant=self._maintenant())
            if not resultat.produit:
                permanent = not resultat.transitoire
                depasse = await self._rejeter(
                    tenant, document, resultat.raison, permanent=permanent,
                    compter_tentative=not resultat.horloge)
                if depasse:
                    compteurs["rejets"] += 1
                    self.journal.warning(
                        "mesure_auto : observation écartée tenant=%s observation=%s "
                        "permanent=%s raison=%s",
                        tenant, identifiant, permanent, rediger_message(resultat.raison))
                    if not await self._avancer(tenant, curseur):
                        compteurs["echecs"] += 1
                        break
                    continue
                compteurs["echecs"] += 1
                self.journal.warning(
                    "mesure_auto : observation conservée tenant=%s observation=%s "
                    "permanent=%s horloge=%s raison=%s",
                    tenant, identifiant, permanent, resultat.horloge,
                    rediger_message(resultat.raison))
                break
            try:
                reponse = self.enfiler(resultat.evenement)
                if inspect.isawaitable(reponse):
                    reponse = await reponse
            except Exception as exc:  # noqa: BLE001 - classer avant de décider
                # Une signature absente/indisponible est environnementale : elle peut se
                # corriger sans perdre la mesure, même si C1 la classe « permanente ».
                permanent = (False if isinstance(exc, pont.SignatureInvalide)
                             else _est_permanent(exc))
                depasse = await self._rejeter(
                    tenant, document, exc, permanent=permanent)
                if depasse:
                    compteurs["rejets"] += 1
                    self.journal.warning(
                        "mesure_auto : enfilage refusé définitivement tenant=%s "
                        "observation=%s permanent=%s raison=%s",
                        tenant, identifiant, permanent, rediger_message(exc))
                    if not await self._avancer(tenant, curseur):
                        compteurs["echecs"] += 1
                        break
                    continue
                compteurs["echecs"] += 1
                self.journal.warning(
                    "mesure_auto : enfilage conservé tenant=%s observation=%s "
                    "permanent=%s raison=%s",
                    tenant, identifiant, permanent, rediger_message(exc))
                break
            if reponse is None:
                # Une réponse vide est traitée comme transitoire : nouvel essai borné.
                depasse = await self._rejeter(
                    tenant, document, "enfilage sans réponse", permanent=False)
                if depasse:
                    compteurs["rejets"] += 1
                    if not await self._avancer(tenant, curseur):
                        compteurs["echecs"] += 1
                        break
                    continue
                compteurs["echecs"] += 1
                break
            if isinstance(reponse, Mapping) and reponse.get("cree"):
                compteurs["outcomes"] += 1
            else:
                compteurs["doublons"] += 1
            if not await self._avancer(tenant, curseur):
                compteurs["echecs"] += 1
                break
        return compteurs

    async def traiter_lot(self, limite: int | None = None) -> dict[str, Any]:
        if not self.actif():
            return {
                "actif": False, "lues": 0, "outcomes": 0, "doublons": 0,
                "echecs": 0, "rejets": 0, "tenants": {},
            }
        # Audit à chaque passe : les documents insérés après le démarrage sont vus.
        await self.auditer()
        borne = min(self.lot, max(1, int(limite or self.lot)))
        total = {
            "lues": 0, "outcomes": 0, "doublons": 0, "echecs": 0, "rejets": 0,
        }
        par_tenant: dict[str, dict[str, Any]] = {}
        for tenant in self.tenants:
            try:
                compteurs = await self._traiter_tenant(tenant, borne)
            except Exception as exc:  # noqa: BLE001 - un tenant en panne ne bloque pas les autres
                self.journal.warning(
                    "mesure_auto : passe en échec tenant=%s : %s",
                    tenant, rediger_message(exc))
                compteurs = {"lues": 0, "outcomes": 0, "doublons": 0,
                             "echecs": 1, "rejets": 0}
            par_tenant[tenant] = compteurs
            for cle in total:
                total[cle] += compteurs[cle]
        self.metriques.ajouter(total)
        self.journal.info(
            "mesure_auto_lues=%d mesure_auto_outcomes=%d mesure_auto_doublons=%d "
            "mesure_auto_echecs=%d mesure_auto_rejets=%d "
            "mesure_auto_non_conformes=%d tenants=%s",
            total["lues"], total["outcomes"], total["doublons"],
            total["echecs"], total["rejets"], self.metriques.mesure_auto_non_conformes,
            ",".join(self.tenants))
        return {"actif": True, **total, "tenants": par_tenant}

    async def une_passe(self, limite: int | None = None) -> dict[str, Any]:
        return await self.traiter_lot(limite)

    async def tourner(self) -> None:
        while not self._arret.is_set():
            try:
                await self.traiter_lot()
            except Exception as exc:  # noqa: BLE001 - une passe ne tue pas le worker
                self.journal.warning(
                    "mesure_auto : passe en échec : %s", rediger_message(exc))
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
                         help="observations par tenant et par passe (défaut : 100, max 1000)")
    parseur.add_argument("--tentatives-max", type=int, default=5,
                         help="reprises d'une erreur transitoire avant dead-letter "
                              "(défaut : 5)")
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
    depuis = None
    if arguments.depuis:
        depuis = mongo_mesure.canoniser_instant(arguments.depuis)
        if depuis is None:
            print("--depuis invalide : date ISO attendue", file=sys.stderr)
            return 2
    if (not arguments.tenant
            and not os.environ.get(_TENANTS_ENV)
            and not os.environ.get(_TENANT_ENV)):
        print("mesure_auto : aucun tenant explicite, repli sur 'local'", file=sys.stderr)
    lot = max(1, min(int(arguments.lot), 1000))
    tentatives_max = max(1, int(arguments.tentatives_max))

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
            rejets = mongo_mesure.DepotRejetsMesure(database[mongo_mesure.REJETS])
            outbox = pont_mongo.DepotPontCanonique(database[pont_mongo.COLLECTION])
            for depot in (observations, rejets, outbox):
                try:
                    await depot.assurer_index()
                except Exception as exc:  # noqa: BLE001 - un index est une optimisation
                    journal.warning(
                        "mesure_auto : création d'index impossible : %s",
                        rediger_message(exc))
            try:
                await observations.assurer_validateur()
            except Exception as exc:  # noqa: BLE001 - validateur indicatif
                journal.warning(
                    "mesure_auto : validateur Mongo indisponible : %s",
                    rediger_message(exc))
            worker = WorkerMesureAuto(
                observations, checkpoints, outbox.enfiler, rejets=rejets,
                tenants=tenants, lot=lot, intervalle=arguments.intervalle,
                depuis=depuis, tentatives_max=tentatives_max)

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
