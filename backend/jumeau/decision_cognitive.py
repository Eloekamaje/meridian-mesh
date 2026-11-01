"""Assistance décisionnelle enrichie : contrefactuel déclaré et calibration tracée.

Le module ne choisit aucune option et n'invente aucune mesure. Il expose le
contrefactuel comme une comparaison strictement déclarative, enregistre les
confiances annoncées dans la calibration et résout les outcomes observés. Une
comparaison contrefactuelle n'est ajoutée au decision support que si des options
sont fournies ; sinon la clé vaut ``None``. Les entrées ne sont jamais mutées.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jumeau import calibration, contrefactuel

__all__ = [
    "calibrer_decision_support",
    "construire_contrefactuel",
    "decision_support_enrichi",
    "enregistrer_confiance",
    "resoudre_outcome",
]


def construire_contrefactuel(options: Any, changements: Any = None, *, criteres: Any = ()) -> dict:
    """Compare des options sous des changements explicitement déclarés.

    La comparaison est déléguée à :func:`contrefactuel.comparer` ; elle ne
    contient aucune recommandation et n'attribue aucun effet causal.
    """
    return contrefactuel.comparer(options, changements, criteres=criteres)


def enregistrer_confiance(
    conn: Any,
    tenant: Any,
    *,
    decision_id: Any,
    confidence: Any,
    prediction_id: Any = None,
) -> Any:
    """Enregistre une prédiction de confiance pour une décision du tenant.

    ``prediction_id`` devient l'identifiant de la prédiction ; s'il est absent,
    la calibration en génère un. Une valeur manquante ou hors contrat est
    refusée par la calibration, sans valeur de remplacement inventée.
    """
    return calibration.enregistrer(
        conn,
        tenant,
        id=prediction_id,
        decision_id=decision_id,
        confidence=confidence,
    )


def resoudre_outcome(conn: Any, tenant: Any, prediction_id: Any, outcome: Any) -> Any:
    """Renseigne l'outcome observé d'une prédiction du tenant.

    Une prédiction absente ou appartenant à un autre tenant reste introuvable :
    aucune écriture ne traverse la frontière du tenant.
    """
    return calibration.resoudre(conn, tenant, prediction_id, outcome)


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _outcome_explicite(decision_support: Mapping, outcome: Any) -> Any:
    if outcome is not None:
        return outcome
    for nom in ("outcome", "resultat_observe"):
        if nom in decision_support:
            return decision_support[nom]
    return None


def calibrer_decision_support(
    conn: Any,
    tenant: Any,
    decision_support: Any,
    *,
    decision_id: Any = None,
    confidence: Any = None,
    prediction_id: Any = None,
    outcome: Any = None,
) -> Any:
    """Enregistre ou résout la prédiction portée par un decision support.

    Une décision (identifiant explicite ou ``decision_id`` du support) et une
    confiance sont nécessaires : sans elles, rien n'est écrit et ``None`` est
    rendu. L'outcome n'est jamais déduit de la recommandation ou de l'abstention :
    seul un booléen explicitement fourni (argument ou clé ``outcome`` /
    ``resultat_observe``) résout la prédiction. Sans identifiant fourni, la
    calibration en dérive un déterministe : un rejeu n'ajoute pas de doublon.
    """
    if decision_support is None:
        return None
    base = _base(decision_support)
    decision = _texte(decision_id) or _texte(base.get("decision_id"))
    if confidence is not None:
        confiance = confidence
    else:
        confiance = base.get("confidence")
        if confiance is None:
            confiance = base.get("confiance")
    if not decision or confiance is None:
        return None
    resultat = _outcome_explicite(base, outcome)
    identifiant = _texte(prediction_id) or calibration.identifiant_prediction(
        tenant, decision, confiance)
    prediction = calibration.lire(conn, tenant, identifiant)
    if prediction is None:
        return calibration.enregistrer(
            conn, tenant, id=identifiant, decision_id=decision,
            confidence=confiance, outcome=resultat)
    if prediction.decision_id != decision:
        raise calibration.CalibrationInvalide(
            f"prediction_id {identifiant!r} liée à la décision "
            f"{prediction.decision_id!r}, attendu {decision!r}")
    if resultat is None or prediction.outcome == resultat:
        return prediction
    if prediction.outcome is not None:
        raise calibration.CalibrationInvalide(
            f"outcome déjà résolu pour la prédiction {identifiant!r}")
    return calibration.resoudre(conn, tenant, identifiant, resultat)


def _base(decision_support: Any) -> dict:
    if isinstance(decision_support, Mapping):
        return dict(decision_support)
    as_dict = getattr(decision_support, "as_dict", None)
    if callable(as_dict):
        valeur = as_dict()
        if isinstance(valeur, Mapping):
            return dict(valeur)
    raise TypeError("decision_support : mapping attendu")


def decision_support_enrichi(
    decision_support: Any,
    *,
    options: Any = None,
    changements: Any = None,
    criteres: Any = (),
) -> dict:
    """Rend une copie enrichie du decision support, sans muter l'original.

    ``contrefactuel`` n'est calculé que si ``options`` est fourni ; autrement il
    vaut ``None``. Aucune option, condition ou recommandation n'est inventée.
    """
    enrichi = _base(decision_support)
    if options is not None:
        enrichi["contrefactuel"] = construire_contrefactuel(
            options, changements, criteres=criteres)
    else:
        enrichi["contrefactuel"] = None
    return enrichi
