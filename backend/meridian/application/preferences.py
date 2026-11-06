"""Projection des préférences dans le prompt, sans les confondre avec des instructions de sécurité."""
from __future__ import annotations

from meridian.domain.preferences import Preferences

__all__ = ["depuis_doc", "lignes_prompt"]


def depuis_doc(doc) -> Preferences:
    if hasattr(doc, "as_dict"):
        doc = doc.as_dict()
    return Preferences.depuis_dict(doc)


def lignes_prompt(preferences) -> tuple[str, ...]:
    p = depuis_doc(preferences)
    lignes = [f"- Ton demandé : {p.ton}", f"- Langue : {p.langue}",
              f"- Longueur : {p.longueur}"]
    if not p.suggestions:
        lignes.append("- Ne propose pas de prochaines étapes non demandées.")
    return tuple(lignes)
