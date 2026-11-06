"""Contrat d'action d'un tour : proposer avant d'exécuter.

Flore peut préparer une investigation, une analyse ou un changement, mais une action
à effet de bord ne doit jamais être présentée comme exécutée sans confirmation
humaine. Ce module est volontairement déterministe : il ne remplace pas le modèle,
il corrige une réponse qui affirme une exécution ou oublie la confirmation.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

__all__ = ["APPLIQUER", "est_demande_action", "appliquer"]

_RE_ACTION = re.compile(
    r"\b(?:lance[rz]?|lancer|demarre[rz]?|démarre[rz]?|demarrer|démarrer|"
    r"ouvre[rz]?|ouvrir|cree[rz]?|crée[rz]?|creer|créer|investigue[rz]?|investiguer|"
    r"declenche[rz]?|déclenche[rz]?|declencher|déclencher)\b",
    re.IGNORECASE,
)
_RE_OBJET_ACTION = re.compile(
    r"\b(investigation|analyse|enquete|enquête|rapport|audit|changement|"
    r"correction|action|workflow)\b",
    re.IGNORECASE,
)
_RE_CONFIRMATION = re.compile(
    r"(confirmez[- ]vous|voulez[- ]vous|souhaitez[- ]vous|"
    r"je peux (?:lancer|preparer|préparer|ouvrir)|"
    r"avant de (?:lancer|demarrer|démarrer|executer|exécuter)|"
    r"en attente de (?:votre )?(?:accord|confirmation)|"
    r"confirmation requise|merci de confirmer)",
    re.IGNORECASE,
)
_RE_EXECUTION = re.compile(
    r"(j'ai (?:lance|lancé|démarre|demarre|démarré|ouvert|cree|créé|execute|exécuté)|"
    r"(?:investigation|analyse|rapport|audit|action|workflow) "
    r"(?:lancee|lancée|demarree|démarrée|ouverte|cree|créée|executee|exécutée))",
    re.IGNORECASE,
)
_RE_NEGATION = re.compile(r"(pas|jamais|aucune|sans|n'ai pas|non)\s*$", re.IGNORECASE)
_RE_ARTEFACT = re.compile(
    r"(j'ai (?:ajout[eé]|d[eé]pos[eé]|cr[eé][eé]) "
    r"(?:au travail )?(?:le |un )?(?:rapport|livrable)|"
    r"(?:rapport|livrable) (?:ajout[eé]|d[eé]pos[eé]|cr[eé][eé]))",
    re.IGNORECASE,
)

APPLIQUER = "contrat_action"


def est_demande_action(question: str) -> bool:
    """Vrai si le tour demande explicitement une action sur un objet nommé."""
    texte = str(question or "")
    return bool(_RE_ACTION.search(texte) and _RE_OBJET_ACTION.search(texte))


def _a_confirmation(texte: str) -> bool:
    return bool(_RE_CONFIRMATION.search(texte))


def _affirme_execution(texte: str) -> bool:
    for trouve in _RE_EXECUTION.finditer(texte):
        avant = texte[max(0, trouve.start() - 40):trouve.start()]
        if not _RE_NEGATION.search(avant):
            return True
    return False


def _a_artefact(reponse: Mapping[str, Any]) -> bool:
    return bool(reponse.get("documentCanvas") or reponse.get("documentTexte")
                or reponse.get("livrable_id") or reponse.get("livrables"))


def _affirme_artefact(texte: str) -> bool:
    for trouve in _RE_ARTEFACT.finditer(texte):
        avant = texte[max(0, trouve.start() - 40):trouve.start()]
        if not _RE_NEGATION.search(avant):
            return True
    return False


def appliquer(question: str, reponse: Mapping[str, Any] | None) -> dict:
    """Ajoute une confirmation si l'action est demandée mais non confirmée.

    Une réponse qui affirme avoir exécuté l'action est corrigée explicitement. La
    fonction est idempotente : un tour déjà marqué ``contrat_action`` n'est pas
    réécrit.
    """
    resultat = dict(reponse or {})
    if resultat.get(APPLIQUER):
        return resultat
    texte = str(resultat.get("reponse") or "").strip()
    if not texte:
        return resultat
    action = est_demande_action(question)
    artefact = _affirme_artefact(texte) and not _a_artefact(resultat)
    if not action and not artefact:
        return resultat
    execution = _affirme_execution(texte)
    confirmation = _a_confirmation(texte)
    if artefact:
        texte += ("\n\n**Correction** : aucun rapport n'a été déposé dans le Travail. "
                  "Je peux le préparer ; confirmez-vous que je dois le créer ?")
        resultat["action_en_attente"] = "rapport"
        resultat[APPLIQUER] = "artefact_corrige"
    elif execution:
        texte = ("**Je n'ai pas exécuté cette action.** Aucune investigation, analyse "
                 "ou écriture n'a été lancée.\n\n" + texte)
        if not confirmation:
            texte += ("\n\n**Confirmation requise** : voulez-vous que je prépare cette "
                      "investigation ? Je ne la lancerai qu'après votre accord.")
        resultat["action_en_attente"] = "investigation"
        resultat[APPLIQUER] = "corrige"
    elif not confirmation:
        texte = ("**Je n'ai pas lancé l'investigation.** Voici les éléments préparatoires ; "
                 "confirmez avant toute action.\n\n" + texte)
        texte += ("\n\n**Confirmation requise** : voulez-vous que je prépare cette "
                  "investigation ? Je ne la lancerai qu'après votre accord.")
        resultat["action_en_attente"] = "investigation"
        resultat[APPLIQUER] = "confirmation_ajoutee"
    else:
        resultat[APPLIQUER] = "conforme"
        return resultat
    resultat["reponse"] = texte.strip()
    resultat["comportement"] = "proposer"
    return resultat
