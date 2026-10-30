"""API des capacités cognitives : Twins typés, boucle mesurée, mémoire, attention, temporalité.

Les routes réutilisent le contexte tenant de la Boucle et restent en lecture/écriture canonique : aucun accès
direct à Mongo, aucun modèle, aucun réseau. Les écritures exigent un acteur (persona) et les Claims exigent une
preuve ; les erreurs de domaine sont traduites en 400/403/404/503.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

import boucle_routes
from jumeau import attention, boucle, entreprise_depot, evaluation_outils, memoire_org, outcomes, rls
from jumeau import temporalite, twins_types

router = APIRouter(prefix="/boucle", tags=["cognitif"])


class CreationTwin(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=32)
    nom: str = Field(min_length=1, max_length=200)
    mission: str | None = Field(None, max_length=2000)
    domaine: str | None = Field(None, max_length=128)
    equipe: str = Field("à confirmer", max_length=200)
    preuve: dict[str, Any] | None = None


class CreationClaim(BaseModel):
    predicat: str = Field(min_length=1, max_length=80)
    objet: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=300)
    preuve: dict[str, Any]
    mode: str = "DECLARED"
    confiance: float = 0.5
    texte: str | None = Field(None, max_length=2000)


class CreationOutcome(BaseModel):
    initiative_id: str
    mesure: Any
    cible: Any = None
    periode: str | None = Field(None, max_length=120)
    preuve_ids: list[str] = Field(default_factory=list)
    decision_id: str | None = None
    situation_ids: list[str] = Field(default_factory=list)
    twin_ids: list[str] = Field(default_factory=list)
    enseignement: str = Field(min_length=1, max_length=4000)
    conditions_reutilisation: list[str] = Field(default_factory=list)


class ReutilisationLearning(BaseModel):
    situation_id: str


class CreationMemoire(BaseModel):
    contenu: str = Field(min_length=1, max_length=8000)
    genre: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=300)
    twin_ids: list[str] = Field(default_factory=list)
    situation_ids: list[str] = Field(default_factory=list)
    confiance: float | None = None


class EvaluationSelections(BaseModel):
    selections: dict[str, list[str]] = Field(default_factory=dict)


def _contexte(conn, tenant):
    return rls.contexte_tenant(conn, tenant) if rls.est_actif() else nullcontext()


def _ids(valeur: str | None) -> list[str]:
    if not valeur:
        return []
    return [element.strip() for element in valeur.split(",") if element.strip()]


def _erreur(exc: Exception) -> HTTPException:
    if isinstance(exc, (PermissionError, twins_types.TwinTenantRefuse)):
        return HTTPException(403, str(exc))
    if isinstance(exc, (LookupError, twins_types.TwinIntrouvable, outcomes.LearningIntrouvable)):
        return HTTPException(404, str(exc))
    if isinstance(exc, psycopg.Error):
        return HTTPException(503, "Couche cognitive indisponible")
    if isinstance(exc, (ValueError, boucle.BoucleInvalide, memoire_org.MemoireInvalide)):
        return HTTPException(400, str(exc))
    return HTTPException(500, "Erreur cognitive interne")


async def _appeler(action):
    try:
        return await asyncio.to_thread(action)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - traduction contrôlée en statut HTTP
        raise _erreur(exc) from exc


async def _avec_connexion(tenant, action):
    dsn = boucle_routes._dsn()

    def executer():
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with _contexte(conn, tenant):
                return action(conn)

    return await _appeler(executer)


@router.get("/twins")
async def lister_twins(
    request: Request,
    type_: str | None = Query(None, alias="type", max_length=32),
    limite: int = Query(200, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    twins = await _avec_connexion(tenant, lambda conn: twins_types.lister_twins(conn, tenant, type_, limite))
    return {"tenant": tenant, "twins": boucle_routes._assainir(twins)}


@router.post("/twins", status_code=201)
async def creer_twin(
    payload: CreationTwin,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    twin = await _avec_connexion(tenant, lambda conn: twins_types.creer_twin(
        conn, tenant, payload.id, payload.type, payload.nom, mission=payload.mission,
        domaine=payload.domaine, equipe=payload.equipe, acteur=x_persona, preuve=payload.preuve))
    return {"tenant": tenant, "twin": boucle_routes._assainir(twin)}


@router.get("/twins/{twin_id}")
async def lire_twin(
    twin_id: str,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    twin = await _avec_connexion(tenant, lambda conn: twins_types.lire_twin(conn, tenant, twin_id))
    if twin is None:
        raise HTTPException(404, "Twin introuvable")
    return {"tenant": tenant, "twin": boucle_routes._assainir(twin)}


@router.post("/twins/{twin_id}/claims", status_code=201)
async def creer_claim(
    twin_id: str,
    payload: CreationClaim,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    claim = await _avec_connexion(tenant, lambda conn: twins_types.creer_claim(
        conn, tenant, twin_id, payload.predicat, payload.objet, source=payload.source,
        preuve=payload.preuve, mode=payload.mode, confiance=payload.confiance,
        acteur=x_persona, texte=payload.texte))
    return {"tenant": tenant, "claim": boucle_routes._assainir(claim)}


@router.get("/twins/{twin_id}/claims")
async def claims_twin(
    twin_id: str,
    request: Request,
    limite: int = Query(100, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    claims = await _avec_connexion(
        tenant, lambda conn: twins_types.claims_du_twin(conn, tenant, twin_id, limite))
    return {"tenant": tenant, "claims": boucle_routes._assainir(claims)}


@router.post("/outcomes", status_code=201)
async def creer_outcome(
    payload: CreationOutcome,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    resultat = await _avec_connexion(tenant, lambda conn: outcomes.mesurer_et_capitaliser(
        conn, tenant, payload.initiative_id, payload.mesure, cible=payload.cible,
        periode=payload.periode, preuve_ids=payload.preuve_ids, decision_id=payload.decision_id,
        situation_ids=payload.situation_ids, twin_ids=payload.twin_ids,
        enseignement=payload.enseignement, conditions_reutilisation=payload.conditions_reutilisation,
        acteur=x_persona))
    return {"tenant": tenant, "outcome": boucle_routes._assainir(resultat["outcome"]),
            "learning": boucle_routes._assainir(resultat["learning"])}


@router.get("/learnings")
async def lister_learnings(
    request: Request,
    situation_id: str | None = Query(None, max_length=128),
    twin_ids: str | None = Query(None, max_length=1000),
    limite: int = Query(20, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    learnings = await _avec_connexion(tenant, lambda conn: outcomes.learnings_pour(
        conn, tenant, situation_id=situation_id, twin_ids=_ids(twin_ids), limite=limite))
    return {"tenant": tenant, "learnings": boucle_routes._assainir(learnings)}


@router.post("/learnings/{learning_id}/reutilisations", status_code=201)
async def reutiliser_learning(
    learning_id: str,
    payload: ReutilisationLearning,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    learning = await _avec_connexion(tenant, lambda conn: outcomes.marquer_reutilise(
        conn, tenant, learning_id, payload.situation_id, x_persona))
    return {"tenant": tenant, "learning": boucle_routes._assainir(learning)}


@router.post("/memoire", status_code=201)
async def memoriser(
    payload: CreationMemoire,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    memoire = await _avec_connexion(tenant, lambda conn: memoire_org.memoriser(
        conn, tenant, payload.contenu, genre=payload.genre, source=payload.source,
        twin_ids=payload.twin_ids, situation_ids=payload.situation_ids,
        confiance=payload.confiance))
    return {"tenant": tenant, "memoire": boucle_routes._assainir(memoire)}


@router.get("/memoire")
async def chercher_memoire(
    request: Request,
    q: str = Query(..., min_length=1, max_length=500),
    twin_ids: str | None = Query(None, max_length=1000),
    limite: int = Query(20, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    memoires = await _avec_connexion(tenant, lambda conn: memoire_org.chercher(
        conn, tenant, q, twin_ids=_ids(twin_ids), limite=limite))
    return {"tenant": tenant, "memoires": boucle_routes._assainir(memoires)}


@router.get("/attention")
async def attention_du_jour(
    request: Request,
    type_: str = Query("SITUATION", alias="type", max_length=64),
    limite: int = Query(50, ge=1, le=500),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    objets = await _avec_connexion(tenant, lambda conn: entreprise_depot.lister_objets(
        conn, tenant, type_=type_, limite=1000))
    classes = attention.classer(objets, limite=limite)
    for item in classes:
        item.pop("objet", None)
    return {"tenant": tenant, "objets": boucle_routes._assainir(classes),
            "resume": attention.resume_attention(objets)}


@router.get("/topologie")
async def topologie_a_date(
    request: Request,
    date: str = Query(..., min_length=1, max_length=80),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    resultat, mode = await asyncio.to_thread(
        boucle_routes._executer_graphe,
        lambda store: temporalite.topologie_a_date(store, tenant, date))
    return {"tenant": tenant, "mode": mode, "topologie": boucle_routes._assainir(resultat)}


@router.get("/evaluation/jeu")
async def evaluation_jeu():
    """Le jeu d'or cognitif déclaratif ; l'évaluation réelle reste un appel explicite."""
    return {"cas": [cas.as_dict() for cas in evaluation_outils.JEU_COGNITIF]}


@router.post("/evaluation")
async def evaluation(payload: EvaluationSelections):
    """Évalue des sélections d'outils déjà produites, sans appeler de modèle."""
    def selectionneur(cas):
        return payload.selections.get(cas.id, [])
    resultat = evaluation_outils.evaluer(evaluation_outils.JEU_COGNITIF, selectionneur)
    return {"resultat": resultat, "seuils": evaluation_outils.seuils(
        evaluation_outils.JEU_COGNITIF, resultat, minimum=0.8)}
