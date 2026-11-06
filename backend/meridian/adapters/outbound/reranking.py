"""Reranking optionnel des chunks : aucun reranker par défaut, Bedrock si configuré.

Le reranker ne crée pas de connaissance : il ne fait que réordonner des candidats déjà
filtrés par tenant, ACL, source et version.
"""
from __future__ import annotations

import os

__all__ = ["RerankIndisponible", "rerank"]


class RerankIndisponible(RuntimeError):
    pass


def _bedrock(question: str, chunks: list[dict], top_n: int) -> list[dict]:
    from meridian.adapters.outbound import bedrock_router
    modele = os.getenv("BEDROCK_RERANK_MODEL", "").strip() or bedrock_router.modele_id("rerank")
    if not modele:
        raise RerankIndisponible("BEDROCK_RERANK_MODEL absent")
    client = bedrock_router.client("bedrock-runtime")
    documents = [str(chunk.get("texte") or "")[:4000] for chunk in chunks[:20]]
    corps = {"query": question, "documents": documents, "top_n": min(top_n, len(documents))}
    reponse = client.invoke_model(modelId=modele, body=__import__("json").dumps(corps))
    charge = __import__("json").loads(reponse["body"].read())
    resultats = charge.get("results") or charge.get("rerank_results") or []
    ordonnes = []
    for resultat in resultats:
        index = resultat.get("index")
        if isinstance(index, int) and 0 <= index < len(chunks):
            chunk = dict(chunks[index])
            chunk["rerank_score"] = resultat.get("relevance_score") or resultat.get("score")
            ordonnes.append(chunk)
    return ordonnes or chunks


def rerank(question: str, chunks: list[dict], *, top_n: int | None = None) -> list[dict]:
    """Réordonne si un provider est configuré ; sinon rend les candidats inchangés."""
    provider = os.getenv("RERANK_PROVIDER", "none").strip().lower()
    if provider in {"", "none", "off"}:
        return chunks
    if provider == "bedrock":
        try:
            return _bedrock(question, chunks, top_n or len(chunks))
        except RerankIndisponible:
            return chunks
        except Exception:
            return chunks
    return chunks
