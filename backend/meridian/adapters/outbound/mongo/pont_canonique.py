"""Outbox Mongo du pont Travail → canonique.

La collection ``pont_canonique`` porte les événements en attente. L'écriture est idempotente :
l'identifiant est déterministe et l'insertion utilise ``$setOnInsert``, jamais un remplacement.
Un worker réclame **un** événement à la fois avec un bail et un jeton de fencing ; seul le
détenteur du jeton peut le terminer ou l'échouer. Un bail expiré est repris par un autre worker,
et le jeton périmé du premier ne peut plus écraser l'état.

Chaque événement est authentifié par HMAC-SHA256 (`PONT_KEY`) et son payload est vérifié contre
`source.hash`. L'enqueue est best-effort pour les routes legacy : une panne Mongo ne casse pas
l'écriture métier.

Déploiement : le producteur (API legacy) doit utiliser un utilisateur Mongo dédié, limité à
`insert`/`update` sur `pont_canonique` (pas de droits sur les collections canoniques ni sur les
autres bases). Le worker utilise un utilisateur distinct en lecture/claim sur la même collection.
`objets.upsert` est réservé à un producteur interne signé (`source.collection=pont_interne`,
`source.interne=true`) et n'est jamais exposé aux routes legacy.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
from datetime import datetime, timedelta, timezone
import logging
import uuid
from typing import Any

from meridian.application import pont_canonique as pont

try:  # pymongo est une dépendance de production ; les tests unitaires peuvent s'en passer.
    from pymongo.errors import DuplicateKeyError as _DuplicateKeyError
except ImportError:  # pragma: no cover
    _DuplicateKeyError = ()  # type: ignore[assignment]

__all__ = [
    "COLLECTION",
    "DepotPontCanonique",
    "OutboxPont",
    "OutboxPontCanonique",
    "PontCanoniqueDepot",
    "PontCanoniqueMongo",
    "assurer_index",
    "depuis_environnement",
    "enfiler_best_effort",
]

COLLECTION = "pont_canonique"
_ETATS_TRAITABLES = ("pending", "failed")
_MAX_ERREUR = 2000
_DEFAUT_BASE_BACKOFF = 5
_DEFAUT_BACKOFF_MAX = 3600
_DEFAUT_TENTATIVES_MAX = 10

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


def _liste_tenants(tenants: Any) -> list[str]:
    if tenants is None:
        return []
    if isinstance(tenants, str):
        tenants = [tenants]
    return [pont.normaliser_tenant(tenant) for tenant in tenants if pont._texte(tenant)]


class DepotPontCanonique:
    """Adaptateur Mongo de l'outbox ``pont_canonique`` (API async compatible Motor)."""

    def __init__(self, collection, *, horloge=None, cle=None, cle_interne=None,
                 tentatives_max: int = _DEFAUT_TENTATIVES_MAX):
        if collection is None:
            raise ValueError("collection pont_canonique obligatoire")
        self.collection = collection
        self._horloge = horloge or _instant
        self.cle = cle
        self.cle_interne = cle_interne
        self.tentatives_max = max(1, int(tentatives_max))

    def _maintenant(self) -> str:
        return _instant(self._horloge())

    def _cle_evenement(self, document: Mapping[str, Any]):
        return pont.cle_pour_evenement(document, self.cle, self.cle_interne)

    def _verifier_authenticite(self, document: Mapping[str, Any]) -> None:
        pont.verifier_evenement(document, self._cle_evenement(document))

    def _verifier_source(self, document: Mapping[str, Any], operation: str,
                         canonical_id: str) -> None:
        pont.verifier_source_evenement(document)

    def _normaliser(self, evenement: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(evenement, Mapping):
            raise pont.PontInvalide("événement attendu")
        self._verifier_authenticite(evenement)
        document = copy.deepcopy(dict(evenement))
        tenant = pont.normaliser_tenant(document.get("tenant_id"))
        document["tenant_id"] = tenant
        operation = pont.normaliser_operation(document.get("operation"))
        document["operation"] = operation
        canonical_id = pont._texte(document.get("canonical_id"))
        identifiants = document.get("canonical_ids") or []
        if isinstance(identifiants, str):
            identifiants = [identifiants]
        identifiants = [pont._texte(identifiant) for identifiant in identifiants
                        if pont._texte(identifiant)]
        if not canonical_id and identifiants:
            canonical_id = identifiants[0]
        if not canonical_id:
            raise pont.PontInvalide("canonical_id ou canonical_ids obligatoire")
        document["canonical_id"] = canonical_id
        document["canonical_ids"] = identifiants or [canonical_id]
        if not isinstance(document.get("payload"), Mapping):
            raise pont.PontInvalide("payload : objet attendu")
        document["payload"] = pont.assainir(document["payload"])
        document["source"] = pont.assainir(document.get("source") or {})
        document["source_event_id"] = pont._texte(document.get("source_event_id"))
        identifiant = pont.identifiant_evenement(
            tenant, operation, canonical_id, document["source_event_id"])
        fourni = pont._texte(document.get("_id"))
        if fourni and fourni != identifiant:
            raise pont.PontInvalide(
                f"_id {fourni!r} non conforme à la clé d'idempotence {identifiant!r}")
        document["_id"] = identifiant
        hash_fourni = pont._texte(document.get("hash"))
        calculé_source = pont.hash_contenu(document["payload"])
        if hash_fourni and hash_fourni != calculé_source:
            raise pont.PontInvalide("hash d'événement divergent du payload")
        document["hash"] = calculé_source
        if pont._texte(document["source"].get("hash")) not in ("", calculé_source):
            raise pont.PontInvalide("source.hash divergent du payload")
        if not pont._iso(document.get("source_maj_le")):
            raise pont.PontInvalide("source_maj_le obligatoire et ISO")
        self._verifier_source(document, operation, canonical_id)
        instant = _instant(document.get("cree_le") or self._maintenant())
        document["cree_le"] = instant
        document["maj_le"] = instant
        document["etat"] = "pending"
        document["tentatives"] = 0
        document["disponible_le"] = _instant(document.get("disponible_le") or instant)
        document["prochaine_tentative"] = None
        document["derniere_erreur"] = None
        document["locked_until"] = None
        document["lock_token"] = None
        document["fencing_token"] = 0
        document.pop("dead_le", None)
        document.pop("done_le", None)
        # Le document normalisé est re-signé : le worker vérifie exactement ce qui est stocké.
        return pont.signer_evenement(document, self._cle_evenement(document))

    async def _verifier_collision(self, document: Mapping[str, Any]) -> None:
        existant = await self.collection.find_one({"_id": document["_id"]})
        if existant is None:
            return
        hash_existant = pont._texte(existant.get("hash"))
        if not hash_existant:
            hash_existant = pont.hash_contenu(existant.get("payload"))
        if hash_existant != document["hash"]:
            raise pont.PontInvalide(
                f"collision d'idempotence sur _id {document['_id']!r} : "
                "le document existant a un contenu différent")

    async def enfiler(self, evenement: Mapping[str, Any]) -> dict[str, Any]:
        """Insère l'événement s'il n'existe pas ; ne touche jamais un document existant."""
        document = self._normaliser(evenement)
        try:
            resultat = await self.collection.update_one(
                {"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True)
        except _DuplicateKeyError:  # course entre deux producteurs : l'idempotence gagne
            await self._verifier_collision(document)
            return {"id": document["_id"], "cree": False, "document": document}
        cree = bool(getattr(resultat, "upserted_id", None)) or (
            int(getattr(resultat, "matched_count", 0) or 0) == 0)
        if not cree:
            await self._verifier_collision(document)
        return {"id": document["_id"], "cree": cree, "document": document}

    async def enfiler_best_effort(self, evenement: Mapping[str, Any]) -> dict[str, Any] | None:
        """Variante pour les routes legacy : une panne Mongo ne casse jamais l'écriture métier."""
        try:
            return await self.enfiler(evenement)
        except Exception:  # noqa: BLE001 - best-effort explicite
            journal.exception("pont : enqueue best-effort en échec ; le legacy continue")
            return None

    async def reclamer(self, worker_id: str, *, bail_secondes: int = 60,
                       maintenant: Any = None, tenants: Any = None) -> dict[str, Any] | None:
        """Réclame atomiquement **un** événement prêt, avec bail et fencing."""
        evenements = await self.reclamer_lot(
            worker_id, limite=1, bail_secondes=bail_secondes,
            maintenant=maintenant, tenants=tenants)
        return evenements[0] if evenements else None

    async def reclamer_lot(self, worker_id: str, *, limite: int = 1,
                           bail_secondes: int = 60, maintenant: Any = None,
                           tenants: Any = None) -> list[dict[str, Any]]:
        """Réclame atomiquement jusqu'à ``limite`` événements prêts, avec bail et fencing."""
        if isinstance(limite, bool):
            raise ValueError("limite doit être un entier positif")
        borne = max(1, min(int(limite), 100))
        bail = max(1, int(bail_secondes))
        instant = _instant(maintenant or self._maintenant())
        selection_tenants = _liste_tenants(tenants)
        evenements: list[dict[str, Any]] = []
        for _ in range(borne):
            jeton = f"{pont._texte(worker_id) or 'worker'}:{uuid.uuid4().hex}"
            filtre: dict[str, Any] = {
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "$and": [
                    {"$or": [
                        {"disponible_le": {"$exists": False}},
                        {"disponible_le": None},
                        {"disponible_le": {"$lte": instant}},
                    ]},
                    {"$or": [
                        {"locked_until": None},
                        {"locked_until": {"$exists": False}},
                        {"locked_until": {"$lte": instant}},
                    ]},
                ],
            }
            if selection_tenants:
                filtre["tenant_id"] = {"$in": selection_tenants}
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
                sort=[("disponible_le", 1), ("cree_le", 1)],
                return_document=True,
            )
            if document is None:
                break
            evenements.append(document)
        return evenements

    async def verifier_bail(self, identifiant: str, lock_token: str, *,
                            maintenant: Any = None) -> bool:
        """Vérifie juste avant l'application que ce worker détient encore le bail."""
        instant = _instant(maintenant or self._maintenant())
        document = await self.collection.find_one({"_id": pont._texte(identifiant)})
        if document is None:
            return False
        if document.get("etat") not in _ETATS_TRAITABLES:
            return False
        if pont._texte(document.get("lock_token")) != pont._texte(lock_token):
            return False
        bail = pont._texte(document.get("locked_until"))
        return bool(bail and not _avant_ou_egal(bail, instant))

    async def terminer(self, identifiant: str, lock_token: str, *,
                       canonical_ids: Any = None, resultat: Any = None,
                       maintenant: Any = None) -> bool:
        """Marque ``done`` uniquement si le worker détient encore le bail."""
        instant = _instant(maintenant or self._maintenant())
        champs: dict[str, Any] = {
            "etat": "done",
            "done_le": instant,
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
                      permanent: bool = False, jitter: float = 0.2,
                      maintenant: Any = None) -> bool:
        """Marque ``failed`` (transitoire) ou ``dead`` (permanent), avec backoff borné."""
        instant = _instant(maintenant or self._maintenant())
        document = await self.collection.find_one({"_id": pont._texte(identifiant)})
        if document is None or document.get("etat") == "done":
            return False
        if pont._texte(document.get("lock_token")) != pont._texte(lock_token):
            return False
        bail = pont._texte(document.get("locked_until"))
        if bail and _avant_ou_egal(bail, instant):
            return False
        tentatives = int(document.get("tentatives") or 0) + 1
        message = pont._texte(erreur)[:_MAX_ERREUR] or "erreur inconnue"
        terminal = bool(permanent or tentatives >= self.tentatives_max)
        delai = pont.backoff_secondes(tentatives, base=base, maximum=maximum,
                                      jitter=jitter)
        champs: dict[str, Any] = {
            "derniere_erreur": message,
            "locked_until": None,
            "lock_token": None,
            "maj_le": instant,
        }
        if terminal:
            champs.update({
                "etat": "dead",
                "dead_le": instant,
                "disponible_le": None,
                "prochaine_tentative": None,
            })
        else:
            disponibilité = _apres(instant, delai)
            champs.update({
                "etat": "failed",
                "disponible_le": disponibilité,
                "prochaine_tentative": disponibilité,
            })
        resultat = await self.collection.update_one(
            {
                "_id": pont._texte(identifiant),
                "lock_token": pont._texte(lock_token),
                "etat": {"$in": list(_ETATS_TRAITABLES)},
                "locked_until": {"$gt": instant},
            },
            {"$inc": {"tentatives": 1}, "$set": champs},
        )
        return int(getattr(resultat, "matched_count", 0) or 0) == 1

    async def requeuter(self, identifiant: str, *, maintenant: Any = None) -> bool:
        """Remet un événement ``failed``/``dead`` en file (sortie de DLQ explicite)."""
        instant = _instant(maintenant or self._maintenant())
        resultat = await self.collection.update_one(
            {"_id": pont._texte(identifiant), "etat": {"$in": ["failed", "dead"]}},
            {"$set": {
                "etat": "pending",
                "tentatives": 0,
                "disponible_le": instant,
                "prochaine_tentative": None,
                "derniere_erreur": None,
                "locked_until": None,
                "lock_token": None,
                "dead_le": None,
                "maj_le": instant,
            }},
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
        dead = int(await self.collection.count_documents({"etat": "dead"}))
        plus_ancien = await self.collection.find(
            {"etat": {"$in": list(_ETATS_TRAITABLES)}}).sort("disponible_le", 1).limit(1).to_list(1)
        lag = 0.0
        if plus_ancien:
            cree = pont._texte(plus_ancien[0].get("disponible_le")
                               or plus_ancien[0].get("cree_le"))
            try:
                base = datetime.fromisoformat(cree.replace("Z", "+00:00"))
                actuel = datetime.fromisoformat(instant.replace("Z", "+00:00"))
                lag = max(0.0, (actuel - base).total_seconds())
            except ValueError:
                lag = 0.0
        return {
            "pont_events_pending": pending,
            "pont_events_failed": failed,
            "pont_events_dead": dead,
            "pont_lag_seconds": lag,
        }

    async def assurer_index(self) -> None:
        """Index de claim et TTL des événements terminés (à appeler au démarrage)."""
        await self.collection.create_index(
            [("etat", 1), ("disponible_le", 1), ("cree_le", 1)], name="pont_a_traiter")
        await self.collection.create_index(
            [("etat", 1), ("locked_until", 1)], name="pont_baux")
        await self.collection.create_index(
            [("done_le", 1)], name="pont_done_ttl", expireAfterSeconds=7 * 24 * 3600,
            partialFilterExpression={"etat": "done"})

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


def depuis_environnement(mongo_client, base: str | None = None, *,
                         cle=None, cle_interne=None) -> DepotPontCanonique:
    """Ouvre la collection depuis un client Motor/AsyncIOMotorClient injecté."""
    base = base or "meridian_db"
    return DepotPontCanonique(
        mongo_client[base][COLLECTION], cle=cle, cle_interne=cle_interne)


async def enfiler_best_effort(collection, evenement: Mapping[str, Any],
                              *, horloge=None, cle=None,
                              cle_interne=None) -> dict[str, Any] | None:
    """Enqueue best-effort sans lever : utilisé par les routes legacy C2/C3."""
    return await DepotPontCanonique(
        collection, horloge=horloge, cle=cle,
        cle_interne=cle_interne).enfiler_best_effort(evenement)


async def assurer_index(collection) -> None:
    await DepotPontCanonique(collection).assurer_index()
