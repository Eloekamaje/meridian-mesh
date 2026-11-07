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
        # `maj_le` garde la microseconde pour C1 (corrections dans la même ms) ;
        # `maj_le_utc` est la date BSON (ms) indexée pour le seek.
        propre["maj_le"] = canoniser_instant(maj_le)
        propre[CHAMP_UTC] = _millisecondes(maj_le)
    sequence = sequence_canonique(
        propre.get("sequence_canonique")
        if propre.get("sequence_canonique") is not None
        else (propre.get("sequence") if propre.get("sequence") is not None
              else propre.get("_id")))
    propre["sequence"] = sequence
    propre["sequence_canonique"] = sequence
    return propre


def curseur_document(document: Mapping[str, Any]) -> CurseurObservation:
    """Curseur d'un document ; lève ``ValueError`` si ``maj_le`` ou ``id`` manque.

    La date effective est ``max(maj_le_utc, maj_le)`` : une correction legacy qui n'a mis à
    jour que ``maj_le`` reste visible même si le backfill a posé un ``maj_le_utc`` plus ancien.
    """
    dates = [
        _instant_datetime(document.get(CHAMP_UTC)),
        _instant_datetime(document.get("maj_le")),
    ]
    dates = [valeur for valeur in dates if valeur is not None]
    if not dates:
        raise ValueError("maj_le absent ou illisible")
    # Le curseur de lecture est aligné sur la précision BSON Date (ms) ; le payload de
    # l'événement garde `maj_le` en microsecondes pour que C1 voie les corrections.
    maj_le = canoniser_instant(_millisecondes(max(dates)))
    identifiant = _texte(document.get("id"))
    if not identifiant:
        raise ValueError("id d'observation absent")
    sequence = sequence_canonique(
        document.get("sequence_canonique")
        if document.get("sequence_canonique") is not None
        else (document.get("sequence") if document.get("sequence") is not None
              else document.get("_id")))
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
                {"sequence_canonique": {"$gt": curseur.sequence}},
            ]},
            {"$and": [
                {CHAMP_UTC: date_curseur},
                {"sequence_canonique": curseur.sequence},
                {"id": {"$gt": curseur.id}},
            ]},
        ]
        return filtre

    def _filtre_perime(self, tenant: str,
                       curseur: CurseurObservation | None) -> dict[str, Any]:
        """Corrections legacy : `maj_le` strictement plus récent que `maj_le_utc`."""
        def date_maj_le() -> dict[str, Any]:
            return {"$convert": {
                "input": "$maj_le", "to": "date", "onError": None, "onNull": None}}

        # Une avance de moins d'une milliseconde est le résidu normal de la troncature BSON :
        # on ne la considère pas comme une correction legacy (M2).
        expr: dict[str, Any] = {"$gt": [
            date_maj_le(), {"$add": ["$maj_le_utc", 1]}]}
        if curseur is not None:
            instant = _instant_datetime(curseur.maj_le)
            if instant is not None:
                expr = {"$and": [
                    expr,
                    {"$gt": [date_maj_le(), instant]},
                ]}
        return {
            "tenant_id": pont.normaliser_tenant(tenant),
            CHAMP_UTC: {"$exists": True},
            "id": {"$exists": True, "$type": "string"},
            "$expr": expr,
        }

    def _filtres_maj_le(self, tenant: str, curseur: CurseurObservation | None, *,
                        avec_utc: bool, sans_sequence: bool = False) -> list[dict[str, Any]]:
        """Filtre `maj_le >= curseur` pour les corrections legacy / documents non tie-breakés.

        On compare les dates via ``$convert`` : les chaînes ISO (offset compris) et les BSON
        Date sont ramenées au même instant, sans dépendre du format brut stocké. Le filtre
        Python applique ensuite le tie-breaker séquence/id exact.
        """
        tenant_normalise = pont.normaliser_tenant(tenant)
        base: dict[str, Any] = {
            "tenant_id": tenant_normalise,
            "id": {"$exists": True, "$type": "string"},
        }
        if avec_utc:
            base[CHAMP_UTC] = {"$exists": True}
        else:
            base[CHAMP_UTC] = {"$exists": False}
        if sans_sequence:
            base["sequence_canonique"] = {"$exists": False}
        instant = _instant_datetime(curseur.maj_le) if curseur is not None else None
        if instant is None:
            return [{**base, "maj_le": {"$exists": True}}]
        return [{
            **base,
            "maj_le": {"$exists": True},
            "$expr": {"$gte": [
                {"$convert": {
                    "input": "$maj_le", "to": "date", "onError": None, "onNull": None}},
                instant,
            ]},
        }]

    async def lister_apres(self, tenant: str, curseur: CurseurObservation | None = None,
                           limite: int = 100) -> list[dict[str, Any]]:
        borne = max(1, min(int(limite), _MAX_LOT))
        tenant_normalise = pont.normaliser_tenant(tenant)

        # Les corrections legacy et les documents non backfillés sont prioritaires : on les
        # draine avant le seek principal pour qu'un document canonique plus récent ne fasse
        # jamais avancer le checkpoint au-delà d'une correction plus ancienne.
        prioritaires: list[dict[str, Any]] = []
        filtre_perime = self._filtre_perime(tenant_normalise, curseur)
        cursor = self.collection.find(filtre_perime)
        cursor = cursor.sort([("maj_le", 1), ("_id", 1)]).limit(borne)
        prioritaires.extend(await cursor.to_list(borne))
        for filtre in self._filtres_maj_le(
                tenant_normalise, curseur, avec_utc=False):
            cursor = self.collection.find(filtre)
            cursor = cursor.sort([("maj_le", 1), ("_id", 1)]).limit(borne)
            prioritaires.extend(await cursor.to_list(borne))
        for filtre in self._filtres_maj_le(
                tenant_normalise, curseur, avec_utc=True, sans_sequence=True):
            cursor = self.collection.find(filtre)
            cursor = cursor.sort([("maj_le", 1), ("_id", 1)]).limit(borne)
            prioritaires.extend(await cursor.to_list(borne))

        par_id: dict[str, tuple[CurseurObservation, dict[str, Any]]] = {}

        def ajouter(documents: list[dict[str, Any]]) -> None:
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

        ajouter(prioritaires)
        if not par_id:
            # Seek d'index : les documents canoniques après le curseur, sans fenêtre glissante.
            filtre_principal = self._filtre_principal(tenant_normalise, curseur)
            cursor = self.collection.find(filtre_principal)
            cursor = cursor.sort(
                [(CHAMP_UTC, 1), ("sequence_canonique", 1), ("id", 1)]).limit(borne)
            ajouter(await cursor.to_list(borne))
        retenus = sorted(par_id.values(), key=lambda paire: paire[0])
        return [document for _position, document in retenus[:borne]]

    async def remplir_maj_le_utc(self, tenant: str, limite: int = _BACKFILL_LOT) -> int:
        """Backfill borné des documents legacy : écrit ``maj_le_utc`` et la séquence canonique."""
        tenant_normalise = pont.normaliser_tenant(tenant)
        borne = max(1, min(int(limite), _MAX_LOT))
        date_maj = {"$convert": {
            "input": "$maj_le", "to": "date", "onError": None, "onNull": None}}
        filtre = {
            "tenant_id": tenant_normalise,
            "$or": [
                {CHAMP_UTC: {"$exists": False}},
                {"sequence_canonique": {"$exists": False}},
                {"$expr": {"$gt": [
                    date_maj, {"$add": ["$maj_le_utc", 1]}]}},
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
            base = ({"_id": document.get("_id")}
                    if document.get("_id") is not None
                    else {"id": document.get("id")})
            if base.get("id") is None and "_id" not in base:
                continue
            # CAS : si un producteur a corrigé le document entre la lecture et l'écriture,
            # on n'écrase pas sa correction ; il sera repris au backfill suivant.
            conditions: list[dict[str, Any]] = [base]
            for champ in ("maj_le", "sequence", "sequence_canonique"):
                if champ in document:
                    conditions.append({champ: document[champ]})
                else:
                    conditions.append({champ: {"$exists": False}})
            valeurs = {
                "tenant_id": propre.get("tenant_id"),
                "maj_le": propre.get("maj_le"),
                CHAMP_UTC: propre[CHAMP_UTC],
                "sequence": propre.get("sequence", ""),
                "sequence_canonique": propre.get("sequence_canonique", ""),
            }
            if _texte(propre.get("id")):
                valeurs["id"] = propre["id"]
            resultat = await self.collection.update_one(
                {"$and": conditions}, {"$set": valeurs}, upsert=False)
            if int(getattr(resultat, "matched_count", 0) or 0) > 0:
                remplis += 1
        return remplis

    async def compter_sans_maj_le_utc(self, tenant: str) -> int:
        return int(await self.collection.count_documents({
            "tenant_id": pont.normaliser_tenant(tenant),
            CHAMP_UTC: {"$exists": False},
        }))

    async def compter_a_migrer(self, tenant: str) -> int:
        """Documents à backfiller avant toute lecture : champs canoniques absents ou périmés."""
        date_maj = {"$convert": {
            "input": "$maj_le", "to": "date", "onError": None, "onNull": None}}
        return int(await self.collection.count_documents({
            "tenant_id": pont.normaliser_tenant(tenant),
            "id": {"$exists": True, "$type": "string", "$ne": ""},
            "maj_le": {"$exists": True},
            "$and": [
                # Une date illisible est un défaut d'audit, pas une migration : elle ne doit
                # jamais bloquer le tenant.
                {"$expr": {"$ne": [date_maj, None]}},
                {"$or": [
                    {CHAMP_UTC: {"$exists": False}},
                    {"sequence_canonique": {"$exists": False}},
                    {"$expr": {"$gt": [
                        date_maj, {"$add": ["$maj_le_utc", 1]}]}},
                ]},
            ],
        }))

    async def auditer_lot(self, tenant: str, apres_id: Any = None,
                          limite: int = _AUDIT_LIMITE) -> tuple[int, Any, int]:
        """Audit borné et rotatif : rend ``(défauts, dernier _id, documents lus)``.

        Les documents d'un autre tenant (même mal normalisés, ex. ``Assurance``) sont ignorés :
        l'audit de ``banque`` ne compte que les défauts de ``banque``. Le curseur ``apres_id``
        (``_id`` Mongo brut) permet de faire tourner le scan entre les passes.
        """
        tenant_normalise = pont.normaliser_tenant(tenant)
        borne = max(1, min(int(limite), _AUDIT_LIMITE))
        filtre: dict[str, Any] = {"tenant_id": {"$type": "string"}}
        if apres_id is not None:
            filtre["_id"] = {"$gt": apres_id}
        cursor = self.collection.find(filtre).sort([("_id", 1)]).limit(borne)
        documents = await cursor.to_list(borne)
        total = 0
        dernier = apres_id
        for document in documents:
            if not isinstance(document, Mapping):
                continue
            dernier = document.get("_id", dernier)
            tenant_brut = _texte(document.get("tenant_id"))
            try:
                normalise = pont.normaliser_tenant(tenant_brut)
            except pont.PontInvalide:
                normalise = None
            if normalise is not None and normalise != tenant_normalise:
                continue
            defaut = normalise is None or tenant_brut != tenant_normalise
            identifiant = document.get("id")
            if not isinstance(identifiant, str) or not identifiant.strip():
                defaut = True
            maj_le = document.get("maj_le")
            if maj_le is None or canoniser_instant(maj_le) is None:
                defaut = True
            if defaut:
                total += 1
        return total, dernier, len(documents)

    async def compter_non_conformes(self, tenant: str) -> int:
        """Audit borné d'une passe (compatibilité tests/exploitation)."""
        total, _dernier, _lus = await self.auditer_lot(tenant)
        return total

    async def assurer_index(self) -> list[Any]:
        resultats = []
        resultats.append(await self.collection.create_index(
            [("tenant_id", 1), (CHAMP_UTC, 1), ("sequence_canonique", 1), ("id", 1)],
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
        actuel = await self.lire(tenant_normalise)
        if actuel is None:
            raise RuntimeError("checkpoint non écrit après CAS")
        return actuel


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
