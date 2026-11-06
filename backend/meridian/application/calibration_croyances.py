"""Calibration des croyances : résolution par outcome et mesure de Brier.

La résolution produit une nouvelle croyance et une `BeliefRevision` ; elle ne modifie pas une
croyance en place. Le Brier est une mesure de qualité, pas une promotion de vérité.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

from meridian.domain import dossier_raisonnement as dossier_domaine
from meridian.domain import epistemie as domaine

__all__ = ["brier", "resoudre", "resoudre_dans_dossier"]


def brier(predictions) -> float | None:
    valeurs = []
    for prediction in predictions or ():
        if isinstance(prediction, Mapping):
            outcome = prediction.get("outcome")
            confiance = prediction.get("confidence", prediction.get("confiance"))
        else:
            outcome = getattr(prediction, "outcome", None)
            confiance = getattr(prediction, "confidence", getattr(prediction, "confiance", None))
        if outcome is None or confiance is None:
            continue
        try:
            valeurs.append((float(confiance) - (1.0 if bool(outcome) else 0.0)) ** 2)
        except (TypeError, ValueError):
            continue
    return round(sum(valeurs) / len(valeurs), 4) if valeurs else None


def resoudre(
    belief: domaine.Belief,
    *,
    outcome: bool,
    motif: str,
    acteur: str = "",
    preuve: str = "",
):
    """Résout une croyance par un outcome booléen ; rend (nouvelle croyance, révision)."""
    if not isinstance(outcome, bool):
        raise ValueError("outcome doit être un booléen")
    if not str(motif or "").strip():
        raise ValueError("motif de résolution obligatoire")
    preuves = tuple(dict.fromkeys((*belief.preuves, *( (preuve,) if preuve else () ))))
    nouveau = domaine.Belief(
        sujet=belief.sujet, predicat=belief.predicat, objet=belief.objet,
        mode="OBSERVED", statut="CONNU" if outcome else "CONTREDIT",
        confiance=1.0 if outcome else 0.0,
        preuves=preuves, sources=belief.sources, twins=belief.twins,
        fraicheur=belief.fraicheur, portee=belief.portee,
        conditions_retournement=belief.conditions_retournement,
    )
    revision = domaine.BeliefRevision(
        belief_id=belief.id,
        ancien_statut=belief.statut,
        nouveau_statut=nouveau.statut,
        motif=str(motif),
        preuves_ajoutees=(preuve,) if preuve else (),
        acteur=acteur,
    )
    return nouveau, revision


def resoudre_dans_dossier(
    dossier: dossier_domaine.DossierRaisonnement,
    belief_id: str,
    *,
    outcome: bool,
    motif: str,
    acteur: str = "",
    preuve: str = "",
) -> dossier_domaine.DossierRaisonnement:
    """Remplace une croyance et conserve la trace de la révision dans le dossier."""
    beliefs = []
    trouvee = None
    for belief in dossier.beliefs:
        if belief.id == belief_id:
            trouvee = belief
            beliefs.append(belief)
        else:
            beliefs.append(belief)
    if trouvee is None:
        raise LookupError("croyance introuvable")
    nouvelle, revision = resoudre(
        trouvee, outcome=outcome, motif=motif, acteur=acteur, preuve=preuve)
    dossier.beliefs = tuple(nouvelle if b.id == belief_id else b for b in beliefs)
    dossier.revisions = (*dossier.revisions, revision)
    return dossier
