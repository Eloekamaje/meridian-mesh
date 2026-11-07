"""Outbox Mongo du pont Travail → canonique.

La collection ``pont_canonique`` porte les événements en attente. L'écriture est idempotente :
l'identifiant est déterministe et l'insertion utilise ``$setOnInsert``, jamais un remplacement.
Un worker réclame un événement avec un bail et un jeton de fencing ; seul le détenteur du jeton
peut le terminer ou l'échouer. Un bail expiré est repris par un autre worker, et le jeton périmé
du premier ne peut plus écraser l'état.

Aucune transaction distribuée Mongo/Postgres n'est tentée : l'enqueue est best-effort, et
l'application canonique est idempotente (hash de contenu + ``enregistrer_boucle``).
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
from datetime import datetime, timedelta, timezone
import logging
import uuid
from typing import Any

from meridian.application import pont_canonique as pont

__all__ = [
    "COLLECTION",
    "DepotPontCanonique",
    "OutboxPont",
    "OutboxPontCanonique",
    "PontCanoniqueDepot",
    "PontCanoniqueMongo",
    "depuis_environnement",
    "enfiler_best_effort",
]

COLLECTION = "pont_canonique"
_ETATS_TRAITABLES = ("pending", "failed")
_MAX_ERREUR = 2000
_DEFAUT_BASE_BACKOFF = 5
_DEFAUT_BACKOFF_MAX = 3600

journal = logging.getLogger("meridian.pont_canonique.mongo")


def _instant(valeur: Any = None) -> str:
    if valeur is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, datetime):
        return valeur.astimezone(timezone.utc).isoformat(timespec="seconds")
    texte = str(valeur).strip()
    if not texte:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return texte


def _apres(instant: str, secondes: int) -> str:
    base = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    return (base + timedelta(seconds=int(secondes))).isoformat(timespec="seconds")


def _avant_ou_egal(gauche: str, droite: str) -> bool:
    try:
        return (datetime.fromisoformat(str(gauche).replace("Z", "+00:00"))
                <= datetime.fromisoformat(str(droite).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return str(gauche) <= str(droite)


class DepotPontCanonique:
    """Adaptateur Mongo de l'outbox ``pont_canonique`` (API async compatible Motor)."""

    def __init__(self, collection, *, horloge=None):
        if collection is None:
            raise ValueError("collection pont_canonique obligatoire")
        self.collection = collection
        self._horloge = horloge or _instant

    def _maintenant(self) -> str:
        return _instant(self._horloge())

    async def enfiler(self, evenement: Mapping[str, Any]) -> dict[str, Any]:
        """Insère l'événement s'il n'existe pas ; ne touche jamais un document existant."""
        if not isinstance(evenement, Mapping):
            raise pont.PontInvalide("événement attendu")
        document = copy.deepcopy(dict(evenement))
        tenant = pont.normaliser_tenant(document.get("tenant_id"))
        document["tenant_id"] = tenant
        operation = pont.normaliser_operation(document.get("operation"))
        document["operation"] = operation
        canonical_id = pont._texte(document.get("canonical_id"))
        source_event_id = document.get("source_event_id")
        if not canonical_id:
            identifiants = document.get("canonical_ids") or []
            canonical_id = pont._texte(identifiants[0]) if identifiants else ""
        if not canonical_id:
            raise pont.PontInvalide("canonical_id ou canonical_ids obligatoire")
        document["canonical_id"] = canonical_id
        document.setdefault("canonical_ids", [canonical_id])
        identifiants = document["canonical_ids"]
        if isinstance(identifiants, str):
            identifiants = [identifiants]
        elif not isinstance(identifiants, (list, tuple, set, frozenset)):
            identifiants = [identifiants]
        document["canonical_ids"] = [pont._texte(identifiant)
                                     for identifiant in identifiants
                                     if pont._texte(identifiant)]
        if not isinstance(document.get("payload"), Mapping):
            raise pont.PontInvalide("payload : objet attendu")
        document["payload"] = pont.assainir(document["payload"])
        document["source"] = pont.assainir(document.get("source") or {})
        document["_id"] = pont._texte(document.get("_id")) or pont.identifiant_evenement(
            tenant, operation, canonical_id, source_event_id)
        document.setdefault("source_event_id", pont._texte(source_event_id))
        instant = _instant(document.get("cree_le") or self._maintenant())
        document["cree_le"] = instant
        document["maj_le"] = instant
        # Un enqueue crée toujours un événement neuf ; un document existant n'est jamais réécrit.
        document["etat"] = "pending"
        document["tentatives"] = 0
        document["prochaine_tentative"] = None
        document["derniere_erreur"] = None
        document["locked_until"] = None
        document["lock_token"] = None
        document["fencing_token"] = 0
        document["hash"] = pont.hash_contenu(document["payload"])

        resultat = await self.collection.update_one(
            {"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True)
        cree = bool(getattr(resultat, "upserted_id", None)) or (
            int(getattr(resultat, "matched_count", 0) or 0) == 0)
        return {"id": document["_id"], "cree": cree, "document": document}

    async def enfiler_best_effort(self, evenement: Mapping[str, Any]) -> dict[str, Any] | None:
        """Variante pour les routes legacy : une panne Mongo ne casse jamais l'écriture métier."""
        try:
            return await self.enfiler(evenement)
        except Exception:  # noqa: BLE001 - best-effort explicite
            journal.exception("pont : enqueue best-effort en échec ; le legacy continue")
            return None

    async def reclamer(self, worker_id: str, *, bail_secondes: int = 60,
                       maintenant: Any = None) -> dict[str, Any] | None:
        """Réclame atomiquement **un** événement prêt, avec bail et fencing."""
        evenements = await self.reclamer_lot(
            worker_id, limite=1, bail_secondes=bail_secondes, maintenant=maintenant)
        return evenements[0] if evenements else None

    async def reclamer_lot(self, worker_id: str, *, limite: int = 1,
                           bail_secondes: int = 60,
                           maintenant: Any = None) -> list[dict[str, Any]]:
        """Réclame atomiquement jusqu'à ``limite`` événements prêts, avec bail et fencing."""
        if isinstance(limite, bool):
            raise ValueError("limite doit être un entier positif")
        borne = max(1, min(int(limite), 100))
        bail = max(1, int(bail_secondes))
        instant = _instant(maintenant or self._maintenant())
        evenements: list[dict[str, Any]] = []
        for _ in range(borne):
            jeton = f"{pont._texte(worker_id) or 'worker'}:{uuid.uuid4().hex}"
            filtre = {
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "$and": [
                    {"$or": [
                        {"prochaine_tentative": None},
                        {"prochaine_tentative": {"$lte": instant}},
                    ]},
                    {"$or": [
                        {"locked_until": None},
                        {"locked_until": {"$lte": instant}},
                    ]},
                ],
            }
            modification = {
                "$set": {
                    "etat": "pending",
                    "locked_until": _apres(instant, bail),
                    "lock_token": jeton,
                    "maj_le": instant,
                },
                "$inc": {"fencing_token": 1},
            }
            document = await self.collection.find_one_and_update(
                filtre, modification,
                sort=[("prochaine_tentative", 1), ("cree_le", 1)],
                return_document=True,
            )
            if document is None:
                break
            evenements.append(document)
        return evenements

    async def terminer(self, identifiant: str, lock_token: str, *,
                       canonical_ids: Any = None, resultat: Any = None,
                       maintenant: Any = None) -> bool:
        """Marque ``done`` uniquement si le worker détient encore le bail."""
        instant = _instant(maintenant or self._maintenant())
        champs: dict[str, Any] = {
            "etat": "done",
            "locked_until": None,
            "lock_token": None,
            "maj_le": instant,
        }
        if canonical_ids is not None:
            valeurs = ([canonical_ids] if isinstance(canonical_ids, str)
                       else list(canonical_ids))
            champs["canonical_ids"] = [pont._texte(valeur) for valeur in valeurs]
        if resultat is not None:
            champs["resultat"] = pont.assainir(resultat)
        resultat_maj = await self.collection.update_one(
            {
                "_id": pont._texte(identifiant),
                "lock_token": pont._texte(lock_token),
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "locked_until": {"$gt": instant},
            },
            {"$set": champs},
        )
        return int(getattr(resultat_maj, "matched_count", 0) or 0) == 1

    async def echouer(self, identifiant: str, lock_token: str, erreur: Any, *,
                      base: int = _DEFAUT_BASE_BACKOFF,
                      maximum: int = _DEFAUT_BACKOFF_MAX,
                      maintenant: Any = None) -> bool:
        """Marque ``failed``, incrémente les tentatives et programme un backoff borné."""
        instant = _instant(maintenant or self._maintenant())
        document = await self.collection.find_one({"_id": pont._texte(identifiant)})
        if document is None:
            return False
        if document.get("etat") == "done":
            return False
        if pont._texte(document.get("lock_token")) != pont._texte(lock_token):
            return False
        bail = pont._texte(document.get("locked_until"))
        if bail and _avant_ou_egal(bail, instant):
            return False
        tentatives = int(document.get("tentatives") or 0) + 1
        delai = pont.backoff_secondes(tentatives, base=base, maximum=maximum)
        message = pont._texte(erreur)[:_MAX_ERREUR] or "erreur inconnue"
        resultat = await self.collection.update_one(
            {
                "_id": pont._texte(identifiant),
                "lock_token": pont._texte(lock_token),
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "locked_until": {"$gt": instant},
            },
            {
                "$inc": {"tentatives": 1},
                "$set": {
                    "etat": "failed",
                    "derniere_erreur": message,
                    "prochaine_tentative": _apres(instant, delai),
                    "locked_until": None,
                    "lock_token": None,
                    "maj_le": instant,
                },
            },
        )
        return int(getattr(resultat, "matched_count", 0) or 0) == 1

    async def reprendre_expires(self, *, maintenant: Any = None) -> int:
        """Rend disponibles les baux expirés ; n'exécute jamais le travail et ne touche pas ``done``."""
        instant = _instant(maintenant or self._maintenant())
        resultat = await self.collection.update_many(
            {
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "locked_until": {"$lte": instant},
                "lock_token": {"$ne": None},
            },
            {"$set": {"locked_until": None, "lock_token": None, "maj_le": instant}},
        )
        return int(getattr(resultat, "matched_count", 0) or 0)

    async def statistiques(self, *, maintenant: Any = None) -> dict[str, Any]:
        """Compte les événements en attente et l'âge du plus ancien (métriques worker)."""
        instant = _instant(maintenant or self._maintenant())
        pending = int(await self.collection.count_documents({"etat": "pending"}))
        failed = int(await self.collection.count_documents({"etat": "failed"}))
        plus_ancien = await self.collection.find(
            {"etat": {"$in": list(_ETATS_TRAITABLES)}}).sort("cree_le", 1).limit(1).to_list(1)
        lag = 0.0
        if plus_ancien:
            cree = pont._texte(plus_ancien[0].get("cree_le"))
            try:
                base = datetime.fromisoformat(cree.replace("Z", "+00:00"))
                actuel = datetime.fromisoformat(instant.replace("Z", "+00:00"))
                lag = max(0.0, (actuel - base).total_seconds())
            except ValueError:
                lag = 0.0
        return {
            "pont_events_pending": pending,
            "pont_events_failed": failed,
            "pont_lag_seconds": lag,
        }

    async def lire(self, identifiant: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": pont._texte(identifiant)})

    # Alias anglais courts, pour les appelants qui nomment le contrat outbox.
    enqueue = enfiler
    claim = reclamer
    claim_lot = reclamer_lot
    complete = terminer
    fail = echouer


OutboxPontCanonique = DepotPontCanonique
PontCanoniqueMongo = DepotPontCanonique
PontCanoniqueDepot = DepotPontCanonique
OutboxPont = DepotPontCanonique


def depuis_environnement(mongo_client, base: str | None = None) -> DepotPontCanonique:
    """Ouvre la collection depuis un client Motor/AsyncIOMotorClient injecté."""
    base = base or "meridian_db"
    return DepotPontCanonique(mongo_client[base][COLLECTION])


async def enfiler_best_effort(collection, evenement: Mapping[str, Any],
                              *, horloge=None) -> dict[str, Any] | None:
    """Enqueue best-effort sans lever : utilisé par les routes legacy C2/C3."""
    return await DepotPontCanonique(collection, horloge=horloge).enfiler_best_effort(evenement)
