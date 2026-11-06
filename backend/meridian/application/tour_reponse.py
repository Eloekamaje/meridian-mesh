"""Contrat de réponse d'un tour : une seule enveloppe pour tous les chemins.

Les adapters peuvent produire des réponses partielles (sélection explicite, orchestrateur,
scénario ou repli). Ce module ne décide rien : il garantit la même forme observable et laisse
les valeurs métier intactes.
"""
from __future__ import annotations

from collections.abc import Mapping

__all__ = ["CLES", "enveloppe", "normaliser"]

CLES = (
    "comportement", "reponse", "preuves", "contributions", "jumeaux_participants",
    "indicateurs", "raisonnement", "raisonnement_statut", "orchestration",
    "questions", "suggestions", "action", "resolution", "diagrammes", "schemas",
    "hors_perimetre",
)
_DEFAUTS = {
    "comportement": "repondre", "reponse": "", "preuves": [], "contributions": [],
    "jumeaux_participants": [], "questions": [], "suggestions": [],
}


def _valeur(valeur, defaut):
    if valeur is None:
        return defaut
    return valeur


def normaliser(reponse: Mapping | None) -> dict:
    """Complète les clés manquantes sans inventer de contenu métier."""
    source = dict(reponse or {})
    resultat = {}
    for cle in CLES:
        if cle in source:
            resultat[cle] = source[cle]
        elif cle in _DEFAUTS:
            resultat[cle] = list(_DEFAUTS[cle]) if isinstance(_DEFAUTS[cle], list) else _DEFAUTS[cle]
        else:
            resultat[cle] = None
    for cle, valeur in source.items():
        if cle not in resultat:
            resultat[cle] = valeur
    return resultat


def enveloppe(reponse: Mapping | None, *, origine: str = "") -> dict:
    """Normalise et conserve l'origine si elle est fournie."""
    resultat = normaliser(reponse)
    if origine:
        resultat.setdefault("origine", origine)
    return resultat
