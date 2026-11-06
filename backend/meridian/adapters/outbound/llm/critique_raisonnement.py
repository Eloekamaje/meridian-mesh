"""Critique croisée d'un dossier par un modèle juge séparé.

Le critique reçoit le livrable, le cadre, les constats et les options — jamais les tokens internes de
l'auteur. Il rend des findings ; il ne réécrit pas le livrable. Le modèle juge est choisi par
`JUMEAU_MODELE_JUGE` et peut être différent du modèle auteur.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from strands import Agent

from meridian.adapters.outbound.llm import agent
from meridian.domain import dossier_raisonnement as domaine

journal = logging.getLogger("meridian.critique_raisonnement")


class FindingJuge(BaseModel):
    constat: str = Field(description="problème précis, actionnable")
    severite: str = Field(default="avertissement", description="info, avertissement, majeure ou critique")
    rubrique: str = Field(default="general", description="options, preuve, risque, validation, schema, etc.")
    preuve: str = Field(default="", description="extrait ou identifiant qui justifie le finding")
    remediation: str = Field(default="", description="correction attendue")


class CritiqueJuge(BaseModel):
    findings: list[FindingJuge] = Field(default_factory=list)
    dissensus: list[str] = Field(default_factory=list)
    verdict: str = Field(default="pass", description="pass, conditional ou fail")


PROMPT = """Tu es un critique indépendant. Tu ne réécris jamais le livrable : tu produis des findings.
Tu reçois le dossier d'un autre agent (demande, cadre, constats, options, réponse, gates). Tu cherches :
- les affirmations non prouvées ou trop sûres ;
- les options manquantes ou non comparables ;
- les risques de sécurité, vie privée, conformité, opérabilité ;
- les hypothèses sans test ;
- les incohérences entre le cadre, les constats et la réponse.
Ne fabrique aucun fait. Si le dossier est incomplet, dis-le. Une sévérité `critique` bloque ;
`majeure` exige une correction ; `avertissement` est à examiner.
Réponds uniquement avec le schéma demandé."""


def _contenu(dossier: domaine.DossierRaisonnement) -> str:
    vue = dossier.as_dict()
    charge = {
        "question": vue.get("question"),
        "demande": vue.get("demande"),
        "cadre": vue.get("cadre"),
        "plan": vue.get("plan"),
        "contexte": vue.get("contexte"),
        "constats": (vue.get("constats") or [])[:20],
        "options": vue.get("options") or [],
        "decision": vue.get("decision"),
        "validation": vue.get("validation") or [],
        "reponse": vue.get("reponse"),
        "gates": vue.get("gates") or [],
    }
    return json.dumps(charge, ensure_ascii=False, default=str)[:60000]


async def critiquer(dossier: domaine.DossierRaisonnement, modele=None):
    """Rend une `Critique` ou None si le modèle juge est indisponible/échoue."""
    if not isinstance(dossier, domaine.DossierRaisonnement):
        return None
    if dossier.niveau not in {"N3", "N4"}:
        return None
    configure = modele
    if configure is None:
        try:
            configure = agent.modele_juge()
        except Exception:
            journal.warning("critique croisée : modèle juge indisponible", exc_info=True)
            return None
    try:
        a = Agent(model=configure, system_prompt=PROMPT, tools=[], callback_handler=None)
        resultat = await a.invoke_async(
            _contenu(dossier), structured_output_model=CritiqueJuge)
        sortie = getattr(resultat, "structured_output", None)
        if sortie is None:
            return None
        findings = tuple(
            domaine.Finding(
                constat=f.constat, severite=f.severite, rubrique=f.rubrique,
                preuve=f.preuve, remediation=f.remediation)
            for f in sortie.findings
        )
        return domaine.Critique(
            cible="livrable",
            findings=findings,
            dissensus=tuple(sortie.dissensus or ()),
            verdict=sortie.verdict if sortie.verdict in domaine.VERDICTS else "conditional",
            reviewer="modele-juge",
            independance="croisee" if dossier.niveau == "N4" else "separee",
        )
    except Exception:
        journal.warning("critique croisée impossible", exc_info=True)
        return None
