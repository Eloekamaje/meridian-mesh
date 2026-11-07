"""Dépôts Mongo de la mesure automatique : observations, checkpoints et rejets.

Le worker lit une collection dédiée, ``mesure_auto_observations``. Chaque document porte
explicitement son ``tenant_id`` normalisé, un ``id`` stable et un ``maj_le`` (date d'ingestion)
qui sert de curseur. Le curseur canonique est ``(maj_le UTC, sequence, id)`` : ``sequence`` est
optionnelle, avec ``_id`` Mongo comme tie-breaker si elle manque.

Les filtres gèrent le **type bracketing** : un ``maj_le`` stocké en BSON Date et un ``maj_le``
stocké en chaîne ISO sont tous deux lus, puis ramenés au même curseur UTC. Une borne basse
conservatrice (courant - 1 jour) permet de ne pas perdre une chaîne portant un offset non-UTC ;
le tri final et le filtre précis se font en Python.

Aucun accès Postgres : les Outcomes sont seulement enfilés dans l'outbox ``pont_canonique``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from typing import Any

from meridian.application import pont_canonique as pont

__all__ = [
    "CHECKPOINTS",
    "OBSERVATIONS",
    "REJETS",
    "SCHEMA_OBSERVATION",
    "CurseurObservation",
    "DepotCheckpointsMesure",
    "DepotObservationsMesure",
    "DepotRejetsMesure",
    "canoniser_document",
    "canoniser_instant",
    "curseur_document",
]

OBSERVATIONS = "mesure_auto_observations"
CHECKPOINTS = "mesure_auto_checkpoints"
REJETS = "mesure_auto_rejets"
_MAX_LOT = 1000
_BORNE_BASSE = timedelta(days=1)

# Validateur indicatif (non appliqué par défaut : le repo n'a pas de convention collMod).
# Il peut être posé par l'exploitation avec ``DepotObservationsMesure.assurer_validateur``.
SCHEMA_OBSERVATION = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["tenant_id", "id", "maj_le", "quand"],
        "properties": {
            "tenant_id": {"bsonType": "string", "minLength": 1},
            "id": {"bsonType": "string", "minLength": 1},
            "maj_le": {"bsonType": ["string", "date"]},
            "quand": {"bsonType": ["string", "date"]},
            "sequence": {"bsonType": ["string", "int", "long"]},
            "initiative_id": {"bsonType": "string"},
            "decision_id": {"bsonType": "string"},
            "metrique": {"bsonType": "string"},
            "periode": {"bsonType": "string"},
            "attendu": {},
            "observe": {},
            "effets_secondaires": {"bsonType": "array"},
        },
    }
}


@dataclass(frozen=True, order=True)
class CurseurObservation:
    """Position monotone : date d'ingestion UTC, tie-breaker producteur, identifiant stable."""

    maj_le: str
    sequence: str = ""
    id: str = ""

    def document(self) -> dict[str, str]:
        return asdict(self)


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def canoniser_instant(valeur: Any) -> str | None:
    """ISO UTC à la microseconde, depuis une chaîne (offset accepté) ou un BSON Date."""
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        horodatage = valeur
    elif isinstance(valeur, date):
        horodatage = datetime.combine(valeur, datetime.min.time())
    else:
        texte = _texte(valeur)
        if not texte:
            return None
        try:
            horodatage = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError:
            return None
    if horodatage.tzinfo is None:
        horodatage = horodatage.replace(tzinfo=timezone.utc)
    return horodatage.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _instant_datetime(valeur: Any) -> datetime | None:
    instant = canoniser_instant(valeur)
    if instant is None:
        return None
    return datetime.fromisoformat(instant)


def canoniser_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Ramène tenant, id, dates et séquence au contrat canonique, sans inventer de valeur."""
    propre = dict(document)
    tenant = _texte(propre.get("tenant_id"))
    if tenant:
        try:
            propre["tenant_id"] = pont.normaliser_tenant(tenant)
        except pont.PontInvalide:
            propre["tenant_id"] = tenant
    identifiant = _texte(propre.get("id"))
    if identifiant:
        propre["id"] = identifiant
    for champ in ("maj_le", "quand", "observe_le", "mesure_le"):
        if champ in propre:
            instant = canoniser_instant(propre.get(champ))
            if instant is not None:
                propre[champ] = instant
    if "sequence" in propre and propre.get("sequence") is not None:
        propre["sequence"] = _texte(propre.get("sequence"))
    if "_id" in propre and propre.get("_id") is not None:
        propre["_id"] = _texte(propre.get("_id"))
    return propre


def curseur_document(document: Mapping[str, Any]) -> CurseurObservation:
    """Curseur d'un document ; lève ``ValueError`` si ``maj_le`` ou ``id`` manque."""
    maj_le = canoniser_instant(document.get("maj_le"))
    identifiant = _texte(document.get("id"))
    if maj_le is None:
        raise ValueError("maj_le absent ou illisible")
    if not identifiant:
        raise ValueError("id d'observation absent")
    sequence = _texte(document.get("sequence")) or _texte(document.get("_id"))
    return CurseurObservation(maj_le=maj_le, sequence=sequence, id=identifiant)


class DepotObservationsMesure:
    """Lecture incrémentale des observations d'un tenant, avec type bracketing."""

    def __init__(self, collection):
        if collection is None:
            raise ValueError("collection mesure_auto_observations obligatoire")
        self.collection = collection

    def _seuil(self, curseur: CurseurObservation | None) -> datetime | None:
        if curseur is None:
            return None
        instant = _instant_datetime(curseur.maj_le)
        return instant - _BORNE_BASSE if instant is not None else None

    def _filtres(self, tenant: str, curseur: CurseurObservation | None) -> list[dict[str, Any]]:
        tenant_normalise = pont.normaliser_tenant(tenant)
        seuil = self._seuil(curseur)
        base = {
            "tenant_id": tenant_normalise,
            "id": {"$exists": True, "$type": "string"},
        }
        filtres: list[dict[str, Any]] = []
        for type_mongo in ("string", "date"):
            condition: dict[str, Any] = {"$exists": True, "$type": type_mongo}
            if seuil is not None:
                condition["$gte"] = (seuil.isoformat(timespec="microseconds")
                                     if type_mongo == "string" else seuil)
            filtres.append({**base, "maj_le": condition})
        return filtres

    async def lister_apres(self, tenant: str, curseur: CurseurObservation | None = None,
                           limite: int = 100) -> list[dict[str, Any]]:
        borne = max(1, min(int(limite), _MAX_LOT))
        # On lit les deux brackets et on fusionne : le tri Mongo entre Date et String n'est pas
        # le tri temporel. Chaque bracket fournit au plus ``scan`` documents triés.
        scan = min(max(borne * 4, borne + 1), _MAX_LOT)
        documents: list[dict[str, Any]] = []
        for filtre in self._filtres(tenant, curseur):
            cursor = self.collection.find(filtre)
            cursor = cursor.sort([("maj_le", 1), ("_id", 1)]).limit(scan)
            documents.extend(await cursor.to_list(scan))
        par_id: dict[str, tuple[CurseurObservation, dict[str, Any]]] = {}
        for document in documents:
            if not isinstance(document, Mapping):
                continue
            propre = canoniser_document(document)
            identifiant = _texte(propre.get("id"))
            if not identifiant:
                continue
            try:
                position = curseur_document(propre)
            except ValueError:
                continue
            if curseur is not None and position <= curseur:
                continue
            existant = par_id.get(identifiant)
            if existant is None or position > existant[0]:
                par_id[identifiant] = (position, propre)
        retenus = sorted(par_id.values(), key=lambda paire: paire[0])
        return [document for _position, document in retenus[:borne]]

    async def compter_non_conformes(self, tenant: str) -> int:
        """Compte les documents sans ``id`` string ou sans ``maj_le`` string/date."""
        filtre = {
            "tenant_id": pont.normaliser_tenant(tenant),
            "$or": [
                {"id": {"$exists": False}},
                {"id": ""},
                {"id": {"$not": {"$type": "string"}}},
                {"maj_le": {"$exists": False}},
                {"$and": [
                    {"maj_le": {"$not": {"$type": "string"}}},
                    {"maj_le": {"$not": {"$type": "date"}}},
                ]},
            ],
        }
        return int(await self.collection.count_documents(filtre))

    async def assurer_index(self) -> list[Any]:
        resultats = []
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), ("maj_le", 1), ("sequence", 1), ("id", 1)],
            name="mesure_auto_observations_curseur",
        ))
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), ("id", 1)],
            name="mesure_auto_observations_tenant_id_unique",
            unique=True,
        ))
        return resultats

    async def assurer_validateur(self) -> bool:
        """Pose le validateur JSON Schema si la collection expose sa base (best-effort)."""
        database = getattr(self.collection, "database", None)
        nom = _texte(getattr(self.collection, "name", ""))
        if database is None or not nom:
            return False
        try:
            await database.command({
                "collMod": nom,
                "validator": SCHEMA_OBSERVATION,
                "validationLevel": "moderate",
                "validationAction": "warn",
            })
            return True
        except Exception:  # noqa: BLE001 - le validateur est une aide d'exploitation
            return False


class DepotCheckpointsMesure:
    """Un checkpoint par tenant, avancé par CAS : un worker lent ne régresse jamais le curseur."""

    def __init__(self, collection, *, horloge=None):
        if collection is None:
            raise ValueError("collection mesure_auto_checkpoints obligatoire")
        self.collection = collection
        self._horloge = horloge or (lambda: datetime.now(timezone.utc).isoformat(
            timespec="seconds"))

    async def lire(self, tenant: str) -> CurseurObservation | None:
        tenant_normalise = pont.normaliser_tenant(tenant)
        document = await self.collection.find_one({"_id": tenant_normalise})
        if not isinstance(document, Mapping):
            return None
        maj_le = canoniser_instant(document.get("dernier_maj_le"))
        identifiant = _texte(document.get("dernier_id"))
        if maj_le is None or not identifiant:
            return None
        return CurseurObservation(
            maj_le=maj_le,
            sequence=_texte(document.get("dernier_sequence")),
            id=identifiant,
        )

    def _document(self, tenant: str, curseur: CurseurObservation) -> dict[str, Any]:
        return {
            "tenant_id": tenant,
            "dernier_maj_le": curseur.maj_le,
            "dernier_sequence": curseur.sequence,
            "dernier_id": curseur.id,
            "maj_le": canoniser_instant(self._horloge()),
        }

    def _filtre_cas(self, tenant: str, actuel: CurseurObservation | None) -> dict[str, Any]:
        if actuel is None:
            return {"_id": tenant}
        filtre: dict[str, Any] = {
            "_id": tenant,
            "dernier_maj_le": actuel.maj_le,
            "dernier_id": actuel.id,
        }
        if actuel.sequence:
            filtre["dernier_sequence"] = actuel.sequence
        else:
            filtre["$or"] = [
                {"dernier_sequence": {"$exists": False}},
                {"dernier_sequence": ""},
            ]
        return filtre

    async def ecrire(self, tenant: str, curseur: CurseurObservation) -> CurseurObservation:
        tenant_normalise = pont.normaliser_tenant(tenant)
        maj_le = canoniser_instant(curseur.maj_le)
        if maj_le is None:
            raise ValueError("maj_le obligatoire et lisible pour avancer le checkpoint")
        if not _texte(curseur.id):
            raise ValueError("id d'observation obligatoire pour avancer le checkpoint")
        position = CurseurObservation(
            maj_le=maj_le, sequence=_texte(curseur.sequence), id=_texte(curseur.id))
        document = self._document(tenant_normalise, position)
        for _ in range(3):
            actuel = await self.lire(tenant_normalise)
            if actuel is not None and position <= actuel:
                return actuel
            if actuel is None:
                # Insertion CAS : si un autre worker a inséré entre-temps, l'index unique
                # sur `_id` lève et on relit son curseur au tour suivant.
                try:
                    resultat = await self.collection.update_one(
                        {"_id": tenant_normalise, "dernier_maj_le": {"$exists": False}},
                        {"$set": document}, upsert=True)
                except Exception:  # noqa: BLE001 - course d'insertion : relire
                    continue
                if (int(getattr(resultat, "matched_count", 0) or 0) > 0
                        or getattr(resultat, "upserted_id", None) is not None):
                    return position
                continue
            filtre = self._filtre_cas(tenant_normalise, actuel)
            resultat = await self.collection.update_one(
                filtre, {"$set": document}, upsert=False)
            if int(getattr(resultat, "matched_count", 0) or 0) > 0:
                return position
        actuel = await self.lire(tenant_normalise)
        return actuel or position


class DepotRejetsMesure:
    """Dead-letter durable : une correction permanente ne bloque jamais le tenant.

    Le compteur de tentatives permet de borner les erreurs transitoires ; au-delà de
    ``tentatives_max``, l'observation passe en ``dead`` et le worker peut avancer.
    """

    def __init__(self, collection, *, horloge=None):
        if collection is None:
            raise ValueError("collection mesure_auto_rejets obligatoire")
        self.collection = collection
        self._horloge = horloge or (lambda: datetime.now(timezone.utc).isoformat(
            timespec="seconds"))

    def _cle(self, tenant: str, document: Mapping[str, Any]) -> str:
        identifiant = _texte(document.get("id")) or "sans-id"
        empreinte = pont.hash_contenu(dict(document))[:16]
        graine = f"{tenant}|{identifiant}|{empreinte}"
        return hashlib.sha256(graine.encode("utf-8")).hexdigest()[:32]

    async def enregistrer(self, tenant: str, document: Mapping[str, Any], raison: str, *,
                          permanent: bool, tentatives_max: int = 5) -> bool:
        """Enregistre/incrémente un rejet ; rend ``True`` si l'observation est dead-letterée."""
        tenant_normalise = pont.normaliser_tenant(tenant)
        cle = self._cle(tenant_normalise, document)
        instant = canoniser_instant(self._horloge())
        await self.collection.update_one(
            {"_id": cle},
            {
                "$setOnInsert": {
                    "tenant_id": tenant_normalise,
                    "observation_id": _texte(document.get("id")) or None,
                    "cree_le": instant,
                    "tentatives": 0,
                },
                "$set": {
                    "derniere_raison": _texte(raison)[:2000],
                    "permanent": bool(permanent),
                    "maj_le": instant,
                },
                "$inc": {"tentatives": 1},
            },
            upsert=True,
        )
        document_rejet = await self.collection.find_one({"_id": cle}) or {}
        tentatives = int(document_rejet.get("tentatives") or 1)
        etat = "dead" if permanent or tentatives >= max(1, int(tentatives_max)) else "retry"
        await self.collection.update_one({"_id": cle}, {"$set": {"etat": etat}})
        return etat == "dead"

    async def assurer_index(self) -> list[Any]:
        return [await self.collection.create_index(
            [("tenant_id", 1), ("etat", 1), ("maj_le", 1)],
            name="mesure_auto_rejets_tenant_etat",
        )]

    async def compter(self, tenant: str, etat: str = "dead") -> int:
        return int(await self.collection.count_documents(
            {"tenant_id": pont.normaliser_tenant(tenant), "etat": etat}))
