"""Dépôts Mongo de la mesure automatique : observations, checkpoints et rejets.

Le worker lit une collection dédiée, ``mesure_auto_observations``. Chaque document porte
explicitement son ``tenant_id`` normalisé, un ``id`` stable, un ``maj_le`` (date d'ingestion)
et, pour les documents récents, un champ canonique indexé ``maj_le_utc`` (BSON Date).

Le curseur canonique est ``(maj_le_utc, sequence, id)``. Les producteurs doivent écrire
``maj_le_utc`` via :func:`document_ingestion` ; les documents legacy sans ce champ passent par un
backfill borné (:meth:`DepotObservationsMesure.remplir_maj_le_utc`) et un fallback explicitement
borné. La requête principale est un **seek d'index** ``maj_le_utc > curseur`` : elle ne peut pas
être affamée par un stock de documents plus anciens.

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
    "AUDIT_LIMITE",
    "BACKFILL_LOT",
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
    "document_ingestion",
    "sequence_canonique",
]

OBSERVATIONS = "mesure_auto_observations"
CHECKPOINTS = "mesure_auto_checkpoints"
REJETS = "mesure_auto_rejets"
CHAMP_UTC = "maj_le_utc"
_MAX_LOT = 1000
_AUDIT_LIMITE = 1000
_BACKFILL_LOT = 500
AUDIT_LIMITE = _AUDIT_LIMITE
BACKFILL_LOT = _BACKFILL_LOT
_BORNE_BASSE = timedelta(days=1)

# Validateur indicatif (non appliqué par défaut : le repo n'a pas de convention collMod).
SCHEMA_OBSERVATION = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["tenant_id", "id", "maj_le", "quand"],
        "anyOf": [
            {"required": ["initiative_id"]},
            {"required": ["decision_id"]},
            {"required": ["observation"]},
        ],
        "properties": {
            "tenant_id": {"bsonType": "string", "minLength": 1},
            "id": {"bsonType": "string", "minLength": 1},
            "maj_le": {"bsonType": ["string", "date"]},
            "maj_le_utc": {"bsonType": "date"},
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
    """Position monotone : date UTC canonique, séquence producteur, identifiant stable."""

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


def _millisecondes(valeur: datetime) -> datetime:
    """BSON Date a une précision milliseconde : le curseur doit matcher exactement."""
    return valeur.replace(microsecond=(valeur.microsecond // 1000) * 1000)


def sequence_canonique(valeur: Any) -> str:
    """Tie-breaker comparable lexicographiquement.

    Les entiers (int/long Mongo) sont zéro-paddés sur 20 chiffres : ``9``, ``10`` et ``11``
    restent ordonnés ``9 < 10 < 11`` au lieu de ``"10" < "11" < "9"``. Les chaînes (ULID,
    ObjectId hex) sont conservées telles quelles.
    """
    if valeur is None or isinstance(valeur, bool):
        return _texte(valeur)
    if isinstance(valeur, int):
        return f"{valeur:020d}"
    return _texte(valeur)


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
        propre["sequence"] = sequence_canonique(propre.get("sequence"))
    if "_id" in propre and propre.get("_id") is not None:
        propre["_id"] = _texte(propre.get("_id"))
    return propre


def document_ingestion(document: Mapping[str, Any]) -> dict[str, Any]:
    """Document prêt à insérer : tenant normalisé, id string, dates UTC, ``maj_le_utc`` indexé.

    Les producteurs doivent utiliser cette fonction (ou écrire les mêmes champs) pour que la
    requête principale de lecture soit un seek d'index non affamable.
    """
    propre = canoniser_document(document)
    tenant = _texte(propre.get("tenant_id"))
    if tenant:
        propre["tenant_id"] = pont.normaliser_tenant(tenant)
    identifiant = _texte(propre.get("id"))
    if identifiant:
        propre["id"] = identifiant
    maj_le = _instant_datetime(propre.get("maj_le"))
    if maj_le is not None:
        maj_le = _millisecondes(maj_le)
        propre["maj_le"] = canoniser_instant(maj_le)
        propre[CHAMP_UTC] = maj_le
    propre["sequence"] = sequence_canonique(
        propre.get("sequence") if propre.get("sequence") is not None else propre.get("_id"))
    return propre


def curseur_document(document: Mapping[str, Any]) -> CurseurObservation:
    """Curseur d'un document ; lève ``ValueError`` si ``maj_le`` ou ``id`` manque."""
    # Le champ canonique BSON Date (milliseconde) est l'arbitre du seek ; `maj_le` reste le
    # contrat lisible pour le payload et les producteurs legacy.
    maj_le = (canoniser_instant(document.get(CHAMP_UTC))
              or canoniser_instant(document.get("maj_le")))
    identifiant = _texte(document.get("id"))
    if maj_le is None:
        raise ValueError("maj_le absent ou illisible")
    if not identifiant:
        raise ValueError("id d'observation absent")
    sequence = sequence_canonique(
        document.get("sequence") if document.get("sequence") is not None
        else document.get("_id"))
    return CurseurObservation(maj_le=maj_le, sequence=sequence, id=identifiant)


class DepotObservationsMesure:
    """Lecture incrémentale par seek d'index canonique, avec fallback legacy borné."""

    def __init__(self, collection):
        if collection is None:
            raise ValueError("collection mesure_auto_observations obligatoire")
        self.collection = collection

    def _filtre_principal(self, tenant: str,
                          curseur: CurseurObservation | None) -> dict[str, Any]:
        filtre: dict[str, Any] = {"tenant_id": pont.normaliser_tenant(tenant)}
        if curseur is None:
            filtre[CHAMP_UTC] = {"$exists": True}
            return filtre
        date_curseur = _instant_datetime(curseur.maj_le)
        if date_curseur is None:
            raise ValueError("curseur maj_le illisible")
        filtre["$or"] = [
            {CHAMP_UTC: {"$gt": date_curseur}},
            {"$and": [
                {CHAMP_UTC: date_curseur},
                {"sequence": {"$gt": curseur.sequence}},
            ]},
            {"$and": [
                {CHAMP_UTC: date_curseur},
                {"sequence": curseur.sequence},
                {"id": {"$gt": curseur.id}},
            ]},
        ]
        return filtre

    def _seuil_legacy(self, curseur: CurseurObservation | None) -> datetime | None:
        if curseur is None:
            return None
        instant = _instant_datetime(curseur.maj_le)
        return instant - _BORNE_BASSE if instant is not None else None

    def _filtres_legacy(self, tenant: str,
                        curseur: CurseurObservation | None) -> list[dict[str, Any]]:
        tenant_normalise = pont.normaliser_tenant(tenant)
        seuil = self._seuil_legacy(curseur)
        base = {
            "tenant_id": tenant_normalise,
            CHAMP_UTC: {"$exists": False},
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
        tenant_normalise = pont.normaliser_tenant(tenant)
        documents: list[dict[str, Any]] = []

        # 1. Seek d'index : les documents canoniques après le curseur, sans fenêtre glissante.
        filtre_principal = self._filtre_principal(tenant_normalise, curseur)
        cursor = self.collection.find(filtre_principal)
        cursor = cursor.sort([(CHAMP_UTC, 1), ("sequence", 1), ("id", 1)]).limit(borne)
        documents.extend(await cursor.to_list(borne))

        # 2. Fallback legacy sans `maj_le_utc` : borné, ne peut pas cacher les résultats du seek.
        for filtre in self._filtres_legacy(tenant_normalise, curseur):
            cursor = self.collection.find(filtre)
            cursor = cursor.sort([("maj_le", 1), ("_id", 1)]).limit(borne)
            documents.extend(await cursor.to_list(borne))

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

    async def remplir_maj_le_utc(self, tenant: str, limite: int = _BACKFILL_LOT) -> int:
        """Backfill borné des documents legacy : écrit ``maj_le_utc`` et la séquence canonique."""
        tenant_normalise = pont.normaliser_tenant(tenant)
        borne = max(1, min(int(limite), _MAX_LOT))
        filtre = {
            "tenant_id": tenant_normalise,
            "$or": [
                {CHAMP_UTC: {"$exists": False}},
                {"sequence": {"$exists": False}},
            ],
        }
        cursor = self.collection.find(filtre).limit(borne)
        documents = await cursor.to_list(borne)
        remplis = 0
        for document in documents:
            if not isinstance(document, Mapping):
                continue
            propre = document_ingestion(document)
            if CHAMP_UTC not in propre:
                continue
            filtre = ({"_id": document.get("_id")}
                      if document.get("_id") is not None
                      else {"id": document.get("id")})
            if filtre.get("id") is None and "_id" not in filtre:
                continue
            valeurs = {
                "tenant_id": propre.get("tenant_id"),
                "maj_le": propre.get("maj_le"),
                CHAMP_UTC: propre[CHAMP_UTC],
                "sequence": propre.get("sequence", ""),
            }
            if _texte(propre.get("id")):
                valeurs["id"] = propre["id"]
            await self.collection.update_one(filtre, {"$set": valeurs})
            remplis += 1
        return remplis

    async def compter_sans_maj_le_utc(self, tenant: str) -> int:
        return int(await self.collection.count_documents({
            "tenant_id": pont.normaliser_tenant(tenant),
            CHAMP_UTC: {"$exists": False},
        }))

    async def compter_non_conformes(self, tenant: str) -> int:
        """Compte les documents inexploitables : types, tenant non normalisé, dates illisibles.

        Le comptage est borné (``AUDIT_LIMITE``) pour rester un audit d'alerte, pas un scan de
        production. Les documents insérés après le démarrage sont revus à chaque passe.
        """
        tenant_normalise = pont.normaliser_tenant(tenant)
        filtre_types = {
            "tenant_id": tenant_normalise,
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
        total = int(await self.collection.count_documents(filtre_types))
        cursor = self.collection.find({"tenant_id": {"$type": "string"}}).limit(_AUDIT_LIMITE)
        async for document in cursor:
            if not isinstance(document, Mapping):
                continue
            tenant_brut = _texte(document.get("tenant_id"))
            if tenant_brut != tenant_normalise:
                total += 1
                continue
            maj_le = _texte(document.get("maj_le"))
            if maj_le and canoniser_instant(maj_le) is None:
                total += 1
        return total

    async def assurer_index(self) -> list[Any]:
        resultats = []
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), (CHAMP_UTC, 1), ("sequence", 1), ("id", 1)],
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

    async def _lire_brut(self, tenant: str) -> dict[str, Any] | None:
        document = await self.collection.find_one({"_id": tenant})
        return dict(document) if isinstance(document, Mapping) else None

    def _curseur(self, document: Mapping[str, Any] | None) -> CurseurObservation | None:
        if not isinstance(document, Mapping):
            return None
        maj_le = canoniser_instant(document.get("dernier_maj_le"))
        identifiant = _texte(document.get("dernier_id"))
        if maj_le is None or not identifiant:
            return None
        return CurseurObservation(
            maj_le=maj_le,
            sequence=sequence_canonique(document.get("dernier_sequence")),
            id=identifiant,
        )

    async def lire(self, tenant: str) -> CurseurObservation | None:
        return self._curseur(await self._lire_brut(pont.normaliser_tenant(tenant)))

    def _document(self, tenant: str, curseur: CurseurObservation) -> dict[str, Any]:
        return {
            "tenant_id": tenant,
            "dernier_maj_le": curseur.maj_le,
            "dernier_sequence": curseur.sequence,
            "dernier_id": curseur.id,
            "maj_le": canoniser_instant(self._horloge()),
        }

    def _filtre_cas(self, tenant: str, brut: Mapping[str, Any] | None,
                    actuel: CurseurObservation | None) -> dict[str, Any]:
        if brut is None or actuel is None:
            return {"_id": tenant}
        # On matche les valeurs **brutes** stockées (legacy secondes/offset) puis on réécrit
        # le document au format canonique.
        filtre: dict[str, Any] = {
            "_id": tenant,
            "dernier_maj_le": brut.get("dernier_maj_le"),
            "dernier_id": brut.get("dernier_id"),
        }
        if brut.get("dernier_sequence") is not None:
            filtre["dernier_sequence"] = brut.get("dernier_sequence")
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
            maj_le=maj_le, sequence=sequence_canonique(curseur.sequence),
            id=_texte(curseur.id))
        document = self._document(tenant_normalise, position)
        for _ in range(3):
            brut = await self._lire_brut(tenant_normalise)
            actuel = self._curseur(brut)
            if actuel is not None and position <= actuel:
                return actuel
            if brut is None:
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
            filtre = self._filtre_cas(tenant_normalise, brut, actuel)
            resultat = await self.collection.update_one(
                filtre, {"$set": document}, upsert=False)
            if int(getattr(resultat, "matched_count", 0) or 0) > 0:
                return position
        return await self.lire(tenant_normalise) or position


class DepotRejetsMesure:
    """Dead-letter durable : une correction permanente ne bloque jamais le tenant.

    Le compteur de tentatives borne les erreurs transitoires d'infrastructure. Les erreurs
    d'horloge ne sont pas comptées (``compter_tentative=False``) : elles attendent la correction
    de l'horloge sans être dead-letterées.
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
                          permanent: bool, tentatives_max: int = 5,
                          compter_tentative: bool = True) -> bool:
        """Enregistre/incrémente un rejet ; rend ``True`` si l'observation est dead-letterée."""
        tenant_normalise = pont.normaliser_tenant(tenant)
        cle = self._cle(tenant_normalise, document)
        instant = canoniser_instant(self._horloge())
        modification: dict[str, Any] = {
            "$setOnInsert": {
                "tenant_id": tenant_normalise,
                "observation_id": _texte(document.get("id")) or None,
                "cree_le": instant,
            },
            "$set": {
                "derniere_raison": _texte(raison)[:2000],
                "permanent": bool(permanent),
                "maj_le": instant,
            },
        }
        # `$inc` crée `tentatives` à 1 à l'insertion. Ne jamais le mettre aussi dans
        # `$setOnInsert` : Mongo refuse deux opérateurs sur le même champ (WriteError 40).
        if compter_tentative:
            modification["$inc"] = {"tentatives": 1}
        await self.collection.update_one({"_id": cle}, modification, upsert=True)
        document_rejet = await self.collection.find_one({"_id": cle}) or {}
        tentatives = int(document_rejet.get("tentatives") or 0)
        if not compter_tentative:
            etat = "retry"
        else:
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
