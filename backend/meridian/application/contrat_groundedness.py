"""Contrat groundedness : la réponse porte l'état de vérification de ses citations.

Branché après ``contrat_preuve`` dans ``generer_tour``. Deux régimes :

- avec ``sources`` (portée du jumeau) : chaque citation code est résolue contre le
  dépôt au SHA — une citation fabriquée est signalée dans ``groundedness`` et dans
  un marqueur explicite de la réponse ;
- sans ``sources`` : les citations sont comptées et marquées ``non_verifiees`` —
  le système ne prétend jamais avoir vérifié ce qu'il n'a pas pu vérifier.

Même discipline que ``contrat_preuve`` : pur, sans réseau, sans base directe.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from meridian.application import groundedness

__all__ = ["appliquer"]

_MARQUEUR = (
    "\n\n**Citation non vérifiée** : {n} citation(s) de cette réponse n'ont pas pu être "
    "rattachées à un artefact réel et doivent être traitées comme non fondées."
)


def appliquer(reponse: Mapping[str, Any] | None, *, resoudre: Callable | None = None) -> dict:
    """Note les citations de la réponse ; signale les fabriquées et les non vérifiées.

    ``resoudre`` est un callable ``citation -> verdict`` construit par l'appelant
    (ex. ``connaissance.resoudre_citations(sources_du_jumeau)`` — l'adapter décide de la
    portée ; le contrat ne touche jamais les sources lui-même).
    """
    resultat = dict(reponse or {})
    texte = str(resultat.get("reponse") or "")
    if not texte.strip():
        return resultat
    rapport = groundedness.noter(texte, resoudre)
    if not rapport["total"]:
        return resultat
    resultat["groundedness"] = {
        "total": rapport["total"],
        "verifiees": rapport["verifiees"] if resoudre else None,
        "non_resolues": rapport["non_resolues"],
        "non_verifiees": rapport["total"] if not resoudre else 0,
    }
    if resoudre and rapport["non_resolues"]:
        resultat["reponse"] = texte.rstrip() + _MARQUEUR.format(n=rapport["non_resolues"])
    return resultat
