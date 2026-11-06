"""Vision sur Amazon Bedrock (Converse API), pour les déploiements canadiens sans DeepSeek."""
from __future__ import annotations

import os

__all__ = ["decrire"]

_FORMATS = {"image/jpeg": "jpeg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}


def decrire(image: bytes, media_type: str = "image/jpeg", question: str = "") -> str:
    fmt = _FORMATS.get(media_type)
    if fmt is None:
        raise ValueError("format d'image non supporté")
    from meridian.adapters.outbound import bedrock_router
    modele = os.getenv("BEDROCK_VISION_MODEL", "").strip() or bedrock_router.modele_id("vision")
    if not modele:
        raise RuntimeError("BEDROCK_VISION_MODEL absent")
    from meridian.adapters.outbound import bedrock_router
    client = bedrock_router.client("bedrock-runtime")
    reponse = client.converse(
        modelId=modele,
        messages=[{"role": "user", "content": [
            {"text": question or "Décris précisément cette image et lis son texte."},
            {"image": {"format": fmt, "source": {"bytes": image}}},
        ]}],
        inferenceConfig={"maxTokens": 1200, "temperature": 0},
    )
    blocs = ((reponse.get("output") or {}).get("message") or {}).get("content") or []
    return "\n".join(str(bloc.get("text") or "") for bloc in blocs if isinstance(bloc, dict)).strip()
