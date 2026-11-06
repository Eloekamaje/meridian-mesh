"""Compréhension d'une application : les sept questions, leur statut et leur couverture.

Ce module est volontairement pur : il ne lit ni base, ni modèle, ni source. Il transforme des
Claims (déjà projetés ou non) en statuts de réponse. La fiche est un **rendu** de ces statuts,
pas le modèle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

__all__ = [
    "PREDICATS",
    "PRESENTATION",
    "QUESTIONS",
    "STATUTS",
    "QuestionStatus",
    "couverture",
    "resume_couverture",
    "statut_question",
    "statuts_depuis_claims",
]

# (clé, titre de section dans la fiche, prédicat de la connaissance, type de Claim)
QUESTIONS = (
    ("sert", "À quoi elle sert", "REALISE_CAPACITE", "CAPABILITY"),
    ("pour_qui", "Pour qui, dans quels parcours", "SERT_ACTEUR", "PROCESS_STEP"),
    ("informations", "Les informations qu'elle détient", "DETIENT", "DATA_FLOW"),
    ("regles", "Les règles qu'elle applique", "APPLIQUE_REGLE", "BUSINESS_RULE"),
    ("echanges", "Avec qui elle échange", "ECHANGE_AVEC", "DATA_FLOW"),
    ("vie", "Comment elle vit", None, None),
    ("inconnu", "Ce que l'on ne sait pas encore", None, None),
)
PREDICATS = {question[2] for question in QUESTIONS if question[2]}

# Sections de la fiche vivante, du plus court au plus détaillé (méthode comprendre-application).
PRESENTATION = (
    ("trente", "En 30 secondes"),
    ("journee", "Une journée avec elle"),
    ("faire", "Ce qu'elle permet de faire"),
    ("regles", "Les règles à retenir"),
    ("garde", "Ce qu'elle garde"),
    ("avec", "Avec qui elle travaille"),
    ("ignore", "D'où je le sais, et ce que j'ignore"),
)

STATUTS = ("answered", "partial", "unknown", "contradicted")


@dataclass(frozen=True)
class QuestionStatus:
    """Réponse à une question : ce qui est prouvé, ce qui manque, ce qui est contesté."""

    cle: str
    statut: str
    claim_ids: tuple[int, ...] = ()
    preuves: tuple[str, ...] = ()
    inconnues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.statut not in STATUTS:
            raise ValueError(
                f"statut inconnu : {self.statut!r} (attendus : {', '.join(STATUTS)})"
            )
        object.__setattr__(self, "claim_ids", tuple(self.claim_ids))
        object.__setattr__(self, "preuves", tuple(dict.fromkeys(self.preuves)))
        object.__setattr__(self, "inconnues", tuple(dict.fromkeys(self.inconnues)))


def _valeur(claim: Any, nom: str, defaut: Any = None) -> Any:
    if isinstance(claim, Mapping):
        return claim.get(nom, defaut)
    return getattr(claim, nom, defaut)


def _preuves_de(claim: Any) -> tuple[str, ...]:
    """Localisateurs de preuve d'un Claim, qu'il soit en forme `preuve` ou `preuves`."""
    directe = _valeur(claim, "preuve")
    if isinstance(directe, str) and directe.strip():
        return (directe.strip(),)
    preuves = _valeur(claim, "preuves") or ()
    resultat = []
    for preuve in preuves:
        if isinstance(preuve, str):
            resultat.append(preuve)
        elif isinstance(preuve, Mapping):
            locator = preuve.get("locator")
            if locator:
                resultat.append(str(locator))
    return tuple(resultat)


def _predicat(claim: Any) -> str:
    return str(_valeur(claim, "predicat", "") or "").strip().upper()


def _statut_claim(claim: Any) -> str:
    return str(_valeur(claim, "statut", "") or "").strip().upper()


def statut_question(cle: str, claims: Iterable[Any], contradictions=()) -> QuestionStatus:
    """Statut d'une question à partir des Claims disponibles.

    - aucun Claim : `unknown` ;
    - Claims sans preuve : `partial` ;
    - Claim contesté ou contradiction ouverte : `contradicted` ;
    - tous les Claims ont une preuve : `answered`.
    """
    question = next((q for q in QUESTIONS if q[0] == cle), None)
    if question is None:
        raise ValueError(f"question inconnue : {cle!r}")
    predicat = question[2]
    if predicat is None:
        return QuestionStatus(
            cle, "unknown",
            inconnues=("question narrative, non adossée à un Claim",),
        )
    pertinents = [claim for claim in claims if _predicat(claim) == predicat]
    ids = tuple(int(_valeur(claim, "id")) for claim in pertinents
                if _valeur(claim, "id") is not None)
    preuves = tuple(
        dict.fromkeys(locator for claim in pertinents for locator in _preuves_de(claim))
    )
    conteste = bool(contradictions) or any(
        _statut_claim(claim) in {"CONTESTED", "INVALIDATED"} for claim in pertinents
    )
    if conteste:
        return QuestionStatus(
            cle, "contradicted", ids, preuves,
            inconnues=("Claim contesté ou contradiction ouverte",),
        )
    if not pertinents:
        return QuestionStatus(
            cle, "unknown", (), (),
            inconnues=("aucun Claim pour cette question",),
        )
    sans_preuve = [claim for claim in pertinents if not _preuves_de(claim)]
    if sans_preuve:
        return QuestionStatus(
            cle, "partial", ids, preuves,
            inconnues=(f"{len(sans_preuve)} Claim(s) sans preuve localisée",),
        )
    return QuestionStatus(cle, "answered", ids, preuves)


def statuts_depuis_claims(claims: Iterable[Any], contradictions=()) -> tuple[QuestionStatus, ...]:
    """Les sept statuts, dans l'ordre de la méthode."""
    claims = tuple(claims)
    return tuple(statut_question(cle, claims, contradictions) for cle, *_ in QUESTIONS)


def couverture(statuts: Iterable[QuestionStatus]) -> dict[str, Any]:
    """Comptage et taux de couverture des sept questions."""
    statuts = tuple(statuts)
    compte = {statut: 0 for statut in STATUTS}
    for question in statuts:
        if question.statut not in compte:
            raise ValueError(f"statut inconnu : {question.statut!r}")
        compte[question.statut] += 1
    total = len(statuts)
    return {
        "total": total,
        **compte,
        "complet": total > 0 and compte["answered"] == total,
        "couverture": (
            round((compte["answered"] + 0.5 * compte["partial"]) / total, 2) if total else 0.0
        ),
    }


def resume_couverture(statuts: Iterable[QuestionStatus]) -> str:
    """Résumé lisible : « 3/7 répondu, 2 partiels, 2 inconnus »."""
    bilan = couverture(statuts)
    morceaux = [f"{bilan['answered']}/{bilan['total']} répondu"]
    if bilan["partial"]:
        morceaux.append(f"{bilan['partial']} partiel(s)")
    if bilan["unknown"]:
        morceaux.append(f"{bilan['unknown']} inconnu(s)")
    if bilan["contradicted"]:
        morceaux.append(f"{bilan['contradicted']} contredit(s)")
    return ", ".join(morceaux)
