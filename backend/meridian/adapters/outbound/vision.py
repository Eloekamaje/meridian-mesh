"""Sélectionne le fournisseur Vision sans mélanger les chemins de données."""
from __future__ import annotations

import os

from meridian.adapters.outbound import bedrock_vision
from meridian.adapters.outbound import deepseek

__all__ = ["decrire", "disponible", "provider"]


def provider() -> str:
    explicite = os.getenv("VISION_PROVIDER", "").strip().lower()
    if explicite:
        return explicite
    return "bedrock" if os.getenv("JUMEAU_MODELE", "").strip().lower() == "bedrock" else "deepseek"


def disponible() -> bool:
    p = provider()
    if p == "deepseek":
        return deepseek.disponible()
    if p == "bedrock":
        return bool(os.getenv("BEDROCK_VISION_MODEL", "").strip())
    return False


def decrire(image: bytes, media_type: str = "image/jpeg", question: str = "") -> str:
    p = provider()
    if p == "bedrock":
        return bedrock_vision.decrire(image, media_type, question)
    if p == "deepseek":
        return deepseek.vision(image, media_type, question)
    raise RuntimeError(f"VISION_PROVIDER inconnu : {p}")
