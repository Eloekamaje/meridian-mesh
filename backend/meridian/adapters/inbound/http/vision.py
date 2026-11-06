"""Vision DeepSeek : décrire une image explicitement envoyée, jamais un balayage silencieux."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import acteur as acteur_courant
from meridian.adapters.outbound import vision as vision_adapter

router = APIRouter(prefix="/vision", tags=["vision"])
MAX_IMAGE = 32 * 1024 * 1024
TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.post("")
async def decrire_image(fichier: UploadFile = File(...),
                        question: str = Form("Décris cette image et lis son texte."),
                        acteur: str = Depends(acteur_courant)):
    if not vision_adapter.disponible():
        raise HTTPException(503, f"Provider Vision indisponible : {vision_adapter.provider()}")
    data = await fichier.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "Image trop volumineuse (32 Mo au plus)")
    media = (fichier.content_type or "").split(";")[0].lower()
    if media not in TYPES:
        raise HTTPException(400, "Formats acceptés : JPEG, PNG, GIF, WebP")
    try:
        texte = await asyncio.to_thread(vision_adapter.decrire, data, media, question[:1000])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "Vision DeepSeek indisponible")
    return {"acteur": acteur, "media": media, "texte": texte}
