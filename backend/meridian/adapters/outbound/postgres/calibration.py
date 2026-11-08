"""Calibration des prédictions : confiance annoncée contre justesse observée.

Le module lit et écrit la table ``prediction_calibration`` (il ne crée pas le
schéma). Une prédiction non résolue reste hors de toute mesure : le Brier et les
tranches de confiance ne portent que sur les prédictions dont ``outcome`` est un
booléen. Toutes les lectures et écritures sont filtrées par tenant ; aucun
secret n'est journalisé ni renvoyé.

C4 : les prédictions datées (``sujet``, ``echeance``, ``source``, ``statut``,
``issue`` — colonnes ajoutées par le schéma) sont résolues contre les outcomes
réels à leur échéance. ``enregistrer_prediction`` ouvre une prédiction datée ;
``resoudre`` appelé sans identifiant rejoue, pour chaque prédiction échue, la
même requête bornée que :mod:`resolution_besoins` sur la source de la
prédiction ; ``score_brier`` rend le Brier avec son intervalle de Wilson —
jamais un nombre sans ``n`` (``None`` sous le seuil). Sur un schéma sans les
colonnes C4, l'écriture et la résolution retombent sur les sept colonnes
historiques ; la résolution en masse refuse alors explicitement.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import math
from typing import Any
import uuid

from meridian.adapters.outbound.postgres import (
    detecteurs_besoins, entreprise_depot, signatures_besoins,
)

try:
    from psycopg.rows import dict_row as _dict_row
except ImportError:  # pragma: no cover - psycopg est une dépendance applicative
    _dict_row = None

__all__ = [
    "CalibrationInvalide",
    "Prediction",
    "PredictionIntrouvable",
    "MIN_RESOLUTIONS",
    "brier",
    "enregistrer",
    "enregistrer_prediction",
    "identifiant_prediction",
    "lire",
    "lister",
    "rapport",
    "resoudre",
    "resoudre_echues",
    "resume",
    "score_brier",
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
_COLONNES_ETENDUES = _COLONNES + ("sujet", "echeance", "source", "statut", "issue")
_SELECT = "SELECT " + ", ".join(_COLONNES) + " FROM prediction_calibration"
_SELECT_ETENDU = (
    "SELECT " + ", ".join(_COLONNES_ETENDUES) + " FROM prediction_calibration")
_BORNES = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))
_TAILLE_MAX = 1000
MIN_RESOLUTIONS = 10  # rapport refusé sous ce seuil : jamais un nombre sans n


class CalibrationInvalide(ValueError):
    """Une prédiction ou une résolution ne respecte pas le contrat attendu."""


class PredictionIntrouvable(LookupError):
    """La prédiction demandée n'existe pas dans le tenant."""


@dataclass(frozen=True)
class Prediction:
    """Une prédiction datée, tenant-scopée, avec son outcome éventuel.

    Les champs C4 (``sujet``, ``echeance``, ``source``, ``statut``, ``issue``)
    sont remplis par :func:`enregistrer_prediction`, :func:`resoudre` et le
    rapport de :func:`resoudre_echues` ; les lectures historiques (``lire``,
    ``lister``) ne portent que les sept colonnes de base.
    """

    id: str
    tenant: str
    decision_id: str
    confidence: float
    outcome: bool | None = None
    cree_le: Any = None
    resolue_le: Any = None
    sujet: str = ""
    echeance: Any = None
    source: str = ""
    statut: str = ""
    issue: str | None = None

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


def _date_ou_none(valeur: Any, champ: str) -> datetime | None:
    """Date ISO ou ``datetime`` → ``datetime`` UTC ; ``None`` si absent, erreur sinon."""
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    else:
        try:
            instant = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        except ValueError as exc:
            raise CalibrationInvalide(f"{champ} : date ISO attendue") from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _minimum(valeur: Any) -> int:
    if isinstance(valeur, bool):
        raise CalibrationInvalide("minimum doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise CalibrationInvalide("minimum doit être un entier positif") from exc
    if borne < 1:
        raise CalibrationInvalide("minimum doit être un entier positif")
    return borne


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


def _etendues(conn: Any) -> bool:
    """Les colonnes C4 (``sujet``…) existent-elles ? Une absence n'est pas fatale :
    l'écriture retombe sur les sept colonnes historiques."""
    try:
        if _est_sqlite(conn):
            _executer(conn, "SELECT sujet FROM prediction_calibration WHERE 1 = 0")
        else:
            with conn.transaction():  # savepoint : un schéma ancien ne casse pas l'appelant
                _executer(conn, "SELECT sujet FROM prediction_calibration WHERE 1 = 0")
    except Exception:
        return False
    return True


def _inserer(
    conn: Any, tenant: str, identifiant: str, decision: str, confiance: float,
    resultat: bool | None, cree_le: datetime, resolue_le: datetime | None, *,
    sujet: str = "", echeance: datetime | None = None, source: str = "",
) -> None:
    """Insert tenant-scopé ; colonnes C4 quand le schéma les porte, sinon repli."""
    if _etendues(conn):
        statut = "resolue" if resultat is not None else "ouverte"
        issue = None if resultat is None else ("succes" if resultat else "echec")
        _executer(
            conn,
            "INSERT INTO prediction_calibration "
            "(id, tenant_id, decision_id, confidence, outcome, cree_le, resolue_le, "
            "sujet, echeance, source, statut, issue) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (identifiant, tenant, decision, confiance, resultat, cree_le, resolue_le,
             sujet or None, echeance, source or None, statut, issue),
        )
        return
    _executer(
        conn,
        "INSERT INTO prediction_calibration "
        "(id, tenant_id, decision_id, confidence, outcome, cree_le, resolue_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (identifiant, tenant, decision, confiance, resultat, cree_le, resolue_le),
    )


def _marquer_resolue(
    conn: Any, tenant: str, identifiant: str, resultat: bool, resolue_le: datetime,
) -> str:
    """UPDATE de résolution ; ``statut``/``issue`` renseignés quand le schéma les porte."""
    issue = "succes" if resultat else "echec"
    if _etendues(conn):
        _executer(
            conn,
            "UPDATE prediction_calibration SET outcome = %s, resolue_le = %s, "
            "statut = 'resolue', issue = %s WHERE tenant_id = %s AND id = %s",
            (resultat, resolue_le, issue, tenant, identifiant),
        )
    else:
        _executer(
            conn,
            "UPDATE prediction_calibration SET outcome = %s, resolue_le = %s "
            "WHERE tenant_id = %s AND id = %s",
            (resultat, resolue_le, tenant, identifiant),
        )
    return issue


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
    _inserer(conn, tenant_propre, identifiant, decision, confiance, resultat,
             cree_le, resolue_le)
    return Prediction(
        id=identifiant,
        tenant=tenant_propre,
        decision_id=decision,
        confidence=confiance,
        outcome=resultat,
        cree_le=cree_le,
        resolue_le=resolue_le,
        statut="resolue" if resultat is not None else "ouverte",
        issue=None if resultat is None else ("succes" if resultat else "echec"),
    )


def enregistrer_prediction(
    conn: Any,
    tenant: Any,
    prediction: Any = None,
    *,
    id: Any = None,
    sujet: Any = None,
    probabilite: Any = None,
    echeance: Any = None,
    source: Any = None,
    decision_id: Any = None,
    outcome: Any = None,
) -> Prediction:
    """Enregistre une prédiction datée ``{sujet, probabilite, echeance, source}``.

    La ligne est ouverte (``statut = 'ouverte'``) tant qu'``outcome`` n'est pas
    fourni ; un outcome booléen la résout immédiatement (``issue`` =
    ``succes``/``echec``). ``sujet`` nomme ce qui est prédit (un besoin, un
    signal), ``source`` la sonde qui l'a émise ; ``decision_id`` prend ``sujet``
    par défaut. ``prediction`` est un mapping de ces mêmes clés — les arguments
    nommés priment. Sans ``id``, l'identifiant est déterministe : un rejeu du
    même enregistrement vise la même ligne.
    """
    donnees: dict = {}
    if prediction is not None:
        if not isinstance(prediction, Mapping):
            raise CalibrationInvalide("prediction : mapping attendu")
        donnees = dict(prediction)
    for cle, valeur in (
        ("id", id), ("sujet", sujet), ("probabilite", probabilite),
        ("echeance", echeance), ("source", source),
        ("decision_id", decision_id), ("outcome", outcome),
    ):
        if valeur is not None:
            donnees[cle] = valeur
    tenant_propre = _tenant(tenant)
    sujet_final = _texte_obligatoire(donnees.get("sujet"), "sujet")
    confiance = _confiance(
        donnees["probabilite"] if "probabilite" in donnees else donnees.get("confidence"))
    echeance_dt = _date_ou_none(donnees.get("echeance"), "echeance")
    source_finale = _texte_obligatoire(donnees.get("source"), "source")
    decision = _texte_obligatoire(
        donnees.get("decision_id") or sujet_final, "decision_id")
    resultat = _outcome_ou_none(donnees.get("outcome"))
    identifiant = donnees.get("id")
    if identifiant is None:
        identifiant = identifiant_prediction(
            tenant_propre,
            f"{decision}|{sujet_final}|{source_finale}"
            f"|{echeance_dt.isoformat() if echeance_dt else ''}",
            confiance)
    else:
        identifiant = _id_existant(identifiant)
    cree_le = _maintenant()
    resolue_le = cree_le if resultat is not None else None
    _inserer(conn, tenant_propre, identifiant, decision, confiance, resultat,
             cree_le, resolue_le, sujet=sujet_final, echeance=echeance_dt,
             source=source_finale)
    return Prediction(
        id=identifiant,
        tenant=tenant_propre,
        decision_id=decision,
        confidence=confiance,
        outcome=resultat,
        cree_le=cree_le,
        resolue_le=resolue_le,
        sujet=sujet_final,
        echeance=echeance_dt,
        source=source_finale,
        statut="resolue" if resultat is not None else "ouverte",
        issue=None if resultat is None else ("succes" if resultat else "echec"),
    )


def resoudre(
    conn: Any,
    tenant: Any,
    id: Any = None,
    outcome: Any = None,
    *,
    maintenant: Any = None,
    observateur: Callable | None = None,
    limite: Any = None,
) -> Prediction | dict:
    """Résout une prédiction, ou toutes les prédictions échues si ``id`` est absent.

    Forme unitaire ``resoudre(conn, tenant, id, outcome)`` : renseigne l'outcome
    booléen de la prédiction du tenant — une prédiction d'un autre tenant est
    introuvable : aucune lecture ni écriture ne traverse la frontière du tenant.

    Forme passe ``resoudre(conn, tenant, maintenant=…)`` : délègue à
    :func:`resoudre_echues`, qui juge chaque prédiction ouverte et échue contre
    l'outcome réel de sa source.
    """
    if id is None:
        if outcome is not None:
            raise CalibrationInvalide("outcome sans prédiction ciblée")
        return resoudre_echues(
            conn, tenant, maintenant=maintenant, observateur=observateur,
            limite=limite)
    tenant_propre = _tenant(tenant)
    identifiant = _id_existant(id)
    resultat = _outcome(outcome)
    prediction = lire(conn, tenant_propre, identifiant)
    if prediction is None:
        raise PredictionIntrouvable("prédiction introuvable dans ce tenant")
    resolue_le = _maintenant()
    issue = _marquer_resolue(conn, tenant_propre, identifiant, resultat, resolue_le)
    return Prediction(
        id=prediction.id,
        tenant=prediction.tenant,
        decision_id=prediction.decision_id,
        confidence=prediction.confidence,
        outcome=resultat,
        cree_le=prediction.cree_le,
        resolue_le=resolue_le,
        sujet=prediction.sujet,
        echeance=prediction.echeance,
        source=prediction.source,
        statut="resolue",
        issue=issue,
    )


def _ligne_etendue(ligne: Any) -> dict:
    return {nom: _champ(ligne, nom, rang) for rang, nom in enumerate(_COLONNES_ETENDUES)}


def _signal_attendu_produit(
    conn: Any, tenant: str, entree: Mapping, instant: datetime,
) -> bool | None:
    """Le signal attendu s'est-il produit ? ``None`` quand la source n'a pas de sonde.

    Pour les paris de besoins (``source`` = signature de détecteur), l'événement
    attendu est la disparition du signal d'origine : la même requête bornée que
    :func:`resolution_besoins._signal_present` est rejouée sur le sujet de la
    prédiction — ``True`` si le signal a disparu (besoin corroboré/résolu).
    """
    source = str(entree.get("source") or "")
    if source not in detecteurs_besoins.SIGNATURES:
        return None
    sujet = str(entree.get("sujet") or "")
    if not sujet:
        raise CalibrationInvalide("prédiction sans sujet : signal introuvable")
    # Import différé : resolution_besoins importe ce module pour y écrire les paris.
    from meridian.adapters.outbound.postgres import resolution_besoins
    objet = entreprise_depot.lire_objet(conn, tenant, sujet)
    if objet is None:
        raise CalibrationInvalide(f"sujet introuvable dans le tenant : {sujet}")
    intention = {"donnees": {"signature": source}}
    entree_besoin = {"objet": objet, "genre": str(objet.get("type") or "").upper()}
    present = resolution_besoins._signal_present(
        conn, tenant, entree_besoin, intention,
        assertions=None, situations=None, claims=None,
        seuil=detecteurs_besoins.SEUIL_RECURRENCE,
        fenetre_jours=detecteurs_besoins.FENETRE_JOURS_DEFAUT,
        instant=instant)
    return not present


def resoudre_echues(
    conn: Any,
    tenant: Any,
    *,
    maintenant: Any = None,
    observateur: Callable | None = None,
    limite: Any = None,
) -> dict:
    """Résout les prédictions ouvertes et échues contre leurs outcomes réels.

    Chaque prédiction ``ouverte`` dont ``echeance <= maintenant`` est jugée :
    l'événement attendu s'est-il produit ? ``observateur(conn, tenant, ligne)``
    remplace la sonde par défaut quand il est fourni — le défaut rejoue la
    requête bornée de :mod:`resolution_besoins` sur la ``source`` de la
    prédiction ; ``None`` (source sans sonde) laisse la prédiction ouverte et la
    compte dans ``ignorees``. Verdict : produit → ``issue = succes``, non
    produit → ``issue = echec``. Fail-closed : une erreur par prédiction remonte
    dans ``erreurs``, jamais avalée, et la prédiction reste ouverte pour la
    passe suivante.
    """
    tenant_propre = _tenant(tenant)
    instant = _date_ou_none(maintenant, "maintenant") or _maintenant()
    if not _etendues(conn):
        raise CalibrationInvalide(
            "prédictions datées indisponibles : colonnes sujet/echeance/source "
            "absentes du schéma")
    lignes = _toutes(
        conn,
        _SELECT_ETENDU + " WHERE tenant_id = %s AND outcome IS NULL "
        "AND echeance IS NOT NULL AND echeance <= %s "
        "ORDER BY echeance, id LIMIT %s",
        (tenant_propre, instant, _limite(limite)),
    )
    resolues: list[dict] = []
    ignorees: list[dict] = []
    erreurs: list[dict] = []
    for ligne in lignes:
        entree = _ligne_etendue(ligne)
        try:
            if observateur is not None:
                produit = observateur(conn, tenant_propre, dict(entree))
            else:
                produit = _signal_attendu_produit(conn, tenant_propre, entree, instant)
            if produit is None:
                ignorees.append({
                    "id": entree["id"], "sujet": entree.get("sujet"),
                    "source": entree.get("source"),
                    "raison": "source sans sonde bornée"})
                continue
            resoudre(conn, tenant_propre, entree["id"], bool(produit))
            resolues.append({
                "id": entree["id"], "sujet": entree.get("sujet"),
                "source": entree.get("source"),
                "issue": "succes" if produit else "echec"})
        except Exception as exc:  # fail-closed : la prédiction reste ouverte, rejouée
            erreurs.append({
                "id": entree.get("id"), "sujet": entree.get("sujet"),
                "source": entree.get("source"), "erreur": str(exc)})
    succes = sum(1 for resolue in resolues if resolue["issue"] == "succes")
    return {
        "tenant": tenant_propre,
        "maintenant": instant.isoformat(timespec="seconds"),
        "resolues": resolues,
        "ignorees": ignorees,
        "erreurs": erreurs,
        "totaux": {
            "echues": len(lignes), "resolues": len(resolues),
            "succes": succes, "echecs": len(resolues) - succes,
            "ignorees": len(ignorees), "erreurs": len(erreurs),
        },
    }


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


# --- C4 : mesure publiée — Brier + intervalle de Wilson, jamais sans n ---


def _mesure_resolues(resolues: list[tuple[float, bool]], minimum: int) -> dict:
    """Mesure d'un lot ``(confiance, outcome)`` : ``None`` tant que n < minimum."""
    n = len(resolues)
    succes = sum(1 for _, issue in resolues if issue)
    mesure = {"n": n, "succes": succes, "minimum": minimum,
              "brier": None, "taux": None, "ic95": None}
    if n < minimum:
        return mesure
    mesure["brier"] = sum(
        (confiance - (1.0 if issue else 0.0)) ** 2
        for confiance, issue in resolues) / n
    mesure["taux"] = succes / n
    mesure["ic95"] = signatures_besoins.intervalle_wilson(succes, n)
    return mesure


def _par_source(
    conn: Any, tenant: str, decision_id: Any, minimum: int,
) -> dict[str, dict]:
    """Même mesure par ``source`` ; vide sur un schéma sans la colonne."""
    if not _etendues(conn):
        return {}
    conditions = ["tenant_id = %s", "outcome IS NOT NULL"]
    parametres: list[Any] = [tenant]
    if decision_id is not None:
        conditions.append("decision_id = %s")
        parametres.append(_texte_obligatoire(decision_id, "decision_id"))
    lignes = _toutes(
        conn,
        "SELECT source, confidence, outcome FROM prediction_calibration WHERE "
        + " AND ".join(conditions),
        tuple(parametres),
    )
    groupes: dict[str, list[tuple[float, bool]]] = {}
    for ligne in lignes:
        source = str(_champ(ligne, "source", 0) or "") or "inconnue"
        resolue = (_confiance_lue(_champ(ligne, "confidence", 1)),
                   bool(_outcome_lu(_champ(ligne, "outcome", 2))))
        groupes.setdefault(source, []).append(resolue)
    return {
        source: _mesure_resolues(predictions, minimum)
        for source, predictions in sorted(groupes.items())
    }


def score_brier(
    conn: Any, tenant: Any, *, decision_id: Any = None, minimum: Any = MIN_RESOLUTIONS,
) -> dict:
    """Score de Brier des résolutions du tenant + IC de Wilson sur le taux observé.

    ``{"brier", "n", "succes", "taux", "ic95", "minimum", "non_resolues",
    "par_source"}`` : ``brier``, ``taux`` et ``ic95`` sont ``None`` tant que le
    nombre de résolutions ``n`` est sous ``minimum`` — jamais un nombre sans
    ``n``. ``ic95`` est l'intervalle de Wilson à 95 % du taux de succès observé
    (``{bas, haut, z}``). ``par_source`` décline la même mesure par ``source``
    de prédiction quand le schéma porte la colonne, sinon ``{}``.
    """
    tenant_propre = _tenant(tenant)
    borne = _minimum(minimum)
    predictions = _predictions(conn, tenant_propre, decision_id)
    resolues = [
        (prediction.confidence, bool(prediction.outcome))
        for prediction in predictions
        if prediction.outcome is not None
    ]
    mesure = _mesure_resolues(resolues, borne)
    mesure["non_resolues"] = len(predictions) - len(resolues)
    mesure["par_source"] = _par_source(conn, tenant_propre, decision_id, borne)
    return mesure
