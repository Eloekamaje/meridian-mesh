"""Fournisseurs d'embeddings réels : Bedrock (Canada par défaut) ou OpenAI.

Aucun vecteur n'est inventé : sans provider configuré, le retrieval continue en lexical +
graphe. Le modèle et la dimension sont stockés avec chaque chunk.
"""
from __future__ import annotations

import json
import os

__all__ = ["EmbeddingIndisponible", "embed", "modele", "statut"]


class EmbeddingIndisponible(RuntimeError):
    """Aucun provider d'embeddings réel n'est configuré ou disponible."""


def _provider() -> str:
    explicite = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
    if explicite:
        return explicite
    # Un déploiement Bedrock reste au Canada : les embeddings suivent le même fournisseur.
    return "bedrock" if os.getenv("JUMEAU_MODELE", "").strip().lower() == "bedrock" else "openai"


def modele() -> str:
    provider = _provider()
    if provider == "bedrock":
        return os.getenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return "lexical-only"


def statut() -> dict:
    """État lisible du retrieval sémantique, sans appel réseau ni secret."""
    provider = _provider()
    modele_id = modele()
    dimension = 0
    if modele_id != "lexical-only":
        if provider == "bedrock":
            dimension = int(os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))
        elif provider == "openai":
            dimension = 1536
    disponible = False
    detail = "retrieval lexical + graphe seulement"
    if modele_id != "lexical-only":
        try:
            if provider == "bedrock":
                from meridian.adapters.outbound import bedrock_router
                disponible = bedrock_router.session().get_credentials() is not None
                detail = f"provider=bedrock modele={modele_id} region={bedrock_router.region()}"
            elif provider == "openai":
                disponible = bool(os.getenv("OPENAI_API_KEY"))
                detail = f"provider=openai modele={modele_id}"
        except Exception:
            disponible = False
            detail = f"provider={provider} credentials indisponibles"
    if modele_id == "lexical-only":
        detail = "aucun provider d'embeddings configuré"
    return {
        "provider": provider,
        "modele": modele_id,
        "dimension": dimension,
        "semantique": disponible,
        "detail": detail,
    }


def _openai(textes: list[str]) -> list[list[float]]:
    if not os.getenv("OPENAI_API_KEY"):
        raise EmbeddingIndisponible("OPENAI_API_KEY absente")
    from openai import OpenAI
    client = OpenAI()
    reponse = client.embeddings.create(
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        input=textes,
    )
    return [list(item.embedding) for item in reponse.data]


def _bedrock(textes: list[str]) -> list[list[float]]:
    """Titan Text Embeddings V2 par défaut, ou Cohere Embed si le modèle commence par cohere."""
    from meridian.adapters.outbound import bedrock_router
    modele_id = bedrock_router.modele_id("embedding") or "amazon.titan-embed-text-v2:0"
    client = bedrock_router.client("bedrock-runtime")
    vecteurs: list[list[float]] = []
    if modele_id.startswith("cohere."):
        corps = {"texts": textes, "input_type": "search_document"}
        reponse = client.invoke_model(modelId=modele_id, body=json.dumps(corps))
        charge = json.loads(reponse["body"].read())
        vecteurs.extend([list(v) for v in charge.get("embeddings") or []])
        return vecteurs
    dimensions = int(os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))
    for texte in textes:
        corps = {"inputText": texte, "dimensions": dimensions, "normalize": True}
        reponse = client.invoke_model(modelId=modele_id, body=json.dumps(corps))
        charge = json.loads(reponse["body"].read())
        if charge.get("embedding"):
            vecteurs.append(list(charge["embedding"]))
    return vecteurs


def embed(textes: list[str]) -> list[list[float]]:
    """Vecteurs réels ; lève une erreur explicite si le provider n'est pas disponible."""
    textes = [str(t or "") for t in textes]
    provider = _provider()
    try:
        if provider == "bedrock":
            vecteurs = _bedrock(textes)
            if vecteurs:
                return vecteurs
            raise EmbeddingIndisponible("Bedrock n'a rendu aucun vecteur")
        if provider == "openai":
            return _openai(textes)
    except EmbeddingIndisponible:
        raise
    except Exception as e:
        raise EmbeddingIndisponible(f"Provider d'embeddings indisponible : {provider}") from e
    raise EmbeddingIndisponible(
        f"Provider d'embeddings inconnu ou non configuré : {provider or 'aucun'}")


class Embedding:
    """Adaptateur injectable ; l'erreur est explicite, jamais remplacée par du bruit."""

    def __init__(self, fonction=embed):
        self.fonction = fonction

    def __call__(self, textes: list[str]) -> list[list[float]]:
        return self.fonction(textes)
