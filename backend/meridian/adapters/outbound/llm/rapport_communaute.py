"""Synthèse LLM d'un rapport de communauté ; jamais de fait ajouté au graphe."""
from __future__ import annotations

import os

from strands import Agent

from meridian.adapters.outbound.llm import agent

PROMPT = """Tu synthétises un rapport de communauté déjà calculé. Tu ne peux citer que les entités,
relations et domaines présents. Tu produis 3 à 6 phrases factuelles en français. Si le rapport est
insuffisant, dis-le. N'invente aucun chiffre, aucune relation et aucune preuve."""


def disponible() -> bool:
    return os.getenv("COMMUNITY_SUMMARY", "").strip().lower() in {"llm", "bedrock", "deepseek"}


async def resumer(texte: str, modele=None) -> str:
    configure = modele
    if configure is None:
        try:
            configure = agent.modele()
        except Exception:
            return ""
    if configure is None:
        return ""
    try:
        a = Agent(model=configure, system_prompt=PROMPT, tools=[], callback_handler=None)
        sortie = await a.invoke_async(texte)
        return str(sortie or "").strip()[:2000]
    except Exception:
        return ""
