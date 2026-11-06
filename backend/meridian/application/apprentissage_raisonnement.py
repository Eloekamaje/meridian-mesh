"""Capitalisation d'un dossier de raisonnement en Learning proposé.

Le noyau ne promeut pas un Learning dans le canonique : il produit une proposition traçable, reliée
au dossier et à son évaluation, qu'un humain ou la boucle Outcome peut reprendre.
"""
from __future__ import annotations

from collections.abc import Mapping

from meridian.application import evaluation_raisonnement

__all__ = ["proposer"]


def _lire(dossier, nom, defaut=None):
    if isinstance(dossier, Mapping):
        return dossier.get(nom, defaut)
    return getattr(dossier, nom, defaut)


def proposer(dossier, *, retour: str | None = None) -> dict | None:
    """Rend un Learning proposé, ou None si le dossier n'a rien de réutilisable."""
    evaluation = evaluation_raisonnement.evaluer(dossier)
    constats = list(_lire(dossier, "constats", ()) or ())
    lecons = list(evaluation.get("lecons") or ())
    if not constats and not lecons and not retour:
        return None
    enonce = retour or (lecons[0] if lecons else "Capitaliser le dossier de raisonnement")
    demande = _lire(dossier, "demande")
    question = _lire(dossier, "question", "")
    conditions = []
    if demande is not None and getattr(demande, "sensibilite", ()):
        conditions.append("revue de risque requise pour le domaine sensible")
    if evaluation.get("constats"):
        conditions.extend(f"corriger : {constat}" for constat in evaluation["constats"])
    return {
        "type": "LEARNING",
        "statut": "PROPOSED",
        "mode": "INFERRED",
        "titre": enonce[:240],
        "enonce": enonce[:4000],
        "resume": enonce[:4000],
        "scope": _lire(dossier, "tenant", "") or "",
        "conditions_reutilisation": conditions,
        "source": {
            "dossier_id": _lire(dossier, "id", ""),
            "trace_id": _lire(dossier, "trace_id", ""),
            "question": question,
            "score": evaluation.get("score"),
        },
        "evaluation": evaluation,
    }
