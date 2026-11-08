"""Machine unifiée ``/demander`` + ``/analyser`` (plan Cognition IA, D9).

Une seule machine, deux profils d'effort. Le profil vient du contrat de preuve
B9 (``contrat_question.contrat_pour`` — ``leger`` | ``standard`` |
``approfondi``) ou d'un effort demandé explicitement, borné aux mêmes valeurs :

- ``leger`` — la sonde a déjà tranché : court-circuit déterministe côté
  conversation, ou budget minimal si la machine profonde est appelée ;
- ``standard`` — le pipeline normal, à budget de base ;
- ``approfondi`` — le « mode analyse » : le même raisonnement à budget élargi
  (``noyau_raisonnement.planifier`` applique le facteur du contrat), avec les
  spécialistes de la composition et le dossier de raisonnement persisté.

Le code profond n'est pas dupliqué : la branche approfondie de ``/demander`` et
la route ``/analyser`` passent toutes deux par :func:`executer_approfondi`, qui
délègue à :func:`meridian.application.analyse_service.executer`. Seule la
sortie diffère : ``demander`` rend la ``reponse``, ``analyser`` rend la
``reponse`` **et** le ``dossier``.
"""
from __future__ import annotations

from typing import Any, Mapping

from meridian.application import analyse_service, contrat_question

__all__ = [
    "APPROFONDI", "EFFORTS", "LEGER", "STANDARD",
    "charge_analyse", "contrat_effort", "executer_approfondi",
]

LEGER, STANDARD, APPROFONDI = (
    contrat_question.LEGER, contrat_question.STANDARD, contrat_question.APPROFONDI)
EFFORTS = contrat_question.EFFORTS


def _effort(valeur: Any) -> str:
    """Un profil d'effort demandé, borné aux valeurs connues ; ``""`` sinon."""
    demande = str(valeur or "").strip().lower()
    return demande if demande in EFFORTS else ""


def contrat_effort(question: Any, *, effort: Any = None,
                   sonde: Mapping | None = None) -> dict:
    """Le contrat B9 du tour, avec l'effort effectif.

    ``effort`` demandé est borné aux profils connus — une valeur inconnue est
    ignorée, jamais honorée. Sans demande, l'effort est celui du contrat de
    preuve calculé depuis la sonde (``standard`` sans sonde) : le contrat rendu
    porte donc toujours l'effort réellement appliqué, pas seulement celui
    souhaité.
    """
    return contrat_question.contrat_pour(question, sonde, effort=effort)


# Les clés qu'`analyse_service.executer` lit sur la charge utile — l'entrée
# unifiée : ``{question, effort?}`` plus les options du mode analyse
# (profondeur, twins, scope, session…). Les clés absentes gardent les défauts
# du service ; ``effort`` absent reste sur son profil nominal (approfondi).
_BASES_ANALYSE = {
    "question": "",
    "situation_id": None,
    "twin_id": None,
    "twin_ids": (),
    "application_id": None,
    "claim_ids": (),
    "profondeur": 2,
    "specialistes": (),
    "profil": None,
    "autorite_max": None,
    "scope": None,
    "domaine": None,
    "surface": None,
    "date": None,
    "options": (),
    "changements": {},
    "criteres": (),
    "session_id": None,
    "decision_id": None,
    "confidence": None,
    "max_tokens": None,
    "effort": None,
    "sonde": None,
    "contrat": None,
}


def charge_analyse(question: Any, *, effort: Any = None, sonde=None,
                   contrat=None, **options) -> dict:
    """La charge unifiée du pipeline profond : ``question`` + profil + options.

    ``options`` ne peut écrire que sur les clés connues — une option inconnue
    est ignorée plutôt que propagée silencieusement.
    """
    payload = dict(_BASES_ANALYSE)
    payload["question"] = question
    for cle, valeur in options.items():
        if cle in payload and valeur is not None:
            payload[cle] = valeur
    demande = _effort(effort)
    if demande:
        payload["effort"] = demande
    if sonde is not None:
        payload["sonde"] = sonde
    if contrat:
        payload["contrat"] = dict(contrat)
    return payload


async def executer_approfondi(tenant: str, acteur: str, payload: Any, *,
                              runtime, acteur_contexte=None, **kwargs) -> dict:
    """Le « mode analyse » de la machine : délègue à ``analyse_service.executer``.

    La route ``/analyser`` (effort ``approfondi`` forcé, réponse + dossier) et
    la branche approfondie de ``/demander`` (réponse seule) passent ici. Le
    résultat porte toujours ``effort`` — l'effort réellement appliqué, mesurable.
    """
    resultat = await analyse_service.executer(
        tenant=tenant, acteur=acteur, payload=payload, runtime=runtime,
        acteur_contexte=acteur_contexte, **kwargs)
    if isinstance(resultat, dict) and not resultat.get("effort"):
        resultat["effort"] = (
            _effort(getattr(payload, "effort", None)) or APPROFONDI)
    return resultat
