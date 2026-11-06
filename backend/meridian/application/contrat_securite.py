"""Refus déterministe des tentatives d'injection de prompt.

Une demande qui cherche explicitement à faire ignorer les consignes, à élargir un accès
ou à obtenir des preuves restreintes ne doit pas être envoyée au modèle : le refus est
court, stable et ne mentionne aucun détail interne. Les questions *sur* la sécurité
restent des questions normales.
"""
from __future__ import annotations

import re

__all__ = ["REFUS", "est_injection", "refuser_si_injection"]

REFUS = (
    "Je ne peux pas exécuter cette demande : elle cherche à contourner les règles "
    "d'accès. Je peux répondre dans votre périmètre autorisé ou expliquer la politique "
    "d'accès."
)

_RE_INJECTION = re.compile(
    r"(ignore[rz]?\s+(?:toutes?\s+)?(?:les|tes|vos)\s+"
    r"(?:consignes|instructions|r[eè]gles|politiques)|"
    r"oublie[rz]?\s+(?:les|tes|vos)\s+(?:consignes|instructions|r[eè]gles)|"
    r"(?:affiche|donne|montre|r[eé]v[eè]le)[rz]?(?:-moi)?\s+.*"
    r"(?:preuves?|donn[eé]es?|secrets?|cl[eé]s?|tokens?)\s+.*"
    r"(?:restreint|interdit|confidentiel|pas\s+acc[eè]s|sans\s+acc[eè]s)|"
    r"contourne[rz]?\s+(?:les|mes|tes|vos)\s+(?:r[eè]gles|consignes|politiques|acc[eè]s)|"
    r"jailbreak|prompt\s+system|system\s+prompt|mode\s+d[eé]veloppeur|"
    r"fais\s+comme\s+si\s+.*(?:admin|root|administrateur))",
    re.IGNORECASE,
)
_RE_QUESTION_SECURITE = re.compile(
    r"(comment|pourquoi|qu'est[- ]ce|explique|d[eé]cris|documente|teste|"
    r"politique|gouvernance|s[eé]curit[eé]|injection|prompt)",
    re.IGNORECASE,
)


def est_injection(question: str) -> bool:
    texte = str(question or "")
    if not _RE_INJECTION.search(texte):
        return False
    # Une question qui porte explicitement sur la sécurité n'est pas une tentative.
    if _RE_QUESTION_SECURITE.search(texte) and "?" in texte:
        return False
    return True


def refuser_si_injection(question: str) -> dict | None:
    if not est_injection(question):
        return None
    return {
        "comportement": "refuser",
        "reponse": REFUS,
        "preuves": [],
        "contributions": [],
        "jumeaux_participants": [],
        "contrat_securite": "refus_injection",
    }
