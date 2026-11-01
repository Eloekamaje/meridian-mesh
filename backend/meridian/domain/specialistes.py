"""Noyau des spécialistes cognitifs : contrats, artefacts et orchestration parallèle.

Un spécialiste ne détient pas la vérité : il observe un contexte borné et produit des **propositions**
traçables. L'orchestrateur les exécute en parallèle, borne leur durée, déduplique et rend un dossier
commun. Aucun spécialiste n'écrit dans le canonique ni ne décide ; l'humain garde l'autorité.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import time
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ContexteSpecialiste",
    "OrchestrateurSpecialistes",
    "Proposition",
    "ResultatSpecialiste",
    "Specialiste",
    "normaliser_propositions",
]

STATUTS = ("ok", "partiel", "erreur", "refuse")
_TYPES_ARTEFACT = frozenset({
    "CONSTAT", "HYPOTHESE", "PROPOSITION", "IMPACT", "PREUVE", "RISQUE", "ACTION", "QUESTION",
    "OUTCOME", "LEARNING", "MODELE",
})


def _texte(valeur, maximum=2000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _identifiants(valeurs) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat = []
    for valeur in valeurs:
        if isinstance(valeur, Mapping):
            valeur = valeur.get("id")
        texte = _texte(valeur, 160)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


@dataclass(frozen=True)
class ContexteSpecialiste:
    """Le dossier borné qu'un spécialiste peut lire ; les dépendances sont injectées, jamais ouvertes ici."""

    tenant: str
    question: str = ""
    situation_id: str | None = None
    twin_ids: tuple[str, ...] = ()
    application_id: str | None = None
    claim_ids: tuple[str, ...] = ()
    profondeur: int = 2
    maintenant: str | None = None
    conn: Any = None
    store: Any = None
    executeur: Any = None

    def __post_init__(self):
        if not _texte(self.tenant, 128):
            raise ValueError("tenant obligatoire")
        object.__setattr__(self, "twin_ids", _identifiants(self.twin_ids))
        object.__setattr__(self, "claim_ids", _identifiants(self.claim_ids))
        try:
            profondeur = int(self.profondeur)
        except (TypeError, ValueError) as exc:
            raise ValueError("profondeur invalide") from exc
        object.__setattr__(self, "profondeur", max(1, min(profondeur, 8)))
        object.__setattr__(self, "maintenant", self.maintenant or datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict:
        return {
            "tenant": self.tenant,
            "question": self.question,
            "situation_id": self.situation_id,
            "twin_ids": list(self.twin_ids),
            "application_id": self.application_id,
            "claim_ids": list(self.claim_ids),
            "profondeur": self.profondeur,
            "maintenant": self.maintenant,
        }


@dataclass(frozen=True)
class Proposition:
    """Un artefact proposé : jamais une vérité promue, jamais une écriture canonique."""

    specialiste: str
    type: str
    titre: str
    resume: str = ""
    preuves: tuple[str, ...] = ()
    confiance: float = 0.5
    actions: tuple[str, ...] = ()
    donnees: dict = field(default_factory=dict)

    def __post_init__(self):
        specialiste = _texte(self.specialiste, 80)
        type_ = _texte(self.type, 40).upper()
        if not specialiste:
            raise ValueError("specialiste obligatoire")
        if type_ not in _TYPES_ARTEFACT:
            raise ValueError(f"type d'artefact inconnu : {type_}")
        titre = _texte(self.titre, 240)
        if not titre:
            raise ValueError("titre obligatoire")
        try:
            confiance = float(self.confiance)
        except (TypeError, ValueError) as exc:
            raise ValueError("confiance invalide") from exc
        object.__setattr__(self, "specialiste", specialiste)
        object.__setattr__(self, "type", type_)
        object.__setattr__(self, "titre", titre)
        object.__setattr__(self, "resume", _texte(self.resume, 2000))
        object.__setattr__(self, "preuves", _identifiants(self.preuves))
        object.__setattr__(self, "confiance", max(0.0, min(1.0, confiance)))
        object.__setattr__(self, "actions", _identifiants(self.actions))
        object.__setattr__(self, "donnees", dict(self.donnees or {}))

    def as_dict(self) -> dict:
        return {
            "specialiste": self.specialiste,
            "type": self.type,
            "titre": self.titre,
            "resume": self.resume,
            "preuves": list(self.preuves),
            "confiance": round(self.confiance, 3),
            "actions": list(self.actions),
            "donnees": self.donnees,
        }


@dataclass
class ResultatSpecialiste:
    specialiste: str
    statut: str = "ok"
    propositions: list[Proposition] = field(default_factory=list)
    limites: list[str] = field(default_factory=list)
    erreur: str | None = None
    duree_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "specialiste": self.specialiste,
            "statut": self.statut,
            "propositions": [p.as_dict() for p in self.propositions],
            "limites": list(self.limites),
            "erreur": self.erreur,
            "duree_ms": self.duree_ms,
        }


@runtime_checkable
class Specialiste(Protocol):
    nom: str
    autorite: str

    def analyser(self, contexte: ContexteSpecialiste) -> ResultatSpecialiste | list[Proposition]: ...


def normaliser_propositions(valeurs: Iterable[Any], specialiste: str) -> list[Proposition]:
    resultat: list[Proposition] = []
    for valeur in valeurs or ():
        if isinstance(valeur, Proposition):
            resultat.append(valeur)
        elif isinstance(valeur, Mapping):
            resultat.append(Proposition(specialiste=specialiste, **valeur))
    return resultat


class OrchestrateurSpecialistes:
    """Exécute des spécialistes en parallèle, borne leur temps et assemble un dossier commun."""

    def __init__(self, specialistes: Iterable[Specialiste], timeout_s: float = 8.0):
        if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise ValueError("timeout_s doit être positif")
        self.specialistes = list(specialistes)
        for specialiste in self.specialistes:
            if not isinstance(specialiste, Specialiste):
                raise TypeError("spécialiste invalide : nom, autorite et analyser attendus")
            if getattr(specialiste, "autorite", "") != "proposition":
                raise ValueError("un spécialiste ne peut avoir que l'autorité proposition")
        self.timeout_s = float(timeout_s)

    async def _executer(self, specialiste: Specialiste, contexte: ContexteSpecialiste):
        debut = time.perf_counter()
        try:
            fonction = specialiste.analyser
            resultat = await asyncio.wait_for(
                asyncio.to_thread(fonction, contexte), timeout=self.timeout_s)
            if inspect.isawaitable(resultat):
                resultat = await asyncio.wait_for(resultat, timeout=self.timeout_s)
            if isinstance(resultat, ResultatSpecialiste):
                resultat.duree_ms = round((time.perf_counter() - debut) * 1000, 2)
                return resultat
            propositions = normaliser_propositions(resultat or (), specialiste.nom)
            return ResultatSpecialiste(
                specialiste=specialiste.nom, statut="ok", propositions=propositions,
                duree_ms=round((time.perf_counter() - debut) * 1000, 2))
        except asyncio.TimeoutError:
            return ResultatSpecialiste(
                specialiste=specialiste.nom, statut="erreur", erreur="TimeoutError",
                duree_ms=round((time.perf_counter() - debut) * 1000, 2))
        except Exception as exc:  # noqa: BLE001 - un spécialiste ne bloque pas le dossier
            return ResultatSpecialiste(
                specialiste=specialiste.nom, statut="erreur", erreur=type(exc).__name__,
                duree_ms=round((time.perf_counter() - debut) * 1000, 2))

    async def analyser(self, contexte: ContexteSpecialiste) -> dict:
        if not isinstance(contexte, ContexteSpecialiste):
            raise TypeError("ContexteSpecialiste attendu")
        resultats = await asyncio.gather(
            *(self._executer(specialiste, contexte) for specialiste in self.specialistes))
        propositions = {}
        for resultat in resultats:
            for proposition in resultat.propositions:
                cle = (proposition.specialiste, proposition.type, proposition.titre)
                precedent = propositions.get(cle)
                if precedent is None or proposition.confiance > precedent.confiance:
                    propositions[cle] = proposition
        ordonnees = sorted(
            propositions.values(),
            key=lambda p: (-p.confiance, p.type, p.titre, p.specialiste))
        return {
            "tenant": contexte.tenant,
            "contexte": contexte.as_dict(),
            "specialistes": [resultat.as_dict() for resultat in resultats],
            "propositions": [proposition.as_dict() for proposition in ordonnees],
            "statut": "ok" if all(r.statut == "ok" for r in resultats) else "partiel",
            "limites": [
                "propositions non canoniques : aucune promotion, décision ou écriture automatique",
            ],
        }
