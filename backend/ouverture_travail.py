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
    if intention != "suivre" and decisions_attendues(situation):
        msg["decisions"] = decisions_attendues(situation)
    return msg


def _preuves_initiative(init: dict) -> list[dict]:
    return [{"source": "Mesh", "detail": p} if isinstance(p, str) else p for p in init.get("preuves", [])]


def message_flore_initiative(init: dict, intention: str, quand: str) -> dict:
    """Ouverture d'un travail depuis une proposition du Mesh (Radar, À traiter) : Flore présente ce que Méridian a découvert,
    pourquoi la personne est concernée, et ce qui est attendu d'elle."""
    titre = init.get("titre", "")
    faits = [init.get("raison", "").strip()]
    if init.get("pourquoi_vous"):
        faits.append(f"Pourquoi vous : {init['pourquoi_vous']}")
    ligne = " · ".join(x for x in (f"Impact : {init['impact']}" if init.get("impact") else "", f"Confiance : {init['confiance']}" if init.get("confiance") else "",
                                    f"Périmètre : {init['perimetre']}" if init.get("perimetre") else "") if x)
    if ligne:
        faits.append(ligne)
    if init.get("attendu"):
        faits.append(f"Ce que j'attends de vous : {init['attendu']}")
    corps = "\n\n".join(f for f in faits if f)
    if intention == "investiguer":
        texte = f"Je propose d'ouvrir une investigation. La question : « {titre} »\n\n{corps}\n\nJe peux délimiter le périmètre, formuler les hypothèses concurrentes et lister les preuves qui manquent. Par où voulez-vous commencer ?"
        suggestions = [
            {"label": "Formuler les hypothèses concurrentes", "question": f"Quelles hypothèses concurrentes expliquent : {titre} ?"},
            {"label": "Délimiter le périmètre", "question": f"Quel périmètre faut-il investiguer pour : {titre} ?"},
            {"label": "Quelles preuves manquent ?", "question": f"Quelles preuves manquent pour trancher : {titre} ?"},
        ]
    elif intention == "suivre":
        texte = f"Voici ce que Méridian a découvert : {titre}.\n\n{corps}\n\nJe le garde sous surveillance : je reviendrai vers vous si ma compréhension change ou si une décision devient nécessaire."
        suggestions = [{"label": "Que surveilles-tu exactement ?", "question": f"Que surveilles-tu exactement pour : {titre} ?"}]
    else:
        texte = f"Voici ce que Méridian a découvert : {titre}.\n\n{corps}"
        suggestions = [
            {"label": "Que reste-t-il à comprendre ?", "question": f"Que reste-t-il à comprendre sur : {titre} ?"},
            {"label": "Quels jumeaux sont concernés ?", "question": f"Quels jumeaux sont concernés par : {titre} ?"},
            {"label": "Que puis-je faire maintenant ?", "question": f"Que puis-je faire maintenant pour : {titre} ?"},
        ]
    msg = {"role": "flore", "comportement": "expliquer", "texte": texte, "quand": quand, "intention": intention, "suggestions": suggestions}
    if init.get("preuves"):
        msg["preuves"] = _preuves_initiative(init)
    return msg


def decisions_attendues(situation: Optional[dict]) -> list[str]:
    """Les décisions qu'attend une situation, proposées comme réponses rapides sous le message de Flore."""
    return [d for d in (situation or {}).get("decisions_attendues", []) if isinstance(d, str) and d.strip()]
