"""État de tour unique : dialogue + cadrage, versionné et rétrocompatible.

Le module ne lit ni n'écrit Mongo : il compose les états déjà sérialisés dans un Travail.
Les adapters peuvent ainsi lire ``etat_tour`` quand il existe et retomber sur les champs
historiques ``dialogue`` / ``cadrage_conversationnel`` pour les Travaux anciens.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from meridian.application import cadrage_conversationnel as cadrage_service
from meridian.application import dialogue as dialogue_service
from meridian.domain.cadrage import CadrageConversationnel
from meridian.domain.dialogue import EtatDialogue

__all__ = ["SCHEMA_VERSION", "EtatTour"]

SCHEMA_VERSION = 1


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, dict) else {}


@dataclass(frozen=True)
class EtatTour:
    """Le seul état logique d'un tour : version, dialogue et cadrage éventuel."""

    version: int = 0
    dialogue: EtatDialogue = field(default_factory=EtatDialogue)
    cadrage: CadrageConversationnel | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        object.__setattr__(self, "version", max(0, int(self.version or 0)))
        object.__setattr__(self, "schema_version", int(self.schema_version or SCHEMA_VERSION))

    @classmethod
    def depuis_case(cls, case: dict | None) -> "EtatTour":
        """Lit ``etat_tour`` sinon reconstruit depuis les champs historiques."""
        case = case or {}
        brut = case.get("etat_tour")
        if isinstance(brut, dict) and int(brut.get("schema_version") or 0) == SCHEMA_VERSION:
            dialogue = EtatDialogue.depuis_dict(brut.get("dialogue"), travail=str(case.get("id") or ""))
            cadrage = _cadrage(brut.get("cadrage"))
            return cls(
                version=int(brut.get("version") or 0),
                dialogue=dialogue, cadrage=cadrage,
                schema_version=SCHEMA_VERSION)
        dialogue = dialogue_service.depuis_case(case, travail=str(case.get("id") or ""))
        cadrage = _cadrage(case.get("cadrage_conversationnel"))
        return cls(version=0, dialogue=dialogue, cadrage=cadrage)

    def avec(self, *, dialogue: EtatDialogue | None = None,
             cadrage: CadrageConversationnel | None = None) -> "EtatTour":
        return replace(
            self, version=self.version + 1,
            dialogue=dialogue if dialogue is not None else self.dialogue,
            cadrage=cadrage if cadrage is not None else self.cadrage,
        )

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "dialogue": self.dialogue.as_dict(),
            "cadrage": self.cadrage.as_dict() if self.cadrage is not None else None,
        }

    def a_poser_question(self) -> bool:
        return self.cadrage is not None and self.cadrage.question_en_attente is not None

    def question_en_attente(self):
        return self.cadrage.question_en_attente if self.cadrage is not None else None


def _cadrage(valeur) -> CadrageConversationnel | None:
    try:
        return cadrage_service.depuis_dict(valeur)
    except (TypeError, ValueError, KeyError):
        return None
