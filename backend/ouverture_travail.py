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
    "connaissance": "decouverte", "comportement": "decouverte", "contradiction": "conformite", "opportunite": "opportunite", "trajectoire": "changement",
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
            "Je la garde sous vérification."
        )
        suggestions = _suggestions(rapport)
    elif intention == "investiguer":
        question = (situation or {}).get("question") or ("Cette opportunité vaut-elle d'être saisie ?" if histoire.get("genre") == "opportunite" else f"{titre} ?")
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
    elif histoire.get("genre") == "opportunite":
        texte = f"J'ai repéré une opportunité : « {titre} ».\n\n{texte_rapport}"
        suggestions = _suggestions(rapport)
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


def messages_reponse_initiative(init: dict, choix: str, nature: str, quand: str) -> list[dict]:
    """Répondre à une proposition du Mesh se passe DANS le travail : la réponse est le message de la personne, Flore l'enregistre.
    nature : « decision » (un choix entre options), « comparaison » (comparer les options), « validation » (demander une validation)."""
    moi = {"role": "utilisateur", "texte": choix, "quand": quand}
    titre = init.get("titre", "")
    if nature == "comparaison":
        texte = (f"Je prépare la comparaison des options pour : {titre}. Pour chacune : ce qu'elle change, ce qu'elle risque, ce qu'elle demande aux équipes concernées.\n\n"
                 "Dites-moi si un critère doit peser plus que les autres, ou si une option manque.")
        flore = {"role": "flore", "comportement": "expliquer", "texte": texte, "quand": quand,
                 "suggestions": [{"label": "Quels critères retenir ?", "question": f"Quels critères retenir pour comparer les options de : {titre} ?"},
                                 {"label": "Quelle option recommandes-tu ?", "question": f"Quelle option recommandes-tu pour : {titre} ?"}]}
    elif nature == "validation":
        texte = (f"J'ai enregistré votre demande de validation pour : {titre}. Je la transmets aux responsables concernés et je vous préviens dès qu'elle est traitée.\n\n"
                 "En attendant, je peux préparer les éléments qui leur seront utiles pour trancher.")
        flore = {"role": "flore", "comportement": "expliquer", "texte": texte, "quand": quand,
                 "suggestions": [{"label": "Prépare les éléments", "question": f"Prépare les éléments utiles à la validation de : {titre}"}]}
    elif nature == "incertain":
        texte = (f"Noté : vous n'avez pas de certitude sur « {titre} ». Je garde la question ouverte et je cherche ce qui permettrait de trancher. "
                 "Je vous reparle dès que j'ai un élément nouveau.")
        flore = {"role": "flore", "comportement": "expliquer", "texte": texte, "quand": quand,
                 "suggestions": [{"label": "Que faudrait-il observer ?", "question": f"Que faudrait-il observer pour trancher : {titre} ?"}]}
    else:
        texte = (f"J'ai enregistré votre réponse : « {choix} ». Méridian l'intègre à sa compréhension et ne vous reposera pas la question sans élément nouveau.\n\n"
                 "Voulez-vous consigner ce que vous en attendez, pour que je l'observe ?")
        flore = {"role": "flore", "comportement": "recommander", "texte": texte, "quand": quand, "propose_passation": True}
    return [moi, flore]


def message_flore_delegation(d: dict, noms_jumeaux: list[str], quand: str) -> dict:
    """Le mandat, dit par Flore à la première personne : ce qu'elle fera, où, combien de temps, ce qu'elle produira et où elle s'arrête."""
    fin = d.get("jusqu_a", "")
    jusqua = f", jusqu'au {int(fin[8:10])}/{fin[5:7]}" if len(fin) >= 10 else ""
    perimetre = ", ".join(noms_jumeaux) or "les jumeaux sélectionnés"
    texte = (f"Vous m'avez confié un mandat : {d['tache'].lower()}.\n\n"
             f"— périmètre : {perimetre} ;\n— durée : {d.get('duree', '')}{jusqua} ;\n"
             f"— sources : {d.get('sources', '')} ;\n— je produirai : {d.get('livrable', '')}.\n\n"
             f"{d.get('validation_requise', '')}. Je vous parle ici dès que j'ai quelque chose à vous dire.")
    return {"role": "flore", "comportement": "expliquer", "type": "mandat", "texte": texte, "quand": quand}


def message_flore_delegation_terminee(d: dict, quand: str) -> dict:
    """Le mandat est arrivé à son terme : Flore le dit, sans prétendre de résultat qu'elle n'a pas — et propose de le reconduire."""
    return {"role": "flore", "comportement": "expliquer", "type": "mandat_termine", "quand": quand,
            "texte": f"Le mandat est arrivé à son terme : « {d['tache']} ». Je n'observe plus ce périmètre. Souhaitez-vous que je le reconduise ?",
            "suggestions": [{"label": "Reconduire 24 h", "question": f"Reconduis pendant 24 h : {d['tache']}"}]}


def decisions_attendues(situation: Optional[dict]) -> list[str]:
    """Les décisions qu'attend une situation, proposées comme réponses rapides sous le message de Flore."""
    return [d for d in (situation or {}).get("decisions_attendues", []) if isinstance(d, str) and d.strip()]
