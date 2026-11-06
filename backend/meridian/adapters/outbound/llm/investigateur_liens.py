"""Investigateur de liens : propose des candidats bornés, jamais une confirmation.

Le modèle reçoit un contexte déjà construit (cas, bindings, Twins, expositions) et rend des
hypothèses structurées. L'application valide ensuite chaque candidat ; un candidat n'entre
jamais dans le Mesh sans revue propriétaire.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field
from strands import Agent

from meridian.adapters.outbound.llm import agent

journal = logging.getLogger("meridian.investigateur_liens")


class BindingPropose(BaseModel):
    kind: str = Field(description="PROPERTY, GATEWAY_ROUTE, SERVICE, ALIAS, JNDI, QUEUE, TOPIC, DATABASE, FILE")
    nom: str
    valeur: str
    evidence_ids: list[str] = Field(default_factory=list)


class CandidatPropose(BaseModel):
    twin_id: str = Field(description="identifiant d'un Twin présent dans le contexte")
    service: str = ""
    confidence: float = Field(0.5, ge=0, le=1)
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    bindings: list[BindingPropose] = Field(default_factory=list)


class ReponseInvestigation(BaseModel):
    candidates: list[CandidatPropose] = Field(default_factory=list)
    next_check: str = ""


PROMPT = """Tu es l'investigateur de liens de Méridian.

Tu reçois un cas de résolution : une référence d'appel dont la destination n'est pas établie,
les bindings de configuration connus, et les Twins avec leurs expositions.

Règles non négociables :
- propose au maximum 5 candidats ;
- chaque candidat doit désigner un `twin_id` présent dans le contexte ;
- tu peux proposer des bindings vérifiables (PROPERTY, GATEWAY_ROUTE, SERVICE, ALIAS, JNDI,
  QUEUE, TOPIC, DATABASE, FILE) pour expliquer la résolution ;
- tu ne confirmes jamais une relation ; tu produis une hypothèse avec sa raison et ses preuves ;
- si la preuve manque, rends `candidates` vide et une `next_check` précise ;
- n'invente aucun Twin, aucun service, aucun binding ;
- ne mets jamais de secret, de mot de passe, de token ou d'URL avec identifiants ;
- ne propose pas un candidat si la seule justification est une ressemblance de nom sans preuve.

Réponds uniquement avec le schéma `ReponseInvestigation`.
"""


class InvestigateurAgent:
    def __init__(self, modele=None):
        self._modele = modele

    async def proposer(self, demande: dict) -> dict:
        configure = self._modele
        if configure is None:
            try:
                configure = agent.modele()
            except Exception:
                journal.warning("investigateur : modèle indisponible", exc_info=True)
                return {"candidates": [],
                        "next_check": "modèle indisponible ; consulter la configuration ou le propriétaire"}
        a = Agent(model=configure, system_prompt=PROMPT, tools=[], callback_handler=None)
        resultat = await a.invoke_async(
            json.dumps(demande, ensure_ascii=False), structured_output_model=ReponseInvestigation)
        sortie = getattr(resultat, "structured_output", None)
        if sortie is None:
            return {"candidates": [], "next_check": "aucune hypothèse rendue"}
        return sortie.model_dump()
