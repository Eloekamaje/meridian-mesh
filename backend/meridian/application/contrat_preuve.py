"""Contrat de preuve d'un tour : citer, ou déclarer explicitement que la liste n'est pas sourcée.

Flore peut répondre sans citer lorsqu'elle explique une notion générale. En revanche, une
énumération technique présentée comme un fait d'entreprise ne doit pas rester silencieusement
sans preuve. Ce module est déterministe et conservateur : il n'ajoute une limite que devant
une liste de plusieurs éléments et en l'absence de toute citation.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

__all__ = ["APPLIQUER", "LIMITE", "appliquer"]

APPLIQUER = "contrat_preuve"
LIMITE = "limite_preuve"

_RE_LISTE = re.compile(r"(?m)^\s*(?:[-*]\s+|\d+[.)]\s+)\S+")
_RE_CITATION = re.compile(
    r"(#L\d+|#preuve-|git://|\[\d+\]|"
    r"[A-Za-z0-9_./-]+\.[A-Za-z]\w*#L\d+|"
    r"\bc:[a-z0-9-]+\b|\br:[a-z0-9-]+\b)",
    re.IGNORECASE,
)
_RE_LIMITE = re.compile(
    r"(limite de preuve|non reli[ée]|non sourc[ée]|preuve absente|"
    r"sans preuve|non v[ée]rifi[ée])",
    re.IGNORECASE,
)
_COMPORTEMENTS_SANS_PREUVE = {"refuser", "clarifier", "signaler"}


def appliquer(reponse: Mapping[str, Any] | None) -> dict:
    """Ajoute une limite explicite si une liste factuelle n'est pas sourcée."""
    resultat = dict(reponse or {})
    if resultat.get(APPLIQUER):
        return resultat
    if str(resultat.get("comportement") or "") in _COMPORTEMENTS_SANS_PREUVE:
        resultat[APPLIQUER] = "non_applicable"
        return resultat
    preuves = resultat.get("preuves") or ()
    texte = str(resultat.get("reponse") or "")
    if preuves or _RE_CITATION.search(texte) or _RE_LIMITE.search(texte):
        resultat[APPLIQUER] = "conforme"
        return resultat
    if len(_RE_LISTE.findall(texte)) < 3:
        resultat[APPLIQUER] = "non_applicable"
        return resultat
    resultat["reponse"] = (
        texte.rstrip()
        + "\n\n**Limite de preuve** : cette liste n'est pas reliée à une preuve "
          "localisée dans ce tour ; elle doit être vérifiée avant d'être utilisée "
          "comme un fait d'entreprise."
    )
    resultat[LIMITE] = True
    resultat[APPLIQUER] = "limite_ajoutee"
    return resultat
