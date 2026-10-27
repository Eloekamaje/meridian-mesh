"""API du jumeau réel (phase 0) : Claims prouvés, extraits vérifiés, revue humaine.

ponytail: l'acteur vient de l'en-tête X-Persona de la démo ; OIDC + Cedar en phase 1 (Architecture Jumeau §4.2).
"""
import json
import logging
import os
from typing import Literal, Optional

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jumeau import agent, connaissance, depot
from jumeau.source_git import extrait

router = APIRouter(prefix="/v2", tags=["jumeau"])
journal = logging.getLogger("meridian.jumeau")
FILS = agent.FilsActifs()


def connexion():
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


class Revue(BaseModel):
    decision: Literal["ACCEPTED", "CONTESTED"]
    motif: Optional[str] = Field(default=None, max_length=2000)


@router.get("/jumeaux")
def lister_jumeaux(conn=Depends(connexion)):
    return depot.lister_jumeaux(conn)


@router.get("/jumeaux/{jumeau_id}/claims")
def lister_claims(jumeau_id: str, conn=Depends(connexion)):
    return depot.lister_claims(conn, jumeau_id)


@router.get("/preuves/{preuve_id}/extrait")
def lire_extrait(preuve_id: int, conn=Depends(connexion)):
    preuve = depot.preuve_par_id(conn, preuve_id)
    if not preuve:
        raise HTTPException(404, "Preuve introuvable")
    try:
        return {"chemin": preuve["chemin"], "sha": preuve["sha"], **extrait(preuve)}
    except ValueError:
        raise HTTPException(422, "Preuve invalide")


@router.post("/claims/{claim_id}/revue")
def reviser(claim_id: int, revue: Revue, conn=Depends(connexion),
            x_persona: str = Header(default="architecte", max_length=64)):
    try:
        depot.reviser(conn, claim_id, x_persona, revue.decision, revue.motif)
    except LookupError:
        raise HTTPException(404, "Claim introuvable")
    return {"ok": True}


# ---------- Code et conversation (le jumeau se connaît par son code) ----------

class Message(BaseModel):
    texte: str = Field(min_length=1, max_length=4000)


def _contexte(conn, jumeau_id, acteur):
    jumeau = depot.jumeau_par_id(conn, jumeau_id)
    source = depot.source_du_jumeau(conn, jumeau_id)
    if not jumeau or not source or not source["index_code"]:
        raise HTTPException(404, "Jumeau sans code ingéré")
    claims = connaissance.connaissances(conn, jumeau_id, limite=500)
    return {"jumeau": jumeau, "source": source, "claims": claims, "acteur": acteur}


@router.get("/jumeaux/{jumeau_id}/code")
def lire_code(jumeau_id: str, chemin: str, debut: int, fin: int, conn=Depends(connexion)):
    source = depot.source_du_jumeau(conn, jumeau_id)
    if not source:
        raise HTTPException(404, "Jumeau sans code ingéré")
    try:
        return connaissance.lire_code(source, chemin, debut, fin)
    except LookupError:
        raise HTTPException(404, "Fichier absent au commit ingéré")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/jumeaux/{jumeau_id}/conversation")
def historique(jumeau_id: str, x_persona: str = Header(default="architecte", max_length=64)):
    return agent.historique(jumeau_id, x_persona)


@router.delete("/jumeaux/{jumeau_id}/conversation")
def oublier(jumeau_id: str, x_persona: str = Header(default="architecte", max_length=64)):
    agent.oublier(jumeau_id, x_persona)
    return {"ok": True}


def _sse(donnee):
    return f"data: {json.dumps(donnee, ensure_ascii=False)}\n\n"


@router.post("/jumeaux/{jumeau_id}/conversation")
def converser(jumeau_id: str, message: Message, conn=Depends(connexion),
              x_persona: str = Header(default="architecte", max_length=64)):
    """Réponse du jumeau en flux SSE : morceaux de texte, outils utilisés, fin ou erreur."""
    ctx = _contexte(conn, jumeau_id, x_persona)
    try:
        a = agent.construire(ctx, os.environ["JUMEAU_PG_DSN"])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    if not FILS.prendre(jumeau_id, x_persona):
        raise HTTPException(409, "Une réponse est déjà en cours sur ce fil")

    async def flux():
        outils_vus, apres_outil = set(), False
        try:
            async for ev in a.stream_async(message.texte):
                if "data" in ev:
                    # Le texte qui suit un appel d'outil commence un nouveau paragraphe (comme dans l'historique).
                    yield _sse({"type": "texte", "texte": ("\n\n" if apres_outil else "") + ev["data"]})
                    apres_outil = False
                elif ev.get("type") == "tool_use_stream":
                    usage = ev["current_tool_use"]
                    if usage.get("toolUseId") not in outils_vus:
                        outils_vus.add(usage.get("toolUseId"))
                        apres_outil = True
                        yield _sse({"type": "outil", "nom": usage.get("name")})
            yield _sse({"type": "fin"})
        except Exception:
            journal.exception("conversation %s/%s", jumeau_id, x_persona)
            yield _sse({"type": "erreur", "message": "Le jumeau n'a pas pu répondre."})
        finally:
            FILS.rendre(jumeau_id, x_persona)

    return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
