"""Mapping legacy partagé par la migration C0 et le pont live C1.

La même valeur `poursuivie` doit produire `DECIDED` dans les deux chemins, et `critique` doit
produire `HAUTE`. Ce module est pur et ne dépend d'aucun adaptateur.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

journal = logging.getLogger("meridian.mapping_legacy")

__all__ = [
    "CHAMPS_INITIATIVE",
    "CHAMPS_SITUATION",
    "PRIORITES",
    "STATUTS_INITIATIVE",
    "STATUTS_SITUATION",
    "cle",
    "code_migration",
    "priorite",
    "statut_initiative",
    "statut_situation",
]

# Champs legacy recopiés dans `donnees` (liste fermée, jamais le document entier).
CHAMPS_SITUATION = (
    "resume", "description", "question", "nature", "type", "verbe", "score", "detectee",
    "indicateurs", "decouverte_quoi", "decouverte_pourquoi", "reste_a_comprendre",
    "decisions_attendues", "chronologie", "hypotheses", "contributions", "preuves", "synthese",
    "actions_proposees", "opportunite", "decidee_le", "relation_id", "statut_legacy",
    "priorite_legacy",
)
CHAMPS_INITIATIVE = (
    "niveau", "genre", "declencheur", "raison", "quand", "periode", "perimetre", "preuves",
    "confiance", "impact", "destinataire", "pourquoi_vous", "attendu", "travail_titre",
    "options", "autonomie", "interruption", "reponse", "urgence", "travail_id",
    "jumeau_cible", "decision_id", "decision_ref", "situation_id", "investigation_id",
    "case_id", "source",
)


def cle(valeur: Any) -> str:
    """Clé de comparaison : accents retirés, casse abaissée, séparateurs normalisés."""
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


STATUTS_SITUATION = {
    "active": "CANDIDATE",
    "candidate": "CANDIDATE",
    "nouveau": "CANDIDATE",
    "nouvelle": "CANDIDATE",
    "en observation": "OBSERVING",
    "observation": "OBSERVING",
    "observing": "OBSERVING",
    "surveillee": "WATCHED",
    "surveillance": "WATCHED",
    "watched": "WATCHED",
    "en investigation": "INVESTIGATING",
    "investigation": "INVESTIGATING",
    "investigating": "INVESTIGATING",
    "qualifiee": "QUALIFIED",
    "qualified": "QUALIFIED",
    "decidee": "DECIDED",
    "decide": "DECIDED",
    "decided": "DECIDED",
    "tranchee": "DECIDED",
    "tranche": "DECIDED",
    "poursuivie": "DECIDED",
    "poursuit": "DECIDED",
    "reportee": "DEFERRED",
    "deferred": "DEFERRED",
    "ecartee": "DISMISSED",
    "classee": "DISMISSED",
    "ignoree": "DISMISSED",
    "rejetee": "DISMISSED",
    "rejete": "DISMISSED",
    "dismissed": "DISMISSED",
    "rejected": "DISMISSED",
    "archivee": "ARCHIVED",
    "archive": "ARCHIVED",
    "archived": "ARCHIVED",
}

STATUTS_INITIATIVE = {
    "en attente": "PROPOSED",
    "proposee": "PROPOSED",
    "propose": "PROPOSED",
    "proposed": "PROPOSED",
    "acceptee": "PLANNED",
    "accepte": "PLANNED",
    "accepted": "PLANNED",
    "suivi": "PLANNED",
    "suivie": "PLANNED",
    "suivre": "PLANNED",
    "refusee": "DISMISSED",
    "refuse": "DISMISSED",
    "rejetee": "DISMISSED",
    "rejete": "DISMISSED",
    "rejected": "DISMISSED",
    "en cours": "IN_PROGRESS",
    "demarree": "IN_PROGRESS",
    "started": "IN_PROGRESS",
    "active": "IN_PROGRESS",
    "terminee": "COMPLETED",
    "termine": "COMPLETED",
    "completed": "COMPLETED",
    "close": "COMPLETED",
    "cloturee": "COMPLETED",
    "annulee": "CANCELLED",
    "annule": "CANCELLED",
    "cancelled": "CANCELLED",
    "en pause": "SUSPENDED",
    "pause": "SUSPENDED",
    "suspended": "SUSPENDED",
}

PRIORITES = {
    "critique": "HAUTE",
    "critical": "HAUTE",
    "haute": "HAUTE",
    "high": "HAUTE",
    "elevee": "HAUTE",
    "eleve": "HAUTE",
    "urgente": "HAUTE",
    "urgent": "HAUTE",
    "p1": "HAUTE",
    "normale": "MOYENNE",
    "normal": "MOYENNE",
    "moyenne": "MOYENNE",
    "moyen": "MOYENNE",
    "medium": "MOYENNE",
    "p2": "MOYENNE",
    "basse": "BASSE",
    "bas": "BASSE",
    "low": "BASSE",
    "faible": "BASSE",
    "p3": "BASSE",
}

_ANCIENNE_ECHELLE = {
    "p0": "CRITIQUE",
    "p1": "HAUTE",
    "p2": "MOYENNE",
    "p3": "BASSE",
    "p4": "BASSE",
}


def code_migration(valeur: Any) -> str:
    """Code legacy stable pour les valeurs sans équivalent canonique."""
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.upper()


def _code_deja_canonique(valeur: Any) -> str:
    original = str(valeur or "").strip()
    if original and original == original.upper() and re.fullmatch(r"[A-Z][A-Z0-9_]*", original):
        return original
    return ""


def statut_situation(valeur: Any, defaut: str = "CANDIDATE") -> str:
    brute = cle(valeur)
    if not brute:
        return defaut
    if brute in STATUTS_SITUATION:
        return STATUTS_SITUATION[brute]
    code = _code_deja_canonique(valeur)
    if not code:
        journal.debug("statut de situation legacy inconnu : %r", valeur)
    return code or defaut


def statut_initiative(valeur: Any, defaut: str = "PROPOSED") -> str:
    brute = cle(valeur)
    if not brute:
        return defaut
    if brute in STATUTS_INITIATIVE:
        return STATUTS_INITIATIVE[brute]
    code = _code_deja_canonique(valeur)
    if not code:
        journal.debug("statut d'initiative legacy inconnu : %r", valeur)
    return code or defaut


def priorite(valeur: Any, defaut: str = "MOYENNE") -> str:
    brute = cle(valeur)
    if not brute:
        return defaut
    if brute in PRIORITES:
        return PRIORITES[brute]
    if brute in _ANCIENNE_ECHELLE:
        return _ANCIENNE_ECHELLE[brute]
    journal.debug("priorité legacy inconnue : %r", valeur)
    return defaut
