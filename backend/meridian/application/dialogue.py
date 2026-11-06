"""Service de dialogue : actes, références et continuité d'un Travail.

Le service ne remplace pas le modèle : il prépare un état borné que le prompt et la session
peuvent utiliser, et met à jour l'état après le tour. Il reste volontairement déterministe.
"""
from __future__ import annotations

import re
import unicodedata

from meridian.domain.dialogue import EtatDialogue

__all__ = ["ACTES", "depuis_case", "mettre_a_jour", "preparer_tour",
           "resoudre_references", "suggestions"]

ACTES = ("question", "suivi", "correction", "confirmation", "meta", "nouveau_sujet", "social")
_PRONOMS = ("il", "elle", "ils", "elles", "en", "y", "celui", "celle", "ce", "cet", "cette",
            "ces", "le", "la", "les", "lui", "leur", "leurs")
_MARQUEURS_SUIVI = ("et ", "alors", "ensuite", "puis", "aussi", "même", "meme", "plus",
                    "moins", "autre", "autres")
_MARQUEURS_CORRECTION = ("non", "je voulais", "je veux dire", "je parlais", "en fait",
                         "corrige", "correction", "plutot", "plutôt", "erreur", "mauvais")
_MARQUEURS_CONFIRMATION = ("oui", "exact", "d'accord", "accord", "confirme", "valide", "ok")
_MARQUEURS_SOCIAL = ("bonjour", "salut", "bonsoir", "merci", "comment vas tu", "ca va")
_MARQUEURS_META = ("pourquoi tu", "pourquoi cette question", "tu as compris", "tu m'as compris",
                   "comment tu", "explique ta question", "qu'est-ce que tu", "tu es sûr")


def _normaliser(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().replace("’", "'").replace("'", " ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texte).split())


def _texte(valeur, maximum=2000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _contient(texte: str, marqueurs) -> bool:
    return any(marqueur in texte for marqueur in marqueurs)


def _acte(question: str, etat: EtatDialogue) -> str:
    normal = _normaliser(question)
    if (any(re.search(rf"\b{m}\b", normal) for m in ("non",))
            or re.search(r"\bpas\s+(ca|celui|celle|ce|cette|ceux)\b", normal)
            or _contient(normal, tuple(m for m in _MARQUEURS_CORRECTION if m != "non"))):
        return "correction"
    if _contient(normal, _MARQUEURS_META):
        return "meta"
    if (_contient(normal, _MARQUEURS_SOCIAL) and len(normal.split()) <= 6
            and not _contient(normal, ("quel", "quelle", "quels", "comment", "pourquoi",
                                       "peux", "peut", "est", "sont"))):
        return "social"
    if _contient(normal, _MARQUEURS_CONFIRMATION) and len(normal.split()) <= 5:
        return "confirmation"
    if etat.derniere_question and (
            _contient(normal, _MARQUEURS_SUIVI)
            or any(f" {mot} " in f" {normal} " for mot in _PRONOMS)):
        return "suivi"
    if any(marqueur in normal for marqueur in ("parle moi", "a propos", "concernant",
                                               "nouveau sujet", "autre sujet")):
        return "nouveau_sujet"
    mots_sujet = {mot for mot in _normaliser(etat.sujet).split() if len(mot) > 3}
    if etat.sujet and mots_sujet and not (mots_sujet & set(normal.split())):
        return "nouveau_sujet"
    return "question"


def _entites(question: str, selection, precedent: EtatDialogue) -> tuple[str, ...]:
    valeurs = list(precedent.entites)
    for identifiant in selection or ():
        if isinstance(identifiant, str) and identifiant not in valeurs:
            valeurs.append(identifiant)
    # Une entité explicitement nommée dans la question reste active.
    normal = _normaliser(question)
    for entite in precedent.entites:
        if _normaliser(entite) and _normaliser(entite) in normal and entite not in valeurs:
            valeurs.append(entite)
    return tuple(valeurs[:20])


def resoudre_references(question: str, etat: EtatDialogue) -> str:
    """Décrit les références que le modèle doit résoudre, sans les inventer."""
    normal = _normaliser(question)
    if not etat.entites or not any(f" {mot} " in f" {normal} " for mot in _PRONOMS):
        return ""
    return "Références possibles dans le fil : " + ", ".join(etat.entites[:8])


def preparer_tour(question: str, *, etat: EtatDialogue | None = None, selection=()) -> dict:
    etat = etat or EtatDialogue()
    acte = _acte(question, etat)
    entites = _entites(question, selection, etat)
    contexte = {
        "acte": acte,
        "interlocuteurs": list(etat.interlocuteurs) or ([etat.acteur] if etat.acteur else []),
        "sujet": etat.sujet,
        "entites": list(entites),
        "derniere_question": etat.derniere_question,
        "derniere_reponse": etat.derniere_reponse,
        "dernier_livrable": etat.dernier_livrable,
    }
    if acte == "correction":
        contexte["correction"] = question
    references = resoudre_references(question, etat)
    if references:
        contexte["references"] = references
    return contexte


def depuis_case(case: dict, *, travail: str = "", acteur: str = "") -> EtatDialogue:
    case = case or {}
    valeur = case.get("dialogue")
    if hasattr(valeur, "as_dict"):
        valeur = valeur.as_dict()
    if isinstance(valeur, dict) and valeur:
        return EtatDialogue.depuis_dict(valeur, travail=travail, acteur=acteur)
    # Reprise d'une conversation antérieure au nouveau modèle de dialogue : le dernier
    # échange donne au moins le sujet et la dernière réponse.
    messages = case.get("conversation") or []
    derniere_question = next(
        (str(m.get("texte") or "") for m in reversed(messages) if m.get("role") == "utilisateur"), "")
    derniere_reponse = next(
        (str(m.get("texte") or "") for m in reversed(messages) if m.get("role") == "flore"), "")
    return EtatDialogue(
        travail=travail, acteur=acteur, sujet=derniere_question[:240],
        derniere_question=derniere_question, derniere_reponse=derniere_reponse,
    )


def mettre_a_jour(etat: EtatDialogue, question: str, reponse: dict, *, selection=()) -> EtatDialogue:
    reponse = dict(reponse or {})
    texte = _texte(reponse.get("reponse") or reponse.get("resume") or "", 2000)
    livrable = ""
    for cle in ("diagrammes", "schemas", "propositions"):
        valeurs = reponse.get(cle) or ()
        if valeurs:
            premier = valeurs[0]
            livrable = str(premier.get("titre") or premier.get("type") or cle) if isinstance(premier, dict) else str(premier)
            break
    if reponse.get("documentCanvas"):
        livrable = str(reponse["documentCanvas"])
    acte = _acte(question, etat)
    sujet = etat.sujet
    if acte in {"question", "nouveau_sujet"} and len(question.split()) > 2:
        sujet = _texte(question, 240)
    entites = list(_entites(question, selection, etat))
    for participant in (reponse.get("jumeaux_participants") or ()):
        if isinstance(participant, dict):
            identifiant = participant.get("id") or participant.get("app_id") or participant.get("nom")
        else:
            identifiant = participant
        if identifiant and str(identifiant) not in entites:
            entites.append(str(identifiant))
    resolution = reponse.get("resolution")
    if isinstance(resolution, dict):
        for cle in ("id", "application_id", "nom"):
            if resolution.get(cle) and str(resolution[cle]) not in entites:
                entites.append(str(resolution[cle]))
    corrections = etat.corrections
    if acte == "correction":
        corrections = (*corrections, _texte(question, 500))[-10:]
    interlocuteurs = etat.interlocuteurs
    if etat.acteur and etat.acteur not in interlocuteurs:
        interlocuteurs = (*interlocuteurs, etat.acteur)
    questions = reponse.get("questions") or ()
    if isinstance(questions, str):
        questions = (questions,)
    questions_ouvertes = tuple(
        str(q.get("texte") if isinstance(q, dict) else q)
        for q in questions if str(q.get("texte") if isinstance(q, dict) else q).strip()
    )
    return etat.avec(
        interlocuteurs=interlocuteurs,
        sujet=sujet, entites=tuple(entites[:20]), derniere_question=_texte(question),
        derniere_reponse=texte, dernier_livrable=livrable,
        corrections=corrections, questions_ouvertes=questions_ouvertes,
    )


def suggestions(etat: EtatDialogue, reponse: dict, *, acte: str = "") -> list[dict]:
    """Trois relances utiles, jamais des actions : elles proposent la suite sans l'exécuter."""
    reponse = dict(reponse or {})
    resultat: list[dict] = []
    if reponse.get("diagrammes"):
        resultat.append({"label": "Comparer avec une cible", "question": "Compare ce diagramme avec une architecture cible."})
        resultat.append({"label": "Limites et hypothèses", "question": "Décris les limites et hypothèses de ce diagramme."})
    elif etat.dernier_livrable:
        resultat.append({"label": "Revenir au livrable", "question": f"Reviens sur le livrable « {etat.dernier_livrable} »."})
    if acte == "correction":
        resultat.append({"label": "Vérifier la correction", "question": "Vérifie que la correction est bien appliquée."})
    if etat.entites:
        resultat.append({"label": f"Approfondir {etat.entites[0]}", "question": f"Approfondis {etat.entites[0]}."})
    if not resultat and etat.sujet:
        resultat.append({"label": "Continuer", "question": f"Continue sur « {etat.sujet[:80]} »."})
    return resultat[:3]
