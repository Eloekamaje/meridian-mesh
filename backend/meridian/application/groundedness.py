"""Groundedness : chaque citation d'une réponse est vérifiée contre l'artefact réel.

Une citation n'est pas un format — c'est une promesse : le fichier existe au SHA ingéré,
les lignes citées existent, la pièce existe. Ce module extrait les citations du texte
(RE_CITATION code, RE_CITATION_SOURCE document, RE_CITATION_PIECE pièce jointe) et les
résout via un résolveur injecté — aucun modèle, aucun réseau, déterministe.

Verdicts : ``resolu`` (l'artefact existe et porte les lignes citées), ``non_resolu``
(citation fabriquée : dépôt inconnu, fichier absent, lignes hors bornes), ``perimee``
(la citation résout mais la source est déclarée périmée), ``hors_perimetre`` (la source
n'est pas dans la portée autorisée), ``indetermine`` (aucun résolveur pour ce type —
compté à part, jamais comme un succès).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
import re
from typing import Any

# application/ ne dépend pas des adapters (test_architecture) : les motifs de citation
# sont répliqués ici. Le résolveur contre les dépôts vit dans
# adapters/outbound/postgres/connaissance.py : `resoudre_citations`.

__all__ = [
    "Citation",
    "RESOLU", "NON_RESOLU", "PERIMEE", "HORS_PERIMETRE", "INDETERMINE",
    "extraire",
    "noter",
]

RESOLU, NON_RESOLU, PERIMEE, HORS_PERIMETRE, INDETERMINE = (
    "resolu", "non_resolu", "perimee", "hors_perimetre", "indetermine")

journal = logging.getLogger("meridian.groundedness")

# Répliques des motifs canoniques (adapters/postgres/connaissance.py,
# adapters/connectors/lecteurs.py) — toute divergence est un bug, ne pas les modifier
# indépendamment.
RE_CITATION = re.compile(
    r"(?:git://(?P<depot_long>[^\s@`]+)@[0-9a-f]+:|(?<![\w/:.-])(?:(?P<depot>[A-Za-z0-9_.-]+):(?!//))?)"
    r"(?P<chemin>[A-Za-z_][\w.-]*(?:/[\w.-]+)*\.[A-Za-z]\w*)#L(?P<debut>\d+)(?:-L(?P<fin>\d+))?")
RE_CITATION_SOURCE = re.compile(
    r"(?P<systeme>(?!git)[a-z]+)://(?P<espace>[\w.-]+)/(?P<ref>[\w.-]+)@(?P<version>[\w.-]+)"
    r"#L(?P<debut>\d+)(?:-L(?P<fin>\d+))?")
_RE_CITATION_PIECE = re.compile(
    r"pi[eè]ce[:\s]+([A-Za-z0-9_-]+)#(table:[^\n#]*?(?=(?:\s+pi[eè]ce[:\s])|\n|$)|[A-Za-z0-9_-]+)",
    re.IGNORECASE)


class Citation(dict):
    """Une citation extraite : type, texte brut et champs propres au type."""


def extraire(texte: Any) -> list[dict]:
    """Les citations du texte, dédupliquées par position, dans l'ordre d'apparition."""
    trouvees: list[dict] = []
    for m in RE_CITATION.finditer(str(texte or "")):
        depot, chemin, debut, fin = (
            m.group("depot_long") or m.group("depot") or "",
            m.group("chemin"), int(m.group("debut")),
            int(m.group("fin") or m.group("debut")))
        trouvees.append({
            "type": "code", "brut": m.group(0), "depot": depot,
            "chemin": chemin, "debut": debut, "fin": fin,
        })
    for m in RE_CITATION_SOURCE.finditer(str(texte or "")):
        trouvees.append({
            "type": "source", "brut": m.group(0), "systeme": m.group("systeme"),
            "espace": m.group("espace"), "ref": m.group("ref"),
            "version": m.group("version"),
            "debut": int(m.group("debut")), "fin": int(m.group("fin") or m.group("debut")),
        })
    for m in _RE_CITATION_PIECE.finditer(str(texte or "")):
        trouvees.append({
            "type": "piece", "brut": m.group(0), "piece_id": m.group(1),
            "section": m.group(2),
        })
    return trouvees


def noter(texte: Any, resoudre: Callable[[dict], str] | None = None) -> dict:
    """Vérifie chaque citation du texte : la réponse est un brouillon jusqu'ici.

    ``non_resolues`` : citations fabriquées — le risque central du système « claims à
    preuves ». ``indetermines`` : types sans résolveur — ni succès ni échec.
    """
    citations = extraire(texte)
    detail: list[dict] = []
    compte = {RESOLU: 0, NON_RESOLU: 0, PERIMEE: 0, HORS_PERIMETRE: 0, INDETERMINE: 0}
    for cite in citations:
        verdict = resoudre(cite) if resoudre else INDETERMINE
        if verdict not in compte:
            verdict = INDETERMINE
        compte[verdict] += 1
        detail.append({"verdict": verdict, **cite})
    resolues = compte[RESOLU]
    non_resolues = compte[NON_RESOLU]
    base = resolues + non_resolues + compte[PERIMEE] + compte[HORS_PERIMETRE]
    return {
        "total": len(citations),
        "verifiees": resolues,
        "non_resolues": non_resolues,
        "perimees": compte[PERIMEE],
        "hors_perimetre": compte[HORS_PERIMETRE],
        "indetermines": compte[INDETERMINE],
        "groundedness": round(resolues / base, 4) if base else (1.0 if not citations else None),
        "detail": detail,
    }
