"""Adaptateur LLM du harness d'exploration : une décision JSON par tour, sans outil natif Strands."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import time

from strands import Agent

from meridian.application.exploration_agent import CONSIGNE
from meridian.adapters.outbound.llm import agent as agent_module

MAX_MESSAGE = 20_000
MAX_CONTENU = 120_000
MAX_TENTATIVES = 3


def _texte(valeur) -> str:
    if isinstance(valeur, str):
        return valeur[:MAX_MESSAGE]
    return json.dumps(valeur, ensure_ascii=False, default=str)[:MAX_MESSAGE]


def serialiser(requete: dict, max_messages: int = 24) -> str:
    outils = json.dumps(requete.get("tools") or {}, ensure_ascii=False)
    messages = requete.get("messages") or []
    lignes = [f"Schémas d'outils disponibles : {outils}"]
    if "claims_count" in requete:
        lignes.append(f"Claims déjà enregistrés : {requete['claims_count']}")
    for message in messages[-max_messages:]:
        lignes.append(f"[{message.get('role', '?')}]\n{_texte(message.get('content'))}")
    texte = "\n\n".join(lignes)
    return texte[:MAX_CONTENU]


def extraire_json(sortie: str) -> dict:
    texte = str(sortie or "").strip()
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte, flags=re.IGNORECASE)
    decodeur = json.JSONDecoder(strict=False)
    for position, caractere in enumerate(texte):
        if caractere != "{":
            continue
        try:
            reponse, _ = decodeur.raw_decode(texte[position:])
        except json.JSONDecodeError:
            continue
        if not isinstance(reponse, dict):
            continue
        if isinstance(reponse.get("final"), str):
            return reponse
        appels = reponse.get("tool_calls")
        if isinstance(appels, list) and 1 <= len(appels) <= 8:
            return reponse
    raise ValueError("l'adaptateur n'a pas rendu une décision JSON exploitable")


def _executer(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class ExplorationAdapter:
    """Implémentation in-process de l'adaptateur attendu par `ExplorationHarness.run`."""

    def __init__(self, modele=None):
        self.modele = modele or agent_module.modele()
        self.derniere_sortie = ""
        try:
            params = self.modele.config.setdefault("params", {})
            params.setdefault("max_tokens", int(os.environ.get("JUMEAU_ENQUETE_MAX_TOKENS", "8192")))
        except (AttributeError, TypeError, ValueError):
            pass

    def __call__(self, requete: dict) -> dict:
        for tentative in range(MAX_TENTATIVES):
            strict = tentative > 0
            contexte = serialiser(requete, 10 if strict else 24)
            prompt = f"{CONSIGNE}\n\nÉtat courant de l'enquête :\n{contexte}"
            if strict:
                prompt = ("Réponds uniquement par un objet JSON valide, sans texte avant ou "
                          "après. Si tu utilises un outil, un seul appel à la fois.\n\n" + prompt)
            assistant = Agent(model=self.modele, system_prompt=CONSIGNE, callback_handler=None)
            try:
                sortie = _executer(assistant.invoke_async(prompt))
            except Exception as erreur:
                message = str(erreur).lower()
                temporaire = any(motif in message for motif in (
                    "maximum token", "rate limit", "timeout", "429", "500", "502",
                    "503", "504", "connection", "temporaire", "temporarily",
                ))
                if tentative < MAX_TENTATIVES - 1 and temporaire:
                    time.sleep(min(2 ** tentative, 5))
                    continue
                raise
            self.derniere_sortie = str(sortie)
            try:
                return extraire_json(str(sortie))
            except ValueError:
                if tentative < MAX_TENTATIVES - 1:
                    time.sleep(0.5)
                    continue
                raise RuntimeError(
                    "adaptateur sans décision JSON après "
                    f"{MAX_TENTATIVES} tentatives : {str(sortie)[:300]}"
                )
        raise RuntimeError("adaptateur sans décision")


__all__ = ["ExplorationAdapter", "extraire_json", "serialiser"]
