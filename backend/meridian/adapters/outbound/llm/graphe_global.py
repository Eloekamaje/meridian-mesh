"""Synthèse LLM optionnelle d'un résumé de communautés, sans nouvelle vérité."""
from __future__ import annotations

import os

from strands import Agent

from meridian.adapters.outbound.llm import agent

PROMPT = """Tu synthétises un contexte de graphe d'entreprise déjà calculé. Tu ne dois pas ajouter
de fait, de chiffre, d'entité ou de relation absents du résumé fourni. Tu produis 3 à 6 phrases
factuelles, en français, utiles pour répondre à la question. Si le résumé est insuffisant, dis-le."""


def disponible() -> bool:
    return os.getenv("GRAPH_GLOBAL_SUMMARY", "").strip().lower() in {"llm", "bedrock", "deepseek"}


async def resumer(question: str, resume: dict, modele=None) -> str:
    configure = modele
    if configure is None:
        try:
            configure = agent.modele()
        except Exception:
            return ""
    if configure is None:
        return ""
    import json
    consigne = f"{PROMPT}\n\nQuestion : {question}\n\nRésumé calculé :\n{json.dumps(resume, ensure_ascii=False)}"
    try:
        a = Agent(model=configure, system_prompt=PROMPT, tools=[], callback_handler=None)
        texte = await a.invoke_async(consigne)
        return str(texte or "").strip()[:2000]
    except Exception:
        return ""
