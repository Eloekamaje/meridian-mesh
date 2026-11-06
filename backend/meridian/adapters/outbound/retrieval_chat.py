"""Façade unique du retrieval de chat : mémoire, documents, communautés, graphe."""
from __future__ import annotations

import asyncio
import os

from meridian.adapters.outbound.neo4j import graph_store
from meridian.adapters.outbound.postgres import community_store
from meridian.adapters.outbound.postgres import documentation as documentation_reader
from meridian.adapters.outbound.postgres import memoire_dialogue
from meridian.adapters.outbound.llm import graphe_global as graphe_global_llm
from meridian.application import graphe_global

__all__ = ["contexte"]


async def contexte(tenant: str, question: str, *, twin_ids=(), acteur: str = "",
                   role: str = "", espace: str = "", graph_ids=None,
                   domaines=None, consommateur=None, twin_proprietaire=None) -> dict:
    """Un seul point d'entrée ; chaque source reste un candidat, jamais une vérité."""
    resultat = {}
    memoires = await memoire_dialogue.recuperer(
        tenant, question, twin_ids, consommateur=consommateur,
        twin_proprietaire=twin_proprietaire)
    if memoires:
        resultat["memoire"] = memoires
    documents = await documentation_reader.chercher(
        tenant, question, twin_ids=twin_ids, acteur=acteur, role=role, espace=espace)
    if documents:
        resultat["documentation"] = documents
    if os.getenv("GRAPH_RAG_MODE", "local").strip().lower() == "global":
        ids = list(graph_ids or twin_ids or ())
        communautes = await asyncio.to_thread(
            community_store.chercher, tenant, question,
            acteur=acteur, role=role, espace=espace)
        if communautes:
            resultat["graphe_global"] = {
                "mode": "global-communautes",
                "communautes": communautes,
                "resume": " ; ".join(c.get("rapport") or "" for c in communautes[:5]),
            }
        elif ids:
            contexte_graphe = graph_store.ouvrir()
            try:
                resume = graphe_global.resume_contextuel(
                    contexte_graphe["store"], tenant, ids, domaines_connus=domaines)
            finally:
                contexte_graphe["fermer"]()
            if resume:
                if graphe_global_llm.disponible() and not resume.get("communautes"):
                    synthese = await graphe_global_llm.resumer(question, resume)
                    if synthese:
                        resume["synthese"] = synthese
                resultat["graphe_global"] = resume
    return resultat
