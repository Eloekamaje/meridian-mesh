"""Planification d'investigations applicatives, sans LLM ni persistance.

La naissance ouvre un petit ensemble stable de questions de compréhension. Les ingestions
suivantes ne rejouent que les connaissances dont une preuve appartient à un fichier modifié.
L'index et le diff restent des observations : ce module ne crée ni Claim ni preuve.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping

__all__ = [
    "MissionInvestigation",
    "ReexamenClaim",
    "fichiers_modifies",
    "missions_initiales",
    "planifier_reexamens",
]

MAX_MISSIONS_INITIALES = 6
MAX_FICHIERS_DIFF = 2000


@dataclass(frozen=True)
class MissionInvestigation:
    cle: str
    objectif: str
    priorite: int
    raison: str


@dataclass(frozen=True)
class ReexamenClaim:
    claim_id: str
    fichiers: tuple[str, ...]
    raison: str = "preuve de code touchée par le changement"


_MISSIONS = (
    MissionInvestigation(
        "points-entree",
        "Identifier les points d'entrée et suivre au moins un parcours jusqu'à ses effets.",
        100,
        "un inventaire de routes ne prouve pas le parcours réel",
    ),
    MissionInvestigation(
        "controles-erreurs",
        "Vérifier permissions, validations, transactions, refus et chemins d'erreur des parcours suivis.",
        90,
        "les contrôles et variantes ne se déduisent pas du seul point d'entrée",
    ),
    MissionInvestigation(
        "donnees-effets",
        "Identifier les données lues ou écrites et les effets secondaires des parcours suivis.",
        80,
        "les impacts exigent de relier service, stockage et publication",
    ),
    MissionInvestigation(
        "dependances-confirmees",
        "Distinguer les dépendances seulement déclarées de celles effectivement utilisées.",
        70,
        "DECLARE_DEPENDANCE ne vaut pas DEPEND_DE",
    ),
    MissionInvestigation(
        "interfaces-sortantes",
        "Identifier les appels, messages et interfaces sortantes avec leurs consommateurs connus.",
        60,
        "une relation externe doit être localisée et bornée",
    ),
)


def _identifiant(valeur, champ: str) -> str:
    texte = str(valeur or "").strip()
    if not texte or len(texte) > 200:
        raise ValueError(f"{champ} invalide")
    return texte


def _chemin(valeur) -> str:
    texte = str(valeur or "").strip().replace("\\", "/")
    chemin = PurePosixPath(texte)
    if (not texte or chemin.is_absolute() or any(part in {"", ".", ".."} for part in chemin.parts)
            or "\x00" in texte):
        raise ValueError("chemin de diff invalide")
    return chemin.as_posix()


def missions_initiales(jumeau_id: str, exploration: Mapping | None = None) -> tuple[MissionInvestigation, ...]:
    """Questions bornées d'une première compréhension, enrichies par les lacunes de couverture."""
    _identifiant(jumeau_id, "jumeau_id")
    exploration = dict(exploration or {})
    missions = list(_MISSIONS)
    couverture = dict(exploration.get("couverture") or {})
    lacunes = sum(int(couverture.get(cle) or 0) for cle in ("partiel", "non_supporte", "tronque", "conflit"))
    erreurs = tuple(sorted({str(e).strip() for e in exploration.get("erreurs_providers") or () if str(e).strip()}))
    if lacunes or erreurs:
        detail = []
        if lacunes:
            detail.append(f"{lacunes} fichier(s) partiels, non supportés, tronqués ou en conflit")
        if erreurs:
            detail.append("providers en erreur : " + ", ".join(erreurs))
        missions.insert(0, MissionInvestigation(
            "lacunes-couverture",
            "Qualifier les zones non couvertes et les sources nécessaires avant toute conclusion globale.",
            110,
            " ; ".join(detail),
        ))
    return tuple(sorted(missions, key=lambda m: (-m.priorite, m.cle))[:MAX_MISSIONS_INITIALES])


def fichiers_modifies(commits: Iterable[Mapping]) -> tuple[str, ...]:
    """Union bornée et normalisée des fichiers portés par ``temps.commits_entre``."""
    resultat = []
    vus = set()
    for commit in commits or ():
        if not isinstance(commit, Mapping):
            raise TypeError("commit attendu")
        for valeur in commit.get("fichiers") or ():
            chemin = _chemin(valeur)
            if chemin not in vus:
                vus.add(chemin)
                resultat.append(chemin)
                if len(resultat) >= MAX_FICHIERS_DIFF:
                    return tuple(sorted(resultat))
    return tuple(sorted(resultat))


def _preuves(claim: Mapping):
    preuves = claim.get("preuves") or claim.get("evidence") or ()
    return preuves if isinstance(preuves, (list, tuple)) else ()


def planifier_reexamens(claims: Iterable[Mapping], depot: str,
                        fichiers: Iterable[str]) -> tuple[ReexamenClaim, ...]:
    """Claims à réexaminer lorsque leur preuve du ``depot`` touche un fichier modifié.

    L'absence de correspondance n'est jamais interprétée comme une preuve de non-impact.
    """
    depot = _identifiant(depot, "depot")
    modifies = {_chemin(fichier) for fichier in fichiers or ()}
    resultat = []
    for claim in claims or ():
        if not isinstance(claim, Mapping):
            raise TypeError("claim attendu")
        claim_id = _identifiant(claim.get("id"), "claim.id")
        touches = set()
        for preuve in _preuves(claim):
            if not isinstance(preuve, Mapping):
                continue
            source = str(preuve.get("repository") or preuve.get("depot") or preuve.get("source") or "").strip()
            chemin = preuve.get("fichier") or preuve.get("chemin") or preuve.get("file")
            if source == depot and chemin:
                normalise = _chemin(chemin)
                if normalise in modifies:
                    touches.add(normalise)
        if touches:
            resultat.append(ReexamenClaim(claim_id, tuple(sorted(touches))))
    return tuple(sorted(resultat, key=lambda r: r.claim_id))
