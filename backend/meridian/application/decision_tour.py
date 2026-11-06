"""Décision de tour validée par le serveur.

Le modèle propose une action ; ce module vérifie qu'elle respecte le contrat avant toute
exécution. Il ne choisit pas le contenu et n'appelle ni modèle ni outil.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "ACTIONS", "ACTES", "DecisionTour", "DecisionInvalide", "AppelOutil",
    "Clarification", "valider",
]

ACTIONS = frozenset({"repondre", "clarifier", "outil", "proposer", "refuser"})
ACTES = frozenset({"question", "suivi", "correction", "confirmation", "meta", "nouveau_sujet", "social"})


class DecisionInvalide(ValueError):
    """La décision du modèle ne respecte pas le contrat du tour."""


@dataclass(frozen=True)
class Clarification:
    slot: str
    texte: str
    effet_attendu: str
    bloquante: bool = True


@dataclass(frozen=True)
class AppelOutil:
    nom: str
    arguments: dict = field(default_factory=dict)
    but: str = ""


@dataclass(frozen=True)
class DecisionTour:
    action: str
    acte: str = "question"
    but: str = "repondre"
    niveau: str = "N0"
    clarification: Clarification | None = None
    appels: tuple[AppelOutil, ...] = ()
    brouillon: dict | None = None
    citations: tuple[str, ...] = ()
    raisons: tuple[str, ...] = ()


def valider(
    decision: DecisionTour,
    *,
    outils_autorises=(),
    slots_connus=(),
    slots_remplis=(),
    budget_outils: int = 6,
    deja_une_question: bool = False,
) -> DecisionTour:
    """Valide une décision ; lève ``DecisionInvalide`` plutôt que de corriger en silence."""
    if not isinstance(decision, DecisionTour):
        raise DecisionInvalide("décision de tour absente")
    if decision.action not in ACTIONS:
        raise DecisionInvalide(f"action inconnue : {decision.action!r}")
    if decision.acte not in ACTES:
        raise DecisionInvalide(f"acte inconnu : {decision.acte!r}")
    if decision.action == "clarifier":
        clarification = decision.clarification
        if decision.acte in {"meta", "social"}:
            raise DecisionInvalide("une question méta ou sociale ne peut pas demander une clarification")
        if clarification is None:
            raise DecisionInvalide("clarification absente")
        if not str(clarification.slot or "").strip():
            raise DecisionInvalide("slot de clarification vide")
        if slots_connus and clarification.slot not in set(slots_connus):
            raise DecisionInvalide(f"slot inconnu : {clarification.slot!r}")
        if clarification.slot in set(slots_remplis):
            raise DecisionInvalide(f"slot déjà rempli : {clarification.slot!r}")
        if not str(clarification.texte or "").strip():
            raise DecisionInvalide("question de clarification vide")
        if not str(clarification.effet_attendu or "").strip():
            raise DecisionInvalide("effet attendu de la clarification absent")
        if deja_une_question:
            raise DecisionInvalide("une question est déjà en attente")
        if decision.appels:
            raise DecisionInvalide("clarifier ne peut pas appeler un outil dans le même tour")
        if decision.brouillon:
            raise DecisionInvalide("clarifier ne peut pas produire un brouillon")
    if decision.action == "outil":
        if not decision.appels:
            raise DecisionInvalide("action outil sans appel")
        if len(decision.appels) > max(0, int(budget_outils)):
            raise DecisionInvalide("budget d'outils dépassé")
        autorises = set(outils_autorises or ())
        for appel in decision.appels:
            if not str(appel.nom or "").strip():
                raise DecisionInvalide("nom d'outil vide")
            if autorises and appel.nom not in autorises:
                raise DecisionInvalide(f"outil non autorisé : {appel.nom!r}")
            if not isinstance(appel.arguments, dict):
                raise DecisionInvalide("arguments d'outil non structurés")
    if decision.action == "repondre" and decision.appels:
        raise DecisionInvalide("répondre ne peut pas appeler un outil et conclure dans le même tour")
    return decision
