"""Ouvrir un travail depuis une actualité — ce que Flore dit en premier dépend de ce qui a été demandé.

    comprendre   → Flore PRÉSENTE la situation : sa lecture, pourquoi cela compte, ce qui reste à comprendre, les décisions attendues ;
    suivre       → Flore explique qu'un phénomène est encore incertain, ce qui manque pour le confirmer, et qu'elle le garde sous vérification ;
    investiguer  → Flore pose la QUESTION de l'investigation (une investigation commence toujours par une question) et propose de la cadrer.

Le module est pur : il prend l'histoire, son rapport et (si elle existe) la situation, et rend les messages du fil. L'actualité devient
ainsi un travail comme un autre ; seul le retour vers l'actualité est mis en évidence par l'interface.
"""
from __future__ import annotations

from typing import Optional

INTENTIONS = ("comprendre", "suivre", "investiguer")

# Genre d'actualité → type de travail (les types connus de la liste des travaux)
TYPE_PAR_GENRE = {
    "incident": "incident", "changement": "changement", "relation": "decouverte", "phenomene": "decouverte",
    "connaissance": "decouverte", "comportement": "decouverte", "contradiction": "conformite",
}


def type_travail(genre: str) -> str:
    return TYPE_PAR_GENRE.get(genre, "demande")


def _suggestions(rapport: dict) -> list[dict]:
    return [{"label": p["label"], "question": p["question"]} for p in rapport.get("propositions", []) if p.get("question")]


def message_flore(intention: str, histoire: dict, rapport: dict, situation: Optional[dict], quand: str) -> dict:
    texte_rapport = (rapport.get("texte") or "").strip()
    titre = histoire.get("titre", "")
    if intention == "suivre":
        texte = (
            f"{texte_rapport}\n\n"
            "Je la garde sous vérification : je reviendrai vers vous si de nouvelles preuves changent ma confiance, ou si vous préférez la confirmer ou l'écarter."
        )
        suggestions = _suggestions(rapport)
    elif intention == "investiguer":
        question = (situation or {}).get("question") or f"{titre} ?"
        texte = (
            f"Je propose d'ouvrir une investigation. La question : « {question} »\n\n"
            f"{texte_rapport}\n\n"
            "Je peux délimiter le périmètre, formuler les hypothèses concurrentes et lister les preuves qui manquent pour trancher. Par où voulez-vous commencer ?"
        )
        suggestions = [
            {"label": "Formuler les hypothèses concurrentes", "question": f"Quelles hypothèses concurrentes expliquent : {titre} ?"},
            {"label": "Délimiter le périmètre", "question": f"Quel périmètre faut-il investiguer pour : {titre} ?"},
            {"label": "Quelles preuves manquent ?", "question": f"Quelles preuves manquent pour trancher : {titre} ?"},
        ]
    else:
        texte = f"Voici ma lecture de la situation « {titre} ».\n\n{texte_rapport}"
        suggestions = _suggestions(rapport)
    msg = {"role": "flore", "comportement": "expliquer", "texte": texte, "quand": quand, "intention": intention}
    if rapport.get("preuves"):
        msg["preuves"] = rapport["preuves"]
    if suggestions:
        msg["suggestions"] = suggestions
    return msg
