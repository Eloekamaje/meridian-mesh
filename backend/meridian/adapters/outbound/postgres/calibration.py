"""Calibration des prédictions : confiance annoncée contre justesse observée.

Le module lit et écrit la table ``prediction_calibration`` (il ne crée pas le
schéma). Une prédiction non résolue reste hors de toute mesure : le Brier et les
tranches de confiance ne portent que sur les prédictions dont ``outcome`` est un
booléen. Toutes les lectures et écritures sont filtrées par tenant ; aucun
secret n'est journalisé ni renvoyé.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import math
from typing import Any
import uuid

try:
    from psycopg.rows import dict_row as _dict_row
except ImportError:  # pragma: no cover - psycopg est une dépendance applicative
    _dict_row = None

__all__ = [
    "CalibrationInvalide",
    "Prediction",
    "PredictionIntrouvable",
    "brier",
    "enregistrer",
    "identifiant_prediction",
    "lire",
    "lister",
    "rapport",
    "resoudre",
    "resume",
]

_COLONNES = (
    "id",
    "tenant_id",
    "decision_id",
    "confidence",
    "outcome",
    "cree_le",
    "resolue_le",
)
_SELECT = "SELECT " + ", ".join(_COLONNES) + " FROM prediction_calibration"
_BORNES = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))
_TAILLE_MAX = 1000


class CalibrationInvalide(ValueError):
    """Une prédiction ou une résolution ne respecte pas le contrat attendu."""


class PredictionIntrouvable(LookupError):
    """La prédiction demandée n'existe pas dans le tenant."""


@dataclass(frozen=True)
class Prediction:
    """Une prédiction datée, tenant-scopée, avec son outcome éventuel."""

    id: str
    tenant: str
    decision_id: str
    confidence: float
    outcome: bool | None = None
    cree_le: Any = None
    resolue_le: Any = None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def tenant_id(self) -> str:
        """Alias de ``tenant`` pour les appelants qui nomment la colonne ``tenant_id``."""
        return self.tenant

    def __getitem__(self, cle: str) -> Any:
        if cle == "tenant_id":
            return self.tenant
        if cle not in self.as_dict():
            raise KeyError(cle)
        return getattr(self, cle)

    def __contains__(self, cle: object) -> bool:
        return cle in self.as_dict() or cle == "tenant_id"

    def __iter__(self):
        return iter(self.as_dict())

    def get(self, cle: str, defaut: Any = None) -> Any:
        try:
            return self[cle]
        except KeyError:
            return defaut

    def keys(self) -> tuple[str, ...]:
        return tuple(self.as_dict())

    def items(self):
        return self.as_dict().items()


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    if not isinstance(valeur, str) or not valeur.strip():
        raise CalibrationInvalide(f"{champ} obligatoire (chaîne non vide)")
    return valeur.strip()


def _tenant(valeur: Any) -> str:
    if valeur is not None and not isinstance(valeur, str) and hasattr(valeur, "id"):
        valeur = valeur.id
    return _texte_obligatoire(valeur, "tenant")


def _confiance(valeur: Any) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float, Decimal)):
        raise CalibrationInvalide("confidence doit être un nombre entre 0 et 1")
    nombre = float(valeur)
    if not math.isfinite(nombre) or nombre < 0 or nombre > 1:
        raise CalibrationInvalide("confidence doit être un nombre entre 0 et 1")
    return nombre


def _confiance_lue(valeur: Any) -> float:
    if isinstance(valeur, str):
        try:
            valeur = float(valeur.strip())
        except ValueError as exc:
            raise CalibrationInvalide("confidence invalide dans la ligne lue") from exc
    return _confiance(valeur)


def _outcome(valeur: Any) -> bool:
    if not isinstance(valeur, bool):
        raise CalibrationInvalide("outcome doit être un booléen")
    return valeur


def _outcome_ou_none(valeur: Any) -> bool | None:
    return None if valeur is None else _outcome(valeur)


def _id_existant(valeur: Any) -> str:
    if valeur is not None and not isinstance(valeur, str) and hasattr(valeur, "id"):
        valeur = valeur.id
    return _texte_obligatoire(valeur, "id")


def _identifiant(valeur: Any) -> str:
    if valeur is None:
        return f"pred-{uuid.uuid4().hex[:12]}"
    return _id_existant(valeur)


def identifiant_prediction(tenant: Any, decision_id: Any, confidence: Any) -> str:
    """Identifiant déterministe d'une prédiction pour un couple décision/confiance.

    Le même tenant, la même décision et la même confiance produisent le même
    identifiant : un enregistrement automatique rejoué ne duplique pas la ligne.
    """
    tenant_propre = _tenant(tenant)
    decision = _texte_obligatoire(decision_id, "decision_id")
    confiance = _confiance(confidence)
    charge = f"{tenant_propre}:{decision}:{confiance:.17g}"
    return "pred-" + hashlib.sha256(charge.encode("utf-8")).hexdigest()[:32]


def _limite(valeur: Any) -> int:
    if valeur is None:
        return _TAILLE_MAX
    if isinstance(valeur, bool):
        raise CalibrationInvalide("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise CalibrationInvalide("limite doit être un entier positif") from exc
    if borne < 1:
        raise CalibrationInvalide("limite doit être un entier positif")
    return min(borne, _TAILLE_MAX)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _est_sqlite(conn: Any) -> bool:
    return type(conn).__module__.split(".", 1)[0] == "sqlite3"


def _sql(conn: Any, requete: str) -> str:
    return requete.replace("%s", "?") if _est_sqlite(conn) else requete


def _cursor(conn: Any) -> Any:
    if _dict_row is not None:
        try:
            return conn.cursor(row_factory=_dict_row)
        except TypeError:
            pass
    return conn.cursor()


def _fermer(cur: Any) -> None:
    fermer = getattr(cur, "close", None)
    if callable(fermer):
        fermer()


def _executer(conn: Any, requete: str, parametres: tuple = ()) -> None:
    cur = _cursor(conn)
    try:
        cur.execute(_sql(conn, requete), parametres)
    finally:
        _fermer(cur)


def _une(conn: Any, requete: str, parametres: tuple = ()) -> Any:
    cur = _cursor(conn)
    try:
        cur.execute(_sql(conn, requete), parametres)
        return cur.fetchone()
    finally:
        _fermer(cur)


def _toutes(conn: Any, requete: str, parametres: tuple = ()) -> list[Any]:
    cur = _cursor(conn)
    try:
        cur.execute(_sql(conn, requete), parametres)
        return list(cur.fetchall())
    finally:
        _fermer(cur)


def _champ(ligne: Any, nom: str, rang: int) -> Any:
    if isinstance(ligne, Mapping):
        return ligne.get(nom)
    return ligne[rang]


def _outcome_lu(valeur: Any) -> bool | None:
    if valeur is None or isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, (int, float, Decimal)):
        return bool(valeur)
    texte = str(valeur).strip().lower()
    if texte in {"t", "true", "1", "oui", "yes"}:
        return True
    if texte in {"f", "false", "0", "non", "no"}:
        return False
    return bool(valeur)


def _prediction(ligne: Any) -> Prediction | None:
    if ligne is None:
        return None
    confiance = _confiance_lue(_champ(ligne, "confidence", 3))
    return Prediction(
        id=str(_champ(ligne, "id", 0)),
        tenant=str(_champ(ligne, "tenant_id", 1)),
        decision_id=str(_champ(ligne, "decision_id", 2)),
        confidence=confiance,
        outcome=_outcome_lu(_champ(ligne, "outcome", 4)),
        cree_le=_champ(ligne, "cree_le", 5),
        resolue_le=_champ(ligne, "resolue_le", 6),
    )


def enregistrer(
    conn: Any,
    tenant: Any,
    *,
    id: Any = None,
    decision_id: Any,
    confidence: Any,
    outcome: Any = None,
) -> Prediction:
    """Enregistre une prédiction tenant-scopée et rend la ligne créée.

    ``confidence`` doit être un nombre fini entre 0 et 1. ``outcome`` est soit
    absent, soit un booléen ; s'il est fourni, la prédiction est résolue
    immédiatement. L'identifiant est généré si ``id`` est absent.
    """
    tenant_propre = _tenant(tenant)
    decision = _texte_obligatoire(decision_id, "decision_id")
    confiance = _confiance(confidence)
    resultat = _outcome_ou_none(outcome)
    identifiant = _identifiant(id)
    cree_le = _maintenant()
    resolue_le = cree_le if resultat is not None else None
    _executer(
        conn,
        "INSERT INTO prediction_calibration "
        "(id, tenant_id, decision_id, confidence, outcome, cree_le, resolue_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (identifiant, tenant_propre, decision, confiance, resultat, cree_le, resolue_le),
    )
    return Prediction(
        id=identifiant,
        tenant=tenant_propre,
        decision_id=decision,
        confidence=confiance,
        outcome=resultat,
        cree_le=cree_le,
        resolue_le=resolue_le,
    )


def resoudre(conn: Any, tenant: Any, id: Any, outcome: Any) -> Prediction:
    """Renseigne l'outcome d'une prédiction du tenant et rend la ligne résolue.

    Une prédiction d'un autre tenant est introuvable : aucune lecture ni
    écriture ne traverse la frontière du tenant.
    """
    tenant_propre = _tenant(tenant)
    identifiant = _id_existant(id)
    resultat = _outcome(outcome)
    prediction = lire(conn, tenant_propre, identifiant)
    if prediction is None:
        raise PredictionIntrouvable("prédiction introuvable dans ce tenant")
    resolue_le = _maintenant()
    _executer(
        conn,
        "UPDATE prediction_calibration SET outcome = %s, resolue_le = %s "
        "WHERE tenant_id = %s AND id = %s",
        (resultat, resolue_le, tenant_propre, identifiant),
    )
    return Prediction(
        id=prediction.id,
        tenant=prediction.tenant,
        decision_id=prediction.decision_id,
        confidence=prediction.confidence,
        outcome=resultat,
        cree_le=prediction.cree_le,
        resolue_le=resolue_le,
    )


def lire(conn: Any, tenant: Any, id: Any) -> Prediction | None:
    """Lit une prédiction du tenant ; ``None`` si elle n'y existe pas."""
    tenant_propre = _tenant(tenant)
    identifiant = _id_existant(id)
    ligne = _une(
        conn,
        _SELECT + " WHERE tenant_id = %s AND id = %s",
        (tenant_propre, identifiant),
    )
    return _prediction(ligne)


def lister(
    conn: Any,
    tenant: Any,
    decision_id: Any = None,
    *,
    limite: Any = 100,
) -> list[Prediction]:
    """Liste les prédictions du tenant, éventuellement filtrées par décision."""
    tenant_propre = _tenant(tenant)
    conditions = ["tenant_id = %s"]
    parametres: list[Any] = [tenant_propre]
    if decision_id is not None:
        conditions.append("decision_id = %s")
        parametres.append(_texte_obligatoire(decision_id, "decision_id"))
    parametres.append(_limite(limite))
    lignes = _toutes(
        conn,
        _SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY cree_le, id LIMIT %s",
        tuple(parametres),
    )
    return [prediction for prediction in (_prediction(ligne) for ligne in lignes) if prediction is not None]


def _predictions(conn: Any, tenant: Any, decision_id: Any = None) -> list[Prediction]:
    tenant_propre = _tenant(tenant)
    conditions = ["tenant_id = %s"]
    parametres: list[Any] = [tenant_propre]
    if decision_id is not None:
        conditions.append("decision_id = %s")
        parametres.append(_texte_obligatoire(decision_id, "decision_id"))
    lignes = _toutes(
        conn,
        _SELECT + " WHERE " + " AND ".join(conditions) + " ORDER BY cree_le, id",
        tuple(parametres),
    )
    return [prediction for prediction in (_prediction(ligne) for ligne in lignes) if prediction is not None]


def _brier_de(predictions: list[Prediction]) -> float | None:
    carres = [
        (prediction.confidence - (1.0 if prediction.outcome else 0.0)) ** 2
        for prediction in predictions
        if prediction.outcome is not None
    ]
    if not carres:
        return None
    return sum(carres) / len(carres)


def brier(conn: Any, tenant: Any, *, decision_id: Any = None) -> float | None:
    """Erreur quadratique moyenne des prédictions résolues ; ``None`` si aucune.

    Un outcome absent exclut la prédiction du calcul. Aucune valeur n'est
    inventée quand la mesure n'existe pas encore.
    """
    return _brier_de(_predictions(conn, tenant, decision_id))


def _indice_tranche(confiance: float) -> int:
    for indice, (borne_min, borne_max) in enumerate(_BORNES):
        if borne_min <= confiance < borne_max:
            return indice
    return len(_BORNES) - 1


def _arrondi(valeur: float | None) -> float | None:
    return None if valeur is None else round(valeur, 9)


def rapport(conn: Any, tenant: Any, decision_id: Any = None) -> dict:
    """Répartit les prédictions résolues par tranche de confiance.

    Chaque tranche expose son effectif, le taux d'outcomes vrais observé, la
    confiance moyenne et l'écart ``taux observé - confiance moyenne`` (positif =
    sous-confiance, négatif = sur-confiance). Les prédictions non résolues sont
    comptées à part et exclues des tranches et du Brier.
    """
    predictions = _predictions(conn, tenant, decision_id)
    resolues = [prediction for prediction in predictions if prediction.outcome is not None]
    tranches = []
    for indice, (borne_min, borne_max) in enumerate(_BORNES):
        dans = [prediction for prediction in resolues if _indice_tranche(prediction.confidence) == indice]
        nombre = len(dans)
        taux = sum(1 for prediction in dans if prediction.outcome) / nombre if nombre else None
        confiance = sum(prediction.confidence for prediction in dans) / nombre if nombre else None
        ecart = taux - confiance if nombre and taux is not None and confiance is not None else None
        tranches.append({
            "intervalle": [borne_min, borne_max],
            "borne_min": borne_min,
            "borne_max": borne_max,
            "min": borne_min,
            "max": borne_max,
            "nombre": nombre,
            "count": nombre,
            "taux_observe": _arrondi(taux),
            "observed_rate": _arrondi(taux),
            "confiance_moyenne": _arrondi(confiance),
            "ecart": _arrondi(ecart),
            "calibration_gap": _arrondi(ecart),
            "gap": _arrondi(ecart),
        })
    return {
        "bins": tranches,
        "tranches": [dict(tranche) for tranche in tranches],
        "total": len(predictions),
        "resolues": len(resolues),
        "non_resolues": len(predictions) - len(resolues),
        "brier": _brier_de(resolues),
    }


def resume(conn: Any, tenant: Any, decision_id: Any = None) -> dict:
    """Résumé de calibration du tenant : volumes, Brier et écart global."""
    predictions = _predictions(conn, tenant, decision_id)
    resolues = [prediction for prediction in predictions if prediction.outcome is not None]
    if resolues:
        confiance = sum(prediction.confidence for prediction in resolues) / len(resolues)
        taux = sum(1 for prediction in resolues if prediction.outcome) / len(resolues)
        ecart = taux - confiance
    else:
        confiance = taux = ecart = None
    return {
        "total": len(predictions),
        "resolues": len(resolues),
        "non_resolues": len(predictions) - len(resolues),
        "brier": _brier_de(resolues),
        "confiance_moyenne": _arrondi(confiance),
        "taux_observe": _arrondi(taux),
        "ecart": _arrondi(ecart),
    }
