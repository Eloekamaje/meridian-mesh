"""Primitives épistémiques : question, présupposés, croyances, besoins et plan de sources.

Le dossier de raisonnement dit *comment* on traite une demande. Ces objets disent *ce qui est tenu
pour vrai, supposé, inconnu ou contredit* — et ce qui devra être révisé si une preuve change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Iterable, Mapping

__all__ = [
    "CROYANCES",
    "PRESUPPOSES",
    "Belief",
    "BeliefRevision",
    "EvidenceNeed",
    "Presupposition",
    "QuestionFrame",
    "SourcePlan",
]

PRESUPPOSES = ("CONNU", "SUPPOSE", "INCONNU", "CONTREDIT", "PERIME")
CROYANCES = PRESUPPOSES


def _texte(valeur, maximum=2000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _textes(valeurs, maximum=1000) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat = []
    for valeur in valeurs:
        texte = _texte(valeur, maximum)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _borne(valeur) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        nombre = 0.5
    return max(0.0, min(1.0, nombre))


def _identifiant(valeur, prefixe="ep") -> str:
    charge = _texte(valeur, 1000)
    digest = hashlib.sha256(charge.encode("utf-8")).hexdigest()[:16]
    return f"{prefixe}-{digest}"


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


@dataclass(frozen=True)
class Presupposition:
    texte: str
    statut: str = "INCONNU"
    materiel: bool = True
    preuves: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    twins: tuple[str, ...] = ()
    confiance: float = 0.0
    motif: str = ""
    id: str = ""

    def __post_init__(self):
        if not _texte(self.texte):
            raise ValueError("présupposé : texte obligatoire")
        statut = _texte(self.statut, 20).upper()
        if statut not in PRESUPPOSES:
            raise ValueError(f"statut de présupposé inconnu : {statut!r}")
        object.__setattr__(self, "texte", _texte(self.texte))
        object.__setattr__(self, "statut", statut)
        object.__setattr__(self, "materiel", bool(self.materiel))
        object.__setattr__(self, "preuves", _textes(self.preuves, 200))
        object.__setattr__(self, "sources", _textes(self.sources, 200))
        object.__setattr__(self, "twins", _textes(self.twins, 160))
        object.__setattr__(self, "confiance", _borne(self.confiance))
        object.__setattr__(self, "motif", _texte(self.motif, 1000))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(self.texte, "pres"))

    @property
    def bloquant(self) -> bool:
        return self.materiel and self.statut in {"INCONNU", "CONTREDIT", "PERIME"}

    def as_dict(self) -> dict:
        return {
            "id": self.id, "texte": self.texte, "statut": self.statut,
            "materiel": self.materiel, "preuves": list(self.preuves),
            "sources": list(self.sources), "twins": list(self.twins),
            "confiance": round(self.confiance, 3), "motif": self.motif,
        }


@dataclass(frozen=True)
class Belief:
    sujet: str
    predicat: str
    objet: str
    mode: str = "INFERRED"
    statut: str = "INCONNU"
    confiance: float = 0.0
    preuves: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    twins: tuple[str, ...] = ()
    fraicheur: str = ""
    portee: str = ""
    conditions_retournement: tuple[str, ...] = ()
    id: str = ""

    def __post_init__(self):
        for champ, valeur in (("sujet", self.sujet), ("predicat", self.predicat), ("objet", self.objet)):
            if not _texte(valeur):
                raise ValueError(f"croyance : {champ} obligatoire")
        statut = _texte(self.statut, 20).upper()
        if statut not in CROYANCES:
            raise ValueError(f"statut de croyance inconnu : {statut!r}")
        mode = _texte(self.mode, 20).upper()
        object.__setattr__(self, "sujet", _texte(self.sujet, 240))
        object.__setattr__(self, "predicat", _texte(self.predicat, 240))
        object.__setattr__(self, "objet", _texte(self.objet, 240))
        object.__setattr__(self, "mode", mode or "INFERRED")
        object.__setattr__(self, "statut", statut)
        object.__setattr__(self, "confiance", _borne(self.confiance))
        object.__setattr__(self, "preuves", _textes(self.preuves, 200))
        object.__setattr__(self, "sources", _textes(self.sources, 200))
        object.__setattr__(self, "twins", _textes(self.twins, 160))
        object.__setattr__(self, "fraicheur", _texte(self.fraicheur, 80))
        object.__setattr__(self, "portee", _texte(self.portee, 240))
        object.__setattr__(self, "conditions_retournement", _textes(self.conditions_retournement, 500))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(
            f"{self.sujet}:{self.predicat}:{self.objet}", "belief"))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "sujet": self.sujet, "predicat": self.predicat,
            "objet": self.objet, "mode": self.mode, "statut": self.statut,
            "confiance": round(self.confiance, 3), "preuves": list(self.preuves),
            "sources": list(self.sources), "twins": list(self.twins),
            "fraicheur": self.fraicheur, "portee": self.portee,
            "conditions_retournement": list(self.conditions_retournement),
        }


@dataclass(frozen=True)
class BeliefRevision:
    belief_id: str
    ancien_statut: str
    nouveau_statut: str
    motif: str
    preuves_ajoutees: tuple[str, ...] = ()
    preuves_retirees: tuple[str, ...] = ()
    acteur: str = ""
    date: str = ""

    def __post_init__(self):
        for champ, valeur in (("belief_id", self.belief_id), ("motif", self.motif)):
            if not _texte(valeur):
                raise ValueError(f"révision : {champ} obligatoire")
        object.__setattr__(self, "belief_id", _texte(self.belief_id, 80))
        object.__setattr__(self, "ancien_statut", _texte(self.ancien_statut, 20).upper())
        object.__setattr__(self, "nouveau_statut", _texte(self.nouveau_statut, 20).upper())
        object.__setattr__(self, "motif", _texte(self.motif, 1000))
        object.__setattr__(self, "preuves_ajoutees", _textes(self.preuves_ajoutees, 200))
        object.__setattr__(self, "preuves_retirees", _textes(self.preuves_retirees, 200))
        object.__setattr__(self, "acteur", _texte(self.acteur, 120))
        object.__setattr__(self, "date", _texte(self.date, 80))

    def as_dict(self) -> dict:
        return {
            "belief_id": self.belief_id, "ancien_statut": self.ancien_statut,
            "nouveau_statut": self.nouveau_statut, "motif": self.motif,
            "preuves_ajoutees": list(self.preuves_ajoutees),
            "preuves_retirees": list(self.preuves_retirees),
            "acteur": self.acteur, "date": self.date,
        }


@dataclass(frozen=True)
class EvidenceNeed:
    question: str
    type: str = "preuve"
    cible: str = ""
    statut: str = "OUVERT"
    twins: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    id: str = ""

    def __post_init__(self):
        if not _texte(self.question):
            raise ValueError("besoin de preuve : question obligatoire")
        object.__setattr__(self, "question", _texte(self.question))
        object.__setattr__(self, "type", _texte(self.type, 40) or "preuve")
        object.__setattr__(self, "cible", _texte(self.cible, 240))
        object.__setattr__(self, "statut", _texte(self.statut, 20).upper() or "OUVERT")
        object.__setattr__(self, "twins", _textes(self.twins, 160))
        object.__setattr__(self, "sources", _textes(self.sources, 200))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(self.question, "need"))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "question": self.question, "type": self.type,
            "cible": self.cible, "statut": self.statut,
            "twins": list(self.twins), "sources": list(self.sources),
        }


@dataclass(frozen=True)
class SourcePlan:
    twins: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    memoire: tuple[str, ...] = ()
    ordre: tuple[str, ...] = ()
    budget: dict = field(default_factory=dict)
    conditions_arret: tuple[str, ...] = ()
    justification: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "twins", _textes(self.twins, 160))
        object.__setattr__(self, "claims", _textes(self.claims, 200))
        object.__setattr__(self, "sources", _textes(self.sources, 200))
        object.__setattr__(self, "memoire", _textes(self.memoire, 200))
        object.__setattr__(self, "ordre", _textes(self.ordre, 80))
        object.__setattr__(self, "budget", _mapping(self.budget))
        object.__setattr__(self, "conditions_arret", _textes(self.conditions_arret, 500))
        object.__setattr__(self, "justification", _textes(self.justification, 500))

    def as_dict(self) -> dict:
        return {
            "twins": list(self.twins), "claims": list(self.claims),
            "sources": list(self.sources), "memoire": list(self.memoire),
            "ordre": list(self.ordre), "budget": dict(self.budget),
            "conditions_arret": list(self.conditions_arret),
            "justification": list(self.justification),
        }


@dataclass(frozen=True)
class QuestionFrame:
    question: str
    tache: str = "repondre"
    objet: str = ""
    presuppositions: tuple[Presupposition, ...] = ()
    inconnues: tuple[str, ...] = ()
    questions_bloquantes: tuple[str, ...] = ()
    materialite: str = "faible"

    def __post_init__(self):
        if not _texte(self.question):
            raise ValueError("question frame : question obligatoire")
        object.__setattr__(self, "question", _texte(self.question))
        object.__setattr__(self, "tache", _texte(self.tache, 40) or "repondre")
        object.__setattr__(self, "objet", _texte(self.objet, 240))
        pres = tuple(
            p if isinstance(p, Presupposition) else Presupposition(**_mapping(p))
            for p in self.presuppositions or ()
        )
        object.__setattr__(self, "presuppositions", pres)
        object.__setattr__(self, "inconnues", _textes(self.inconnues, 500))
        object.__setattr__(self, "questions_bloquantes", _textes(self.questions_bloquantes, 500))
        object.__setattr__(self, "materialite", _texte(self.materialite, 20) or "faible")

    @property
    def bloquantes(self) -> tuple[Presupposition, ...]:
        return tuple(p for p in self.presuppositions if p.bloquant)

    def as_dict(self) -> dict:
        return {
            "question": self.question, "tache": self.tache, "objet": self.objet,
            "presuppositions": [p.as_dict() for p in self.presuppositions],
            "inconnues": list(self.inconnues),
            "questions_bloquantes": list(self.questions_bloquantes),
            "materialite": self.materialite,
        }
