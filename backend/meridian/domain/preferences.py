"""Préférences de conversation : ton, langue, longueur et suggestions.

Elles sont déclaratives et ne donnent aucun droit : elles orientent la forme de la réponse,
jamais l'autorité ou les preuves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = ["Preferences", "TONS", "LONGUEURS"]

TONS = ("direct", "pedagogique", "chaleureux")
LONGUEURS = ("concis", "moyenne", "detaillee")


def _texte(valeur, maximum=40) -> str:
    return " ".join(str(valeur or "").split())[:maximum].lower()


@dataclass(frozen=True)
class Preferences:
    ton: str = "direct"
    langue: str = "fr"
    longueur: str = "moyenne"
    suggestions: bool = True

    def __post_init__(self):
        ton = _texte(self.ton)
        longueur = _texte(self.longueur)
        object.__setattr__(self, "ton", ton if ton in TONS else "direct")
        object.__setattr__(self, "langue", _texte(self.langue) or "fr")
        object.__setattr__(self, "longueur", longueur if longueur in LONGUEURS else "moyenne")
        object.__setattr__(self, "suggestions", bool(self.suggestions))

    def as_dict(self) -> dict:
        return {"ton": self.ton, "langue": self.langue, "longueur": self.longueur,
                "suggestions": self.suggestions}

    @classmethod
    def depuis_dict(cls, valeur: Mapping | None) -> "Preferences":
        if not isinstance(valeur, Mapping):
            return cls()
        return cls(ton=valeur.get("ton") or "direct", langue=valeur.get("langue") or "fr",
                   longueur=valeur.get("longueur") or "moyenne",
                   suggestions=valeur.get("suggestions", True))
