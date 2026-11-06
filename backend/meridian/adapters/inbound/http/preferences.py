"""API des préférences de conversation de l'acteur courant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth import acteur as acteur_courant
from meridian.application import preferences as application
from meridian.domain import preferences as domaine

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferencesPayload(BaseModel):
    ton: str = Field("direct", max_length=40)
    langue: str = Field("fr", max_length=20)
    longueur: str = Field("moyenne", max_length=20)
    suggestions: bool = True


@router.get("")
async def lire_preferences(request: Request, acteur: str = Depends(acteur_courant)):
    db = request.app.state.db
    doc = await db.preferences.find_one({"acteur": acteur}, {"_id": 0}) or {}
    return application.depuis_doc(doc).as_dict()


@router.put("")
async def ecrire_preferences(payload: PreferencesPayload, request: Request,
                             acteur: str = Depends(acteur_courant)):
    p = domaine.Preferences(ton=payload.ton, langue=payload.langue,
                            longueur=payload.longueur, suggestions=payload.suggestions)
    await request.app.state.db.preferences.update_one(
        {"acteur": acteur}, {"$set": {"acteur": acteur, **p.as_dict()}}, upsert=True)
    return p.as_dict()
