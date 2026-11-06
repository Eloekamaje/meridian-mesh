"""Boucle d'enquête bornée : planifier, outiller, observer, s'arrêter.

La boucle ne sait rien du modèle ni de la base. Elle reçoit :

- un cas (`ResolutionCase` ou objet compatible) ;
- un planificateur qui choisit le prochain outil ou demande l'arrêt ;
- des outils read-only injectés ;
- un budget strict.

Elle rend des candidats structurés, l'historique des étapes et la raison d'arrêt.
Elle n'écrit aucun lien, ne confirme rien et ne dépasse jamais son budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from meridian.domain.decouverte_liens import CandidatResolution

__all__ = [
    "BudgetEnquete",
    "EtapeInvestigation",
    "PlanificateurRegles",
    "ResultatInvestigation",
    "executer",
]


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


@dataclass(frozen=True)
class BudgetEnquete:
    max_etapes: int = 6
    max_outils: int = 4
    max_candidats: int = 5

    def __post_init__(self):
        for nom in ("max_etapes", "max_outils", "max_candidats"):
            valeur = int(getattr(self, nom))
            if valeur < 1:
                raise ValueError(f"{nom} doit être >= 1")
            object.__setattr__(self, nom, valeur)


@dataclass(frozen=True)
class EtapeInvestigation:
    numero: int
    outil: str
    arguments: dict = field(default_factory=dict)
    statut: str = "ok"
    resume: str = ""
    evidence_ids: tuple[str, ...] = ()
    candidats: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "numero": self.numero, "outil": self.outil,
            "arguments": dict(self.arguments), "statut": self.statut,
            "resume": self.resume, "evidence_ids": list(self.evidence_ids),
            "candidats": list(self.candidats),
        }


@dataclass(frozen=True)
class ResultatInvestigation:
    cas_id: str
    etapes: tuple[EtapeInvestigation, ...] = ()
    candidats: tuple[dict, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    arret: str = "planificateur"
    budget_atteint: bool = False
    erreurs: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "cas_id": self.cas_id,
            "etapes": [etape.as_dict() for etape in self.etapes],
            "candidats": list(self.candidats),
            "evidence_ids": list(self.evidence_ids),
            "arret": self.arret,
            "budget_atteint": self.budget_atteint,
            "erreurs": list(self.erreurs),
        }


class PlanificateurRegles:
    """Planificateur déterministe de repli : la preuve manquante choisit la source."""

    _ORDRE = ("configuration", "deploiement", "gateway", "contrats", "code",
              "messagerie", "traces", "runtime", "annuaire", "portail")

    def prochain(self, cas, historique) -> dict:
        historique = tuple(historique or ())
        if historique and getattr(historique[-1], "candidats", ()):
            return {"stop": True, "raison": "candidat trouvé"}
        utilises = {etape.outil for etape in historique}
        texte = " ".join((
            _texte(getattr(cas, "reference", "")),
            _texte(getattr(cas, "missing_evidence", "")),
            _texte(getattr(cas, "next_check", "")),
        )).casefold()
        indices = []
        if any(mot in texte for mot in ("propriété", "propriete", "property", "binding")):
            indices.append("configuration")
        if any(mot in texte for mot in ("service", "route", "hôte")):
            indices.append("deploiement")
        if any(mot in texte for mot in ("gateway", "passerelle")):
            indices.append("gateway")
        if any(mot in texte for mot in ("jms", "queue", "topic", "file", "file d'attente")):
            indices.append("messagerie")
        if any(mot in texte for mot in ("contrat", "wsdl", "openapi", "swagger")):
            indices.append("contrats")
        if any(mot in texte for mot in ("trace", "observé", "observed")):
            indices.append("traces")
        if "runtime" in texte:
            indices.append("runtime")
        if any(mot in texte for mot in ("propriétaire", "proprietaire", "owner", "twin")):
            indices.append("annuaire")
        if "portail" in texte:
            indices.append("portail")
        for nom in (*indices, *self._ORDRE):
            if nom not in utilises:
                return {
                    "outil": nom,
                    "arguments": {
                        "reference": _texte(getattr(cas, "reference", "")),
                        "environment": _texte(getattr(cas, "environment", "")),
                        "missing_evidence": _texte(getattr(cas, "missing_evidence", "")),
                        "service": _texte(getattr(cas, "twin_id", "")),
                    },
                    "raison": f"preuve manquante : {_texte(getattr(cas, 'missing_evidence', ''))}",
                }
        return {"stop": True, "raison": "sources épuisées"}


def _candidats(reponse) -> tuple[tuple[dict, ...], tuple[str, ...]]:
    candidats = []
    erreurs = []
    for brut in (reponse.get("candidats") or ()):
        try:
            candidat = CandidatResolution.depuis_dict(brut)
        except ValueError as exc:
            erreurs.append(f"candidat invalide : {exc}")
            continue
        candidats.append(candidat.as_dict())
    return tuple(candidats), tuple(erreurs)


def _evidence(reponse) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        str(x) for x in (reponse.get("evidence_ids") or ()) if str(x).strip()))


def executer(cas, planificateur, outils: Mapping, *,
             budget: BudgetEnquete | None = None) -> ResultatInvestigation:
    """Exécute la boucle bornée ; aucune écriture, aucune confirmation."""
    budget = budget or BudgetEnquete()
    etapes: list[EtapeInvestigation] = []
    candidats: dict[str, dict] = {}
    evidence_ids: list[str] = []
    erreurs: list[str] = []
    utilises: set[str] = set()
    arret = "budget_etapes"

    for numero in range(1, budget.max_etapes + 1):
        decision = planificateur.prochain(cas, tuple(etapes))
        if not isinstance(decision, dict):
            erreurs.append("planificateur : décision non structurée")
            arret = "planificateur_invalide"
            break
        if decision.get("stop"):
            arret = _texte(decision.get("raison") or "planificateur", 300) or "planificateur"
            break
        nom = _texte(decision.get("outil"), 80)
        if nom not in outils:
            erreurs.append(f"outil inconnu : {nom}")
            arret = "outil_inconnu"
            break
        if nom in utilises:
            erreurs.append(f"outil déjà utilisé : {nom}")
            arret = "outil_deja_utilise"
            break
        if len(utilises) >= budget.max_outils:
            arret = "budget_outils"
            break
        arguments = decision.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        outil = outils[nom]
        try:
            reponse = outil.appeler(arguments) if hasattr(outil, "appeler") else outil(arguments)
        except Exception as exc:  # noqa: BLE001 - un outil en panne ne doit pas casser la boucle
            etapes.append(EtapeInvestigation(
                numero=numero, outil=nom, arguments=dict(arguments),
                statut="erreur", resume=f"{type(exc).__name__}: {exc}"))
            erreurs.append(f"{nom} : {type(exc).__name__}")
            arret = "erreur_outil"
            break
        if not isinstance(reponse, dict):
            reponse = {}
        nouveaux, erreurs_candidats = _candidats(reponse)
        erreurs.extend(erreurs_candidats)
        preuves = _evidence(reponse)
        for identifiant in preuves:
            if identifiant not in evidence_ids:
                evidence_ids.append(identifiant)
        for candidat in nouveaux:
            candidats[candidat["id"]] = candidat
        utilises.add(nom)
        etapes.append(EtapeInvestigation(
            numero=numero, outil=nom, arguments=dict(arguments),
            statut=str(reponse.get("statut") or "ok"),
            resume=_texte(reponse.get("resume"), 1000),
            evidence_ids=preuves, candidats=nouveaux))
        if len(candidats) >= budget.max_candidats:
            arret = "budget_candidats"
            break
    else:
        arret = "budget_etapes"

    return ResultatInvestigation(
        cas_id=_texte(getattr(cas, "id", "") or getattr(cas, "reference", ""), 300),
        etapes=tuple(etapes), candidats=tuple(candidats.values()),
        evidence_ids=tuple(evidence_ids), arret=arret,
        budget_atteint=arret.startswith("budget_"),
        erreurs=tuple(dict.fromkeys(erreurs)),
    )
