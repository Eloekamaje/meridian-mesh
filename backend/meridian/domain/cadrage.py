"""Cadrage conversationnel : un état explicite, des slots et une question à la fois.

Le cadrage n'est pas reconstruit à partir du texte du dernier message. Chaque information
demandée est un slot identifié ; une question porte l'identifiant du slot qu'elle cherche à
remplir. Une réponse ne remplit donc jamais « tous les champs » par accident.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

__all__ = [
    "SLOTS",
    "CadrageConversationnel",
    "QuestionCadrage",
    "SlotCadrage",
]

SLOTS = (
    "existant_ou_cible",
    "perimetre",
    "utilisateurs",
    "contraintes",
    "criteres_succes",
    "options_ecartees",
)
STATUTS_SLOT = ("absent", "infere", "confirme")
STATUTS_CADRAGE = ("en_cours", "en_attente", "pret")


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


@dataclass(frozen=True)
class SlotCadrage:
    id: str
    valeur: str = ""
    statut: str = "absent"
    source: str = ""
    question_id: str = ""

    def __post_init__(self):
        if self.id not in SLOTS:
            raise ValueError(f"slot de cadrage inconnu : {self.id!r}")
        if self.statut not in STATUTS_SLOT:
            raise ValueError(f"statut de slot inconnu : {self.statut!r}")
        object.__setattr__(self, "valeur", _texte(self.valeur))
        object.__setattr__(self, "source", _texte(self.source, 40))
        object.__setattr__(self, "question_id", _texte(self.question_id, 40))

    @property
    def rempli(self) -> bool:
        return bool(self.valeur)

    def as_dict(self) -> dict:
        return {"id": self.id, "valeur": self.valeur, "statut": self.statut,
                "source": self.source, "question_id": self.question_id}

    @classmethod
    def depuis_dict(cls, valeur: Mapping) -> "SlotCadrage":
        return cls(
            id=str(valeur.get("id") or ""), valeur=valeur.get("valeur") or "",
            statut=valeur.get("statut") or "absent", source=valeur.get("source") or "",
            question_id=valeur.get("question_id") or "",
        )


@dataclass(frozen=True)
class QuestionCadrage:
    id: str
    slot: str
    texte: str

    def __post_init__(self):
        if self.slot not in SLOTS:
            raise ValueError(f"slot de question inconnu : {self.slot!r}")
        object.__setattr__(self, "id", _texte(self.id, 40))
        object.__setattr__(self, "texte", _texte(self.texte, 1000))

    def as_dict(self) -> dict:
        return {"id": self.id, "slot": self.slot, "texte": self.texte}

    @classmethod
    def depuis_dict(cls, valeur: Mapping) -> "QuestionCadrage":
        return cls(id=str(valeur.get("id") or ""), slot=str(valeur.get("slot") or ""),
                   texte=str(valeur.get("texte") or ""))


@dataclass(frozen=True)
class CadrageConversationnel:
    question: str
    objet: str = ""
    type_livrable: str = "reponse"
    slots: tuple[SlotCadrage, ...] = ()
    question_en_attente: QuestionCadrage | None = None
    posees: int = 0
    statut: str = "en_cours"

    def __post_init__(self):
        question = _texte(self.question)
        if not question:
            raise ValueError("cadrage : question obligatoire")
        if self.statut not in STATUTS_CADRAGE:
            raise ValueError(f"statut de cadrage inconnu : {self.statut!r}")
        ids = [slot.id for slot in self.slots]
        if len(ids) != len(set(ids)):
            raise ValueError("cadrage : slots dupliqués")
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "objet", _texte(self.objet, 240))
        object.__setattr__(self, "type_livrable", _texte(self.type_livrable, 40) or "reponse")
        object.__setattr__(self, "slots", tuple(self.slots))
        object.__setattr__(self, "posees", max(0, int(self.posees)))

    def slot(self, identifiant: str) -> SlotCadrage:
        for slot in self.slots:
            if slot.id == identifiant:
                return slot
        return SlotCadrage(id=identifiant)

    def avec_slot(self, identifiant: str, valeur: str, *, source: str = "utilisateur",
                  statut: str = "confirme", question_id: str = "") -> "CadrageConversationnel":
        nouveaux = []
        trouve = False
        for slot in self.slots:
            if slot.id == identifiant:
                nouveaux.append(replace(slot, valeur=_texte(valeur), statut=statut,
                                        source=source, question_id=question_id))
                trouve = True
            else:
                nouveaux.append(slot)
        if not trouve:
            nouveaux.append(SlotCadrage(id=identifiant, valeur=valeur, statut=statut,
                                        source=source, question_id=question_id))
        return replace(self, slots=tuple(nouveaux))

    def avec_question(self, question: QuestionCadrage | None, *,
                      posee: bool = False) -> "CadrageConversationnel":
        return replace(self, question_en_attente=question,
                       posees=self.posees + (1 if posee else 0))

    def contexte(self) -> dict:
        """Les valeurs confirmées/inférées, dans le vocabulaire attendu par le noyau."""
        slots = {slot.id: slot.valeur for slot in self.slots if slot.rempli}
        return {
            "sans_questions": True,
            "objectif": self.question,
            "objet": self.objet,
            "type_livrable": self.type_livrable,
            "perimetre": slots.get("perimetre", ""),
            "contraintes": [slots["contraintes"]] if slots.get("contraintes") else [],
            "criteres_succes": [slots["criteres_succes"]] if slots.get("criteres_succes") else [],
            "utilisateurs": [slots["utilisateurs"]] if slots.get("utilisateurs") else [],
            "options_ecartees": [slots["options_ecartees"]] if slots.get("options_ecartees") else [],
            "reponses_utilisateur": [slot.valeur for slot in self.slots if slot.rempli],
            "existant_ou_cible": slots.get("existant_ou_cible", ""),
        }

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "objet": self.objet,
            "type_livrable": self.type_livrable,
            "slots": [slot.as_dict() for slot in self.slots],
            "question_en_attente": self.question_en_attente.as_dict() if self.question_en_attente else None,
            "posees": self.posees,
            "statut": self.statut,
        }

    @classmethod
    def depuis_dict(cls, valeur: Mapping | None) -> "CadrageConversationnel | None":
        if not isinstance(valeur, Mapping) or not valeur.get("question"):
            return None
        slots = tuple(
            SlotCadrage.depuis_dict(item)
            for item in valeur.get("slots") or ()
            if isinstance(item, Mapping) and item.get("id")
        )
        question = valeur.get("question_en_attente")
        return cls(
            question=str(valeur.get("question")), objet=str(valeur.get("objet") or ""),
            type_livrable=str(valeur.get("type_livrable") or "reponse"),
            slots=slots,
            question_en_attente=QuestionCadrage.depuis_dict(question) if isinstance(question, Mapping) else None,
            posees=int(valeur.get("posees") or 0), statut=str(valeur.get("statut") or "en_cours"),
        )
