"""API du jumeau réel (phase 0) : Claims prouvés, extraits vérifiés, revue humaine.

ponytail: l'acteur vient de l'en-tête X-Persona de la démo ; OIDC + Cedar en phase 1 (Architecture Jumeau §4.2).
"""
import os
from typing import Literal, Optional

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from jumeau import connaissance, depot, flore, gardien
from jumeau.source_git import lire_au_sha
from jumeau.source_git import extrait

router = APIRouter(prefix="/v2", tags=["jumeau"])


def connexion():
    dsn = os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


class Revue(BaseModel):
    decision: Literal["ACCEPTED", "CONTESTED"]
    motif: Optional[str] = Field(default=None, max_length=2000)


class Tranche(BaseModel):
    verdict: Literal["a", "b", "aucune"]
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


@router.post("/contradictions/{contradiction_id}/revue")
def trancher(contradiction_id: int, decision: Tranche, conn=Depends(connexion),
             x_persona: str = Header(default="architecte", max_length=64)):
    c = depot.contradiction_par_id(conn, contradiction_id)
    try:
        if not c:
            raise LookupError(contradiction_id)
        depot.trancher_contradiction(conn, c["jumeau_id"], contradiction_id, x_persona, decision.verdict, decision.motif)
    except LookupError:
        raise HTTPException(404, "Contradiction introuvable ou déjà tranchée")
    return {"ok": True}


def _extrait_citation(conn, jumeau_id, locator, systeme, contexte=3):
    """Lignes du code citées (et leur contexte) ; pour une autre source, locator et système seulement."""
    base = {"systeme": systeme, "locator": locator, "lignes": None}
    m = connaissance.RE_CITATION.fullmatch(locator) if systeme == "git" else None
    if not m:
        return base
    depot_nom, chemin, debut, fin = connaissance.decouper(m)
    try:
        source = connaissance.resoudre_source(depot.sources_du_jumeau(conn, jumeau_id), depot_nom, chemin)
        lignes = lire_au_sha(source.get("copie") or source["emplacement"], source["curseur"])(chemin)
    except (LookupError, ValueError):
        return base
    if lignes is None:
        return base
    de, a = max(1, debut - contexte), min(len(lignes), fin + contexte)
    return {**base, "lignes": [{"n": n, "texte": lignes[n - 1], "citee": debut <= n <= fin} for n in range(de, a + 1)]}


@router.get("/contradictions/{contradiction_id}/extraits")
def lire_extraits_contradiction(contradiction_id: int, conn=Depends(connexion)):
    c = depot.contradiction_par_id(conn, contradiction_id)
    if not c:
        raise HTTPException(404, "Contradiction introuvable")
    return [_extrait_citation(conn, c["jumeau_id"], c[f"preuve_{x}"], c[f"systeme_{x}"]) for x in "ab"]


@router.get("/jumeaux/{jumeau_id}/fiche")
def lire_fiche(jumeau_id: str, conn=Depends(connexion)):
    """Fiche vivante rédigée par le gardien : ce que le jumeau dit de l'application."""
    fiche, sources = gardien.fiche_courante(conn, jumeau_id), depot.sources_du_jumeau(conn, jumeau_id)
    if not fiche or not sources:
        raise HTTPException(404, "Pas encore de fiche vivante pour ce jumeau")
    return flore.fiche_affichable(fiche, sources)
