"""Chargement d'un corpus de liens depuis un fichier JSON et des racines locales.

Un corpus décrit :

- une politique de sources ;
- des dépôts (application, composant, racine) ;
- les liens, questions, externes et contradictions attendus.

Il ne contient aucun secret : seuls les fichiers autorisés par la politique sont lus.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from meridian.adapters.outbound.connectors.decouverte_composants import (
    extraire_depot,
    lire_fichiers,
)
from meridian.application.evaluation_liens import JeuOrLiens, LienAttendu, QuestionAttendue
from meridian.domain.liens_composants import ExtractionDepot, SourceDepot
from meridian.domain.politique_decouverte import PolitiqueSources

__all__ = ["CorpusLiens", "charger_corpus"]


@dataclass(frozen=True)
class CorpusLiens:
    chemin: str
    tenant_id: str
    politique: PolitiqueSources
    extractions: tuple[ExtractionDepot, ...]
    jeu: JeuOrLiens
    diagnostics: tuple[str, ...] = ()


def _chemin_racine(base: Path, valeur) -> Path:
    chemin = Path(str(valeur or "")).expanduser()
    return chemin if chemin.is_absolute() else (base / chemin).resolve()


def _jeu(donnees, chemin: str) -> JeuOrLiens:
    if not isinstance(donnees, dict):
        raise ValueError(f"{chemin} : bloc attendu manquant")
    liens = []
    for item in donnees.get("liens") or ():
        try:
            liens.append(LienAttendu(**item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{chemin} : lien attendu invalide ({exc})") from exc
    questions = []
    for item in donnees.get("questions") or ():
        try:
            questions.append(QuestionAttendue(**item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{chemin} : question attendue invalide ({exc})") from exc
    return JeuOrLiens(
        liens=tuple(liens), questions=tuple(questions),
        externes=tuple(donnees.get("externes") or ()),
        contradictions=tuple(donnees.get("contradictions") or ()),
    )


def charger_corpus(chemin) -> CorpusLiens:
    """Lit un corpus JSON et prépare les extractions et le jeu d'or."""
    chemin = Path(chemin).expanduser().resolve()
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"corpus illisible : {chemin}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"corpus JSON invalide : {exc.msg}") from exc
    if not isinstance(donnees, dict):
        raise ValueError("corpus : objet JSON attendu")
    base = chemin.parent
    try:
        politique = PolitiqueSources(
            tenant_id=donnees.get("tenant") or "corpus",
            niveaux=tuple(donnees.get("niveau_sources") or (0,)),
            sources_explicites=tuple(donnees.get("sources_explicites") or ()),
            approuve_par=donnees.get("approuve_par") or "",
            approuve_le=donnees.get("approuve_le") or "",
            motif=donnees.get("motif") or "corpus de mesure",
        )
    except ValueError as exc:
        raise ValueError(f"corpus : politique de sources invalide ({exc})") from exc

    extractions = []
    diagnostics: list[str] = []
    for depot in donnees.get("depots") or ():
        if not isinstance(depot, dict):
            raise ValueError("corpus : dépôt attendu sous forme d'objet")
        try:
            application = depot["application_id"]
            composant = depot["composant_id"]
            racine = _chemin_racine(base, depot["racine"])
        except KeyError as exc:
            raise ValueError(f"corpus : champ de dépôt manquant ({exc})") from exc
        fichiers, problemes = lire_fichiers(
            racine, sources_autorisees=politique.sources_autorisees)
        diagnostics.extend(problemes)
        extraction = extraire_depot(SourceDepot(
            application_id=application, composant_id=composant,
            environment=depot.get("environment") or "prod",
            owner=depot.get("owner") or "",
            type_composant=depot.get("type_composant") or "SERVICE",
            fichiers=fichiers))
        extractions.append(extraction)
        diagnostics.extend(extraction.diagnostics)

    return CorpusLiens(
        chemin=str(chemin), tenant_id=politique.tenant_id,
        politique=politique, extractions=tuple(extractions),
        jeu=_jeu(donnees.get("attendu"), str(chemin)),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )
