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
    r"(confirmer|confirmation|voulez[- ]vous|souhaitez[- ]vous|"
    r"je peux (?:lancer|preparer|préparer|ouvrir)|"
    r"avant de (?:lancer|demarrer|démarrer|executer|exécuter)|"
    r"en attente de (?:votre )?(?:accord|confirmation))",
    re.IGNORECASE,
)
_RE_EXECUTION = re.compile(
    r"(j'ai (?:lance|lancé|démarre|demarre|démarré|ouvert|cree|créé|execute|exécuté)|"
    r"(?:investigation|analyse|rapport|audit|action|workflow) "
    r"(?:lancee|lancée|demarree|démarrée|ouverte|cree|créée|executee|exécutée))",
    re.IGNORECASE,
)
_RE_NEGATION = re.compile(r"(pas|jamais|aucune|sans|n'ai pas|non)\s*$", re.IGNORECASE)

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


def appliquer(question: str, reponse: Mapping[str, Any] | None) -> dict:
    """Ajoute une confirmation si l'action est demandée mais non confirmée.

    Une réponse qui affirme avoir exécuté l'action est corrigée explicitement. La
    fonction est idempotente : un tour déjà marqué ``contrat_action`` n'est pas
    réécrit.
    """
    resultat = dict(reponse or {})
    if resultat.get(APPLIQUER) or not est_demande_action(question):
        return resultat
    texte = str(resultat.get("reponse") or "").strip()
    if not texte:
        return resultat
    execution = _affirme_execution(texte)
    confirmation = _a_confirmation(texte)
    if not execution and confirmation:
        resultat[APPLIQUER] = "conforme"
        return resultat
    if execution:
        texte += ("\n\n**Correction** : je n'ai pas exécuté cette action. "
                  "Aucune investigation, analyse ou écriture n'a été lancée.")
    if not confirmation:
        texte += ("\n\n**Confirmation requise** : voulez-vous que je prépare cette "
                  "investigation ? Je ne la lancerai qu'après votre accord.")
    resultat["reponse"] = texte.strip()
    resultat["comportement"] = "proposer"
    resultat["action_en_attente"] = "investigation"
    resultat[APPLIQUER] = "corrige" if execution else "confirmation_ajoutee"
    return resultat
