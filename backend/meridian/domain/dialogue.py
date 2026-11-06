"""État de dialogue : ce qui reste actif entre deux messages.

Le Travail garde les messages pour l'interface ; cet état garde ce que le tour suivant doit
savoir sans relire tout le fil : sujet, entités, dernière réponse, dernier livrable,
questions ouvertes et corrections explicites.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

__all__ = ["EtatDialogue"]

ACTES = ("question", "suivi", "correction", "confirmation", "meta", "nouveau_sujet")


def _texte(valeur, maximum=2000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _textes(valeurs, maximum=240) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat = []
    for valeur in valeurs or ():
        texte = _texte(valeur, maximum)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


@dataclass(frozen=True)
class EtatDialogue:
    travail: str = ""
    acteur: str = ""
    interlocuteurs: tuple[str, ...] = ()
    sujet: str = ""
    entites: tuple[str, ...] = ()
    derniere_question: str = ""
    derniere_reponse: str = ""
    dernier_livrable: str = ""
    questions_ouvertes: tuple[str, ...] = ()
    corrections: tuple[str, ...] = ()
    version: int = 0

    def __post_init__(self):
        object.__setattr__(self, "travail", _texte(self.travail, 120))
        object.__setattr__(self, "acteur", _texte(self.acteur, 240))
        object.__setattr__(self, "interlocuteurs", _textes(self.interlocuteurs, 240))
        object.__setattr__(self, "sujet", _texte(self.sujet, 240))
        object.__setattr__(self, "entites", _textes(self.entites))
        object.__setattr__(self, "derniere_question", _texte(self.derniere_question, 2000))
        object.__setattr__(self, "derniere_reponse", _texte(self.derniere_reponse, 2000))
        object.__setattr__(self, "dernier_livrable", _texte(self.dernier_livrable, 240))
        object.__setattr__(self, "questions_ouvertes", _textes(self.questions_ouvertes, 500))
        object.__setattr__(self, "corrections", _textes(self.corrections, 500))
        object.__setattr__(self, "version", max(0, int(self.version)))

    def as_dict(self) -> dict:
        return {
            "travail": self.travail, "acteur": self.acteur,
            "interlocuteurs": list(self.interlocuteurs), "sujet": self.sujet,
            "entites": list(self.entites), "derniere_question": self.derniere_question,
            "derniere_reponse": self.derniere_reponse, "dernier_livrable": self.dernier_livrable,
            "questions_ouvertes": list(self.questions_ouvertes),
            "corrections": list(self.corrections), "version": self.version,
        }

    @classmethod
    def depuis_dict(cls, valeur: Mapping | None, *, travail: str = "", acteur: str = "") -> "EtatDialogue":
        if not isinstance(valeur, Mapping):
            return cls(travail=travail, acteur=acteur)
        return cls(
            travail=str(valeur.get("travail") or travail),
            acteur=str(valeur.get("acteur") or acteur),
            interlocuteurs=tuple(valeur.get("interlocuteurs") or ()),
            sujet=str(valeur.get("sujet") or ""),
            entites=tuple(valeur.get("entites") or ()),
            derniere_question=str(valeur.get("derniere_question") or ""),
            derniere_reponse=str(valeur.get("derniere_reponse") or ""),
            dernier_livrable=str(valeur.get("dernier_livrable") or ""),
            questions_ouvertes=tuple(valeur.get("questions_ouvertes") or ()),
            corrections=tuple(valeur.get("corrections") or ()),
            version=int(valeur.get("version") or 0),
        )

    def avec(self, **champs) -> "EtatDialogue":
        return replace(self, **champs, version=self.version + 1)
