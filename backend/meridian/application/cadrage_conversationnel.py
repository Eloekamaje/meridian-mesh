"""Service de cadrage : une question à la fois, une réponse routée vers un slot.

Ce service est l'autorité de cadrage du dialogue. Le modèle ne décide pas librement de
redemander une information : le noyau choisit le prochain slot bloquant, pose une seule
question, puis route la réponse. Une réponse hors sujet est conservée dans son slot réel
sans faire croire que la question posée a été comprise.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from meridian.domain import cadrage as domaine

MAX_QUESTIONS = 2
_SLOTS_BLOQUANTS_DIAGRAMME = ("existant_ou_cible", "perimetre")
_SLOTS_BLOQUANTS_CONCEPTION = ("perimetre",)
_MOTS_DIAGRAMME = ("diagramme", "diagrame", "diagrammes", "schema", "cartographie", "architecture")
_MOTS_EXISTANT = ("existant", "existante", "actuel", "actuelle", "as is", "cartographie")
_MOTS_CIBLE = ("cible", "futur", "future", "to be", "refonte", "a concevoir", "architecture cible")
_MOTS_PERIMETRE = ("perimetre", "scope", "juste", "seulement", "uniquement", "limite", "limiter",
                   "hors perimetre")
_MOTS_UTILISATEURS = ("utilisateur", "partie prenante", "acteur", "equipe", "population", "client")
_MOTS_CONTRAINTES = ("contrainte", "budget", "delai", "echeance", "securite", "reglement", "temps")
_MOTS_CRITERES = ("critere", "succes", "resultat attendu", "resultat vise", "objectif de succes")
_MOTS_OPTIONS = ("option", "ecartee", "ecarter", "alternative")


def _normaliser(valeur) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().replace("’", "'").replace("'", " ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texte).split())


def _contient(texte: str, marqueurs) -> bool:
    return any(marqueur in texte for marqueur in marqueurs)


def _type_livrable(question: str, but: str) -> str:
    normal = _normaliser(question)
    if _contient(normal, _MOTS_DIAGRAMME):
        return "diagramme"
    return "proposition" if but in {"concevoir", "decider"} else "reponse"


def _slots_bloquants(etat: domaine.CadrageConversationnel) -> tuple[str, ...]:
    if etat.type_livrable == "diagramme":
        return _SLOTS_BLOQUANTS_DIAGRAMME
    if etat.type_livrable == "proposition":
        return _SLOTS_BLOQUANTS_CONCEPTION
    return ()


def _manquants(etat: domaine.CadrageConversationnel) -> tuple[str, ...]:
    return tuple(slot for slot in _slots_bloquants(etat) if not etat.slot(slot).rempli)


def initialiser(question: str, demande, contexte=None) -> domaine.CadrageConversationnel:
    """Crée l'état initial ; ne pose aucune question tant que l'appelant n'a pas demandé la suite."""
    contexte = dict(contexte or {})
    dialogue = dict(contexte.get("dialogue") or {})
    objet = (contexte.get("objet") or getattr(demande, "objet", "")
             or (dialogue.get("entites") or [""])[0])
    type_livrable = _type_livrable(question, getattr(demande, "but", "repondre"))
    # Une question méta (« pourquoi tu ne l'as pas dessiné ? ») porte sur la réponse
    # précédente, pas sur une nouvelle conception : elle ne doit pas rouvrir un cadrage.
    if dialogue.get("acte") == "meta":
        type_livrable = "reponse"
    slots = []
    for identifiant in domaine.SLOTS:
        valeur = contexte.get(identifiant) or ""
        if isinstance(valeur, (list, tuple)):
            valeur = valeur[0] if valeur else ""
        slots.append(domaine.SlotCadrage(
            id=identifiant, valeur=str(valeur or ""),
            statut="confirme" if valeur else "absent", source="contexte" if valeur else ""))
    etat = domaine.CadrageConversationnel(
        question=question, objet=objet, type_livrable=type_livrable, slots=tuple(slots))
    # Une demande peut déjà porter sa réponse : « architecture cible », « processus existant ».
    etat = _appliquer(etat, _detecter(question), source="utilisateur")
    # « Fais-en un diagramme » après une réponse sur un existant : la référence est le dernier
    # sujet, et le diagramme décrit ce qui vient d'être observé. On l'explicite comme inféré.
    if (etat.type_livrable == "diagramme" and dialogue.get("acte") == "suivi"
            and dialogue.get("derniere_reponse") and not etat.slot("existant_ou_cible").rempli):
        etat = etat.avec_slot("existant_ou_cible", "existant", source="dialogue", statut="infere")
    if (etat.type_livrable == "diagramme" and dialogue.get("entites")
            and not etat.slot("perimetre").rempli):
        etat = etat.avec_slot("perimetre", ", ".join(dialogue["entites"][:5]),
                              source="dialogue", statut="infere")
    return avancer(etat)


def _detecter(texte: str, slot_attendu: str | None = None) -> dict[str, str]:
    normal = _normaliser(texte)
    valeurs = {}
    if _contient(normal, _MOTS_EXISTANT):
        valeurs["existant_ou_cible"] = "existant"
    elif _contient(normal, _MOTS_CIBLE):
        valeurs["existant_ou_cible"] = "cible"
    if _contient(normal, _MOTS_UTILISATEURS):
        valeurs["utilisateurs"] = texte
    if _contient(normal, _MOTS_CONTRAINTES):
        valeurs["contraintes"] = texte
    if _contient(normal, _MOTS_CRITERES):
        valeurs["criteres_succes"] = texte
    if _contient(normal, _MOTS_OPTIONS):
        valeurs["options_ecartees"] = texte
    if _contient(normal, _MOTS_PERIMETRE) or (slot_attendu == "perimetre" and not valeurs):
        valeurs["perimetre"] = texte
    # Une réponse courte à une question « existant ou cible » qui parle d'abord du périmètre
    # est une réponse de périmètre, pas une réponse A/B inventée.
    if slot_attendu == "existant_ou_cible" and "existant_ou_cible" not in valeurs:
        if not valeurs and len(normal.split()) <= 5:
            valeurs["perimetre"] = texte
    return valeurs


def recevoir_reponse(etat: domaine.CadrageConversationnel, reponse: str,
                     acte: str | None = None) -> domaine.CadrageConversationnel:
    """Route une réponse vers le(s) slot(s) qu'elle adresse réellement.

    Un acte ``meta`` ne consomme pas la question ouverte ; un nouveau sujet ou une
    correction l'annule au lieu de la remplir avec un texte qui n'y répond pas.
    """
    if acte == "meta":
        return etat
    if acte in {"nouveau_sujet", "correction"} and etat.question_en_attente:
        return replace(etat, question_en_attente=None, statut="pret")
    if not etat.question_en_attente:
        return avancer(_appliquer(etat, _detecter(reponse), source="utilisateur"))
    attendu = etat.question_en_attente.slot
    valeurs = _detecter(reponse, attendu)
    if attendu == "existant_ou_cible" and "existant_ou_cible" not in valeurs:
        # La question A/B reste ouverte ; la réponse de périmètre est quand même conservée.
        etat = _appliquer(etat, valeurs, source="utilisateur")
        return avancer(replace(etat, question_en_attente=None, statut="en_cours"))
    if not valeurs:
        valeurs = {attendu: reponse}
    etat = _appliquer(etat, valeurs, source="utilisateur", question_id=etat.question_en_attente.id)
    return avancer(replace(etat, question_en_attente=None, statut="en_cours"))


def _appliquer(etat, valeurs: dict[str, str], *, source="utilisateur", question_id="") -> domaine.CadrageConversationnel:
    attendu = etat.question_en_attente.slot if etat.question_en_attente else ""
    for identifiant, valeur in valeurs.items():
        etat = etat.avec_slot(identifiant, valeur, source=source, statut="confirme",
                              question_id=question_id if identifiant == attendu else "")
    return etat


def _question(etat: domaine.CadrageConversationnel, slot: str) -> domaine.QuestionCadrage:
    perimetre = etat.slot("perimetre").valeur
    if slot == "existant_ou_cible":
        if perimetre:
            texte = (f"J'ai noté le périmètre « {perimetre} ». Le diagramme doit-il décrire "
                     "ce processus existant ou une architecture cible ?")
        else:
            texte = "Le diagramme doit-il décrire l'existant ou une architecture cible ?"
    elif slot == "perimetre":
        texte = "Quel est le périmètre exact à couvrir, et qu'est-ce qui est exclu ?"
    else:
        texte = "Quelle précision manque pour cadrer la demande ?"
    return domaine.QuestionCadrage(id=f"q-{etat.posees + 1}", slot=slot, texte=texte)


def avancer(etat: domaine.CadrageConversationnel) -> domaine.CadrageConversationnel:
    """Pose au plus une question ; après le budget, infère et poursuit."""
    manquants = _manquants(etat)
    if not manquants:
        return replace(etat, question_en_attente=None, statut="pret")
    if etat.posees >= MAX_QUESTIONS:
        # Budget de clarification épuisé : on ne boucle pas, on explicite l'hypothèse.
        for slot in manquants:
            if slot == "existant_ou_cible" and etat.type_livrable == "diagramme":
                etat = etat.avec_slot(slot, "cible", source="infere", statut="infere")
            elif slot == "perimetre" and etat.objet:
                etat = etat.avec_slot(slot, etat.objet, source="infere", statut="infere")
        return replace(etat, question_en_attente=None, statut="pret")
    slot = manquants[0]
    question = _question(etat, slot)
    return replace(etat, question_en_attente=question, posees=etat.posees + 1, statut="en_attente")


def contexte_pour_noyau(etat: domaine.CadrageConversationnel) -> dict:
    return etat.contexte()


def depuis_dict(valeur) -> domaine.CadrageConversationnel | None:
    return domaine.CadrageConversationnel.depuis_dict(valeur)
