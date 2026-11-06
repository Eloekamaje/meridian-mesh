"""Évaluation déterministe d'un dossier de raisonnement.

Ce module ne juge pas la vérité d'une réponse : il mesure la présence des artefacts qui rendent une
décision défendable. Il sert aux tests de non-régression, au tableau de bord et à la capitalisation.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from meridian.domain import dossier_raisonnement as domaine

__all__ = ["evaluer"]


def _lire(dossier: Any, nom: str, defaut=None):
    if isinstance(dossier, Mapping):
        return dossier.get(nom, defaut)
    return getattr(dossier, nom, defaut)


def _liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return list(valeur)
    return [valeur]


def evaluer(dossier: Any) -> dict:
    """Rend des scores bornés, des constats et des leçons actionnables."""
    niveau = str(_lire(dossier, "niveau", "N0") or "N0")
    cadre = _lire(dossier, "cadre")
    options = _liste(_lire(dossier, "options"))
    critiques = _liste(_lire(dossier, "critiques"))
    validation = _liste(_lire(dossier, "validation"))
    gates = _liste(_lire(dossier, "gates"))
    risque = niveau in {"N3", "N4"}
    scores = {
        "cadrage": 1.0 if cadre else 0.0,
        "options": min(1.0, len(options) / 2) if risque else 1.0,
        "critique": 1.0 if critiques else (0.0 if risque else 1.0),
        "validation": 1.0 if validation else (0.0 if risque else 1.0),
        "gates": 1.0 if gates and not any(
            (g.get("statut") if isinstance(g, Mapping) else getattr(g, "statut", "")) == "echec"
            for g in gates) else 0.0,
    }
    for critique in critiques:
        findings = critique.get("findings") if isinstance(critique, Mapping) else getattr(critique, "findings", ())
        if any((f.get("severite") if isinstance(f, Mapping) else getattr(f, "severite", "")) in {"majeure", "critique"}
               for f in findings or ()):
            scores["critique"] = min(scores["critique"], 0.5)
    constats = []
    if risque and not cadre:
        constats.append("N3/N4 sans cadre")
    if risque and len(options) < 2:
        constats.append("moins de deux options")
    if risque and not critiques:
        constats.append("aucune critique")
    if risque and not validation:
        constats.append("aucun plan de validation")
    if any((g.get("statut") if isinstance(g, Mapping) else getattr(g, "statut", "")) == "echec" for g in gates):
        constats.append("gate bloquante")
    score = round(sum(scores.values()) / len(scores), 3)
    return {
        "niveau": niveau,
        "score": score,
        "ok": score >= 0.8 and not constats,
        "scores": {cle: round(valeur, 3) for cle, valeur in scores.items()},
        "constats": constats,
        "lecons": [f"corriger : {constat}" for constat in constats],
    }
