"""Routage Bedrock par besoin : chat, juge, vision, embeddings, rerank.

Le profil modèle est déclaratif. Il ne dépend ni du domaine ni d'un prompt : la politique choisit
un rôle, le routeur rend un model_id. Les credentials viennent du profil AWS de la machine
(`AWS_PROFILE`), jamais d'une clé recopiée dans le dépôt.
"""
from __future__ import annotations

import json
import os

__all__ = ["PROFILS", "client", "modele_id", "region", "session"]

PROFILS = ("chat", "fast", "judge", "vision", "embedding", "rerank")
_ENV = {
    "chat": ("BEDROCK_MODEL_CHAT", "BEDROCK_MODELE"),
    "fast": ("BEDROCK_MODEL_FAST", "BEDROCK_MODELE"),
    "judge": ("BEDROCK_MODEL_JUDGE", "BEDROCK_MODELE"),
    "vision": ("BEDROCK_MODEL_VISION", "BEDROCK_VISION_MODEL"),
    "embedding": ("BEDROCK_MODEL_EMBEDDING", "BEDROCK_EMBEDDING_MODEL"),
    "rerank": ("BEDROCK_MODEL_RERANK", "BEDROCK_RERANK_MODEL"),
}


def region() -> str:
    return os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION") or "ca-central-1"


def _mapping() -> dict:
    try:
        valeur = json.loads(os.getenv("BEDROCK_MODELES", "{}"))
    except (TypeError, ValueError):
        return {}
    return valeur if isinstance(valeur, dict) else {}


def modele_id(profil: str = "chat") -> str:
    profil = profil if profil in PROFILS else "chat"
    mapping = _mapping()
    if mapping.get(profil):
        return str(mapping[profil]).strip()
    for variable in _ENV[profil]:
        valeur = os.getenv(variable, "").strip()
        if valeur:
            return valeur
    return ""


def session():
    """Session boto3 du profil AWS de la machine (AWS_PROFILE), jamais une clé du dépôt."""
    import boto3
    profil = os.getenv("AWS_PROFILE", "").strip() or None
    return boto3.Session(profile_name=profil, region_name=region()) if profil else boto3.Session(region_name=region())


def client(service: str = "bedrock-runtime"):
    return session().client(service)
