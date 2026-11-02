"""Contrat d'artefact affichable dans le chat et le Canvas.

Un artefact est une donnée structurée, jamais du HTML arbitraire. Le rendu est choisi par `type` ;
le serveur fournit une version, un hash et une provenance pour permettre le rejeu et l'export.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

VERSION = "1.0"
TYPES = (
    "planification.capacite", "planification.prevision", "planification.budget",
    "planification.alertes", "planification.dependances", "planification.gantt",
    "planification.serie", "document.markdown", "table", "mermaid", "json", "svg",
)


class ArtefactInvalide(ValueError):
    """Le type ou la charge de l'artefact ne respecte pas le contrat."""


def _hash(donnees: Any) -> str:
    return hashlib.sha256(json.dumps(donnees, sort_keys=True, default=str,
                                     ensure_ascii=False).encode()).hexdigest()


def envelopper(type_: str, titre: str, donnees: dict[str, Any] | None = None, *,
               source: str = "flore", version: str = VERSION,
               fallback: str = "json") -> dict[str, Any]:
    """Construit un artefact canonique ; les données restent à la racine pour les renderers existants."""
    if type_ not in TYPES:
        raise ArtefactInvalide(f"type d'artefact inconnu : {type_!r}")
    if not str(titre or "").strip():
        raise ArtefactInvalide("titre d'artefact requis")
    charge = dict(donnees or {})
    charge.pop("type", None)
    charge.pop("hash", None)
    base = {"type": type_, "titre": str(titre)[:200], "version": version, "source": source,
            "fallback": fallback}
    empreinte = _hash({**base, "donnees": charge})
    return {**charge, **base, "hash": empreinte, "artefact_id": empreinte[:24]}


def valider(artefact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artefact, dict):
        raise ArtefactInvalide("artefact : objet attendu")
    type_ = str(artefact.get("type") or "")
    if type_ not in TYPES:
        raise ArtefactInvalide(f"type d'artefact inconnu : {type_!r}")
    if not str(artefact.get("titre") or "").strip():
        raise ArtefactInvalide("titre d'artefact requis")
    if type_ == "svg":
        contenu = str(artefact.get("svg") or "")
        debut = contenu.lstrip()
        if not (debut.startswith("<svg") or (debut.startswith("<?xml") and "<svg" in debut[:500])) \
                or len(contenu) > 2_000_000:
            raise ArtefactInvalide("artefact SVG invalide ou trop volumineux")
        if any(marqueur in contenu.lower() for marqueur in ("<script", "onload=", "javascript:")):
            raise ArtefactInvalide("artefact SVG exécutable refusé")
    if len(json.dumps(artefact, default=str, ensure_ascii=False)) > 2_000_000:
        raise ArtefactInvalide("artefact trop volumineux")
    return dict(artefact)
