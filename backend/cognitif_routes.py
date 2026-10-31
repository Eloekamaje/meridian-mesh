"""API des capacités cognitives : Twins typés, boucle mesurée, mémoire, attention, temporalité.

Les routes réutilisent le contexte tenant de la Boucle et restent en lecture/écriture canonique : aucun accès
direct à Mongo, aucun modèle, aucun réseau. Les écritures exigent un acteur (persona) et les Claims exigent une
preuve ; les erreurs de domaine sont traduites en 400/403/404/503.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import auth as auth_identite

import boucle_routes
from jumeau import attention, boucle, calibration, contexte as contexte_module, contrefactuel
from jumeau import entreprise_depot
from jumeau import evaluation_outils, evaluation_profils
from jumeau import consolidation_memoire, memoire_durable, memoire_org, outcomes, portefeuille
from jumeau import raisonnement as raisonnement_module, resolveur_contexte
from jumeau import rls, valeur as valeur_module
from jumeau import specialiste_decouverte, specialiste_impact, specialiste_preuve
from jumeau import specialistes, temporalite, twins_types
from jumeau import composition, graph_store, profils, reponse_cognitive

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


class AnalyseSpecialistes(BaseModel):
    question: str = ""
    situation_id: str | None = None
    twin_ids: list[str] = Field(default_factory=list)
    application_id: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    profondeur: int = 2
    specialistes: list[str] = Field(default_factory=lambda: ["decouverte", "preuve", "impact", "outcome"])


class AnalyseCognitive(AnalyseSpecialistes):
    profil: str | None = None
    autorite_max: str | None = None
    scope: str | None = None
    domaine: str | None = None
    surface: str | None = None
    date: str | None = None


class DemandeComposition(BaseModel):
    profil: str | None = None
    question: str = ""
    application_id: str | None = None
    situation_id: str | None = None
    twin_ids: list[str] = Field(default_factory=list)
    autorite_max: str | None = None


class EvaluationProfilsRequete(BaseModel):
    reponses: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CreationMemoireDurable(BaseModel):
    id: str | None = Field(None, max_length=128)
    scope: str
    scope_id: str = Field(min_length=1, max_length=200)
    classe: str
    contenu: str = Field(min_length=1, max_length=4000)
    provenance: str = Field(min_length=1, max_length=4000)
    consentement: bool = False
    confiance: float = 0.5
    expire_le: str | None = None
    donnees: Any = None


class DemandeContexte(BaseModel):
    surface: str
    twin_id: str | None = None
    situation_id: str | None = None
    work_id: str | None = None
    domaine: str | None = None
    date: str | None = None
    utilisateur: str | None = None
    perimetre: str | None = None


class CreationPrediction(BaseModel):
    id: str | None = Field(None, max_length=128)
    decision_id: str = Field(min_length=1, max_length=200)
    confidence: float
    outcome: bool | None = None


class ResolutionPrediction(BaseModel):
    outcome: bool


class DemandeContrefactuel(BaseModel):
    options: list[dict[str, Any]] = Field(default_factory=list)
    changements: dict[str, Any] = Field(default_factory=dict)
    criteres: list[str] = Field(default_factory=list)


class DemandeConsolidation(BaseModel):
    memoires: list[dict[str, Any]] = Field(default_factory=list)
    seuil_similarite: float = 0.9
    ids: list[str] = Field(default_factory=list)
    acteur: str | None = None


class CreationValeur(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: str
    libelle: str = Field(min_length=1, max_length=240)
    proprietaire: str = Field(min_length=1, max_length=160)
    beneficiaire: str | None = None
    domaine: str | None = None
    objet_source_type: str | None = None
    objet_source_id: str | None = None
    baseline: Any = None
    cible: Any = None
    observe: Any = None
    unite: str | None = None
    devise: str | None = None
    periode: str | None = None
    attribution: str = "inconnue"
    confiance: float = 0.5
    preuves: list[Any] = Field(default_factory=list)
    fraicheur: Any = None
    cout: Any = None
    risque: Any = None
    statut: str = "hypothese"
    date_revue: str | None = None
    donnees: dict[str, Any] = Field(default_factory=dict)


class MiseAJourValeur(BaseModel):
    statut: str | None = None
    observe: Any = None
    baseline: Any = None
    cible: Any = None
    confiance: float | None = None
    preuves: list[Any] | None = None
    fraicheur: Any = None
    cout: Any = None
    risque: Any = None
    date_revue: str | None = None
    attribution: str | None = None
    donnees: dict[str, Any] | None = None


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


_SPECIALISTES = {
    "decouverte": specialiste_decouverte.SpecialisteDecouverte,
    "preuve": specialiste_preuve.SpecialistePreuve,
    "impact": specialiste_impact.SpecialisteImpact,
    "outcome": specialiste_impact.SpecialisteOutcome,
}


async def _lancer_specialistes(noms, base, tenant, dsn):
    async def lancer(nom):
        instance = _SPECIALISTES[nom]()
        graph_context = None
        try:
            if nom in {"impact", "decouverte"}:
                try:
                    graph_context = graph_store.ouvrir()
                except Exception:
                    graph_context = None
            magasin = graph_context["store"] if graph_context is not None else None
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with _contexte(conn, tenant):
                    contexte = replace(base, conn=conn, store=magasin)
                    orchestrateur = specialistes.OrchestrateurSpecialistes([instance], timeout_s=8.0)
                    dossier = await orchestrateur.analyser(contexte)
                    return dossier["specialistes"][0]
        finally:
            if graph_context is not None:
                graph_context["fermer"]()

    return await asyncio.gather(*(lancer(nom) for nom in noms))


def _fusionner_dossiers(dossiers, tenant):
    propositions = {}
    limites = []
    for dossier in dossiers:
        limites.extend(dossier.get("limites") or [])
        for proposition in dossier.get("propositions") or []:
            cle = (proposition["specialiste"], proposition["type"], proposition["titre"])
            precedent = propositions.get(cle)
            if precedent is None or proposition["confiance"] > precedent["confiance"]:
                propositions[cle] = proposition
    ordonnees = sorted(propositions.values(),
                       key=lambda p: (-p["confiance"], p["type"], p["titre"], p["specialiste"]))
    return {
        "tenant": tenant,
        "statut": "ok" if all(d.get("statut") == "ok" for d in dossiers) else "partiel",
        "propositions": boucle_routes._assainir(ordonnees),
        "specialistes": boucle_routes._assainir(dossiers),
        "limites": list(dict.fromkeys(limites)),
    }


@router.post("/specialistes/analyser")
async def analyser_specialistes(
    payload: AnalyseSpecialistes,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Fait travailler les spécialistes en parallèle sur un dossier borné ; aucune écriture canonique."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    noms = payload.specialistes or ["decouverte", "preuve", "impact", "outcome"]
    inconnus = [nom for nom in noms if nom not in _SPECIALISTES]
    if inconnus:
        raise HTTPException(400, f"Spécialiste inconnu : {inconnus[0]}")
    dsn = boucle_routes._dsn()
    base = specialistes.ContexteSpecialiste(
        tenant=tenant, question=payload.question, situation_id=payload.situation_id,
        twin_ids=tuple(payload.twin_ids), application_id=payload.application_id,
        claim_ids=tuple(payload.claim_ids), profondeur=payload.profondeur)
    dossiers = await _lancer_specialistes(noms, base, tenant, dsn)
    return _fusionner_dossiers(dossiers, tenant)


@router.post("/analyser")
async def analyser_cognitif(
    payload: AnalyseCognitive,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Résout le profil, compose les spécialistes et rend une réponse située sur un socle unique."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    # Le profil est une lentille, pas un droit. En demo, le sélecteur est accepté ; hors demo,
    # l'identité authentifiée fait foi et l'autorité de l'agent reste plafonnée à proposition.
    profil_demande = payload.profil if auth_identite.mode() == "demo" else None
    profil = profils.resoudre_profil(
        profil=profil_demande, identite={"role": x_persona},
        question=payload.question, autorite_max="proposition")
    plan = composition.planifier(
        profil, payload.question, autorite_max="proposition",
        application_id=payload.application_id, situation_id=payload.situation_id,
        twin_ids=payload.twin_ids)
    global_scope = (
        payload.scope in {"enterprise", "portfolio"}
        or payload.domaine is not None
        or (not payload.application_id and not payload.twin_ids and not payload.situation_id)
    )
    noms = []
    valeur = None
    if global_scope:
        agregat = await _avec_connexion(tenant, lambda conn: portefeuille.agreger(
            conn, tenant, domaine=payload.domaine, limite=100))
        dossier = {
            "tenant": tenant, "statut": "ok",
            "propositions": agregat["propositions"],
            "specialistes": [{"specialiste": "portefeuille", "statut": "ok",
                              "propositions": agregat["propositions"],
                              "limites": list(agregat["limites"])}],
            "limites": list(agregat["limites"]),
        }
        valeur = agregat["valeur"]
    else:
        noms = list(plan.specialistes_socle)
        dsn = boucle_routes._dsn()
        base = specialistes.ContexteSpecialiste(
            tenant=tenant, question=payload.question, situation_id=payload.situation_id,
            twin_ids=tuple(payload.twin_ids), application_id=payload.application_id,
            claim_ids=tuple(payload.claim_ids), profondeur=payload.profondeur)
        dossiers = await _lancer_specialistes(noms, base, tenant, dsn) if noms else []
        dossier = _fusionner_dossiers(dossiers, tenant) if dossiers else {
            "tenant": tenant, "statut": "partiel", "propositions": [],
            "specialistes": [], "limites": ["aucun spécialiste mobilisé par la composition"],
        }
    reponse = reponse_cognitive.composer(
        payload.question, profil, plan, dossier, autorite_max="proposition")
    contexte_pack = contexte_module.construire(payload.question, profil, dossier)
    trace = raisonnement_module.construire(
        payload.question, profil, plan, contexte_pack, dossier, reponse.as_dict())
    resultat = {
        "tenant": tenant,
        "scope": ("enterprise" if global_scope and not payload.domaine else "portfolio")
        if global_scope else "application",
        "domaine": payload.domaine,
        "profil": boucle_routes._assainir(profil.as_dict()),
        "composition": boucle_routes._assainir(plan.as_dict()),
        "specialistes_executes": list(noms),
        "dossier": boucle_routes._assainir(dossier),
        "reponse": boucle_routes._assainir(reponse.as_dict()),
        "contexte": boucle_routes._assainir(contexte_pack.as_dict()),
        "raisonnement": boucle_routes._assainir(trace.as_dict()),
        "qualite": {
            "faits": len(reponse.socle.faits),
            "preuves": len(reponse.socle.preuves),
            "specialistes_ok": sum(1 for d in dossier["specialistes"] if d.get("statut") == "ok"),
            "limites": len(reponse.socle.limites),
            "autorite": reponse.autorite,
        },
    }
    if valeur is not None:
        resultat["valeur"] = boucle_routes._assainir(valeur)
    return resultat


@router.get("/profils")
async def lister_profils(
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    boucle_routes._tenant(request, x_tenant)
    return {"profils": [profil.as_dict() for profil in profils.CATALOGUE_PROFILS.values()]}


@router.get("/profils/{profil_id}")
async def lire_profil(
    profil_id: str,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    boucle_routes._tenant(request, x_tenant)
    profil = profils.CATALOGUE_PROFILS.get(profil_id)
    if profil is None:
        raise HTTPException(404, "Profil inconnu")
    return {"profil": boucle_routes._assainir(profil.as_dict())}


@router.post("/composition")
async def previsualiser_composition(
    payload: DemandeComposition,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Prévisualise la composition sans exécuter aucun spécialiste."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    # Le profil est une lentille, pas un droit. En demo, le sélecteur est accepté ; hors demo,
    # l'identité authentifiée fait foi et l'autorité de l'agent reste plafonnée à proposition.
    profil_demande = payload.profil if auth_identite.mode() == "demo" else None
    profil = profils.resoudre_profil(
        profil=profil_demande, identite={"role": x_persona},
        question=payload.question, autorite_max="proposition")
    plan = composition.planifier(
        profil, payload.question, autorite_max="proposition",
        application_id=payload.application_id, situation_id=payload.situation_id,
        twin_ids=payload.twin_ids)
    return {"tenant": tenant, "profil": boucle_routes._assainir(profil.as_dict()),
            "composition": boucle_routes._assainir(plan.as_dict())}


@router.get("/evaluation/profils/jeu")
async def jeu_evaluation_profils():
    return {"cas": [cas.as_dict() for cas in evaluation_profils.JEU_PROFILS]}


@router.post("/evaluation/profils")
async def evaluer_profils(payload: EvaluationProfilsRequete):
    """Évalue des réponses déjà produites : vérité, adaptation et sécurité par profil."""
    resultat = evaluation_profils.evaluer_jeu(evaluation_profils.JEU_PROFILS, payload.reponses)
    return boucle_routes._assainir(resultat)


@router.get("/portefeuille")
async def lire_portefeuille(
    request: Request,
    domaine: str | None = Query(None, max_length=120),
    limite: int = Query(50, ge=1, le=500),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Agrège situations, décisions, initiatives, outcomes et learnings à l'échelle portefeuille."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    resultat = await _avec_connexion(tenant, lambda conn: portefeuille.agreger(
        conn, tenant, domaine=domaine, limite=limite))
    return boucle_routes._assainir(resultat)


@router.get("/valeurs/resume")
async def resume_valeurs(
    request: Request,
    domaine: str | None = Query(None, max_length=120),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    resultat = await _avec_connexion(
        tenant, lambda conn: valeur_module.resume(conn, tenant, domaine=domaine))
    return boucle_routes._assainir(resultat)


@router.get("/valeurs")
async def lister_valeurs(
    request: Request,
    statut: str | None = Query(None, max_length=32),
    domaine: str | None = Query(None, max_length=120),
    type_: str | None = Query(None, alias="type", max_length=40),
    proprietaire: str | None = Query(None, max_length=160),
    limite: int = Query(200, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    valeurs = await _avec_connexion(tenant, lambda conn: valeur_module.lister(
        conn, tenant, statut=statut, domaine=domaine, type_=type_,
        proprietaire=proprietaire, limite=limite))
    return {"tenant": tenant, "valeurs": boucle_routes._assainir(valeurs)}


@router.get("/valeurs/{valeur_id}")
async def lire_valeur(
    valeur_id: str,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    valeur = await _avec_connexion(
        tenant, lambda conn: valeur_module.lire(conn, tenant, valeur_id))
    if valeur is None:
        raise HTTPException(404, "Valeur introuvable")
    return {"tenant": tenant, "valeur": boucle_routes._assainir(valeur)}


@router.post("/valeurs", status_code=201)
async def creer_valeur(
    payload: CreationValeur,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    donnees = payload.model_dump()
    donnees["tenant_id"] = tenant
    valeur = await _avec_connexion(
        tenant, lambda conn: valeur_module.creer(conn, tenant, donnees))
    return {"tenant": tenant, "valeur": boucle_routes._assainir(valeur)}


@router.patch("/valeurs/{valeur_id}")
async def maj_valeur(
    valeur_id: str,
    payload: MiseAJourValeur,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    changements = {cle: v for cle, v in payload.model_dump().items() if v is not None}
    valeur = await _avec_connexion(
        tenant, lambda conn: valeur_module.mettre_a_jour(conn, tenant, valeur_id, changements))
    return {"tenant": tenant, "valeur": boucle_routes._assainir(valeur)}


@router.post("/contexte/resoudre")
async def resoudre_contexte(
    payload: DemandeContexte,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Résout explicitement une surface et ses entités, sans laisser le modèle deviner un id."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    try:
        resultat = resolveur_contexte.resoudre(
            tenant, payload.surface, twin_id=payload.twin_id,
            situation_id=payload.situation_id, work_id=payload.work_id,
            domaine=payload.domaine, date=payload.date,
            utilisateur=x_persona, perimetre=payload.perimetre)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"tenant": tenant, "contexte": boucle_routes._assainir(resultat.as_dict())}


@router.get("/memoire/durable")
async def lister_memoire_durable(
    request: Request,
    scope: str | None = Query(None, max_length=32),
    scope_id: str | None = Query(None, max_length=200),
    classe: str | None = Query(None, max_length=32),
    q: str | None = Query(None, max_length=500),
    limite: int = Query(200, ge=1, le=1000),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    if q:
        valeurs = await _avec_connexion(tenant, lambda conn: memoire_durable.chercher(
            conn, tenant, q, scope=scope, scope_id=scope_id, limite=limite))
    else:
        valeurs = await _avec_connexion(tenant, lambda conn: memoire_durable.lister(
            conn, tenant, scope=scope, scope_id=scope_id, classe=classe, limite=limite))
    return {"tenant": tenant, "memoires": boucle_routes._assainir(valeurs)}


@router.get("/memoire/durable/export")
async def exporter_memoire_durable(
    request: Request,
    scope: str | None = Query(None, max_length=32),
    scope_id: str | None = Query(None, max_length=200),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    valeurs = await _avec_connexion(tenant, lambda conn: memoire_durable.exporter(
        conn, tenant, scope=scope, scope_id=scope_id))
    return {"tenant": tenant, "memoires": boucle_routes._assainir(valeurs)}


@router.post("/memoire/durable/purge")
async def purger_memoire_durable(
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    supprimees = await _avec_connexion(tenant, lambda conn: memoire_durable.purger(conn, tenant))
    return {"tenant": tenant, "supprimees": supprimees}


@router.post("/memoire/durable", status_code=201)
async def creer_memoire_durable(
    payload: CreationMemoireDurable,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    memoire = await _avec_connexion(tenant, lambda conn: memoire_durable.creer(
        conn, tenant, id=payload.id, scope=payload.scope, scope_id=payload.scope_id,
        classe=payload.classe, contenu=payload.contenu, provenance=payload.provenance,
        consentement=payload.consentement, confiance=payload.confiance,
        expire_le=payload.expire_le, donnees=payload.donnees))
    return {"tenant": tenant, "memoire": boucle_routes._assainir(memoire)}


@router.get("/memoire/durable/{memoire_id}")
async def lire_memoire_durable(
    memoire_id: str,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    memoire = await _avec_connexion(
        tenant, lambda conn: memoire_durable.lire(conn, tenant, memoire_id))
    if memoire is None:
        raise HTTPException(404, "Mémoire introuvable")
    return {"tenant": tenant, "memoire": boucle_routes._assainir(memoire)}


@router.delete("/memoire/durable/{memoire_id}", status_code=204)
async def supprimer_memoire_durable(
    memoire_id: str,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    supprimee = await _avec_connexion(
        tenant, lambda conn: memoire_durable.supprimer(conn, tenant, memoire_id))
    if not supprimee:
        raise HTTPException(404, "Mémoire introuvable")
    return Response(status_code=204)


@router.post("/calibration/predictions", status_code=201)
async def enregistrer_prediction(
    payload: CreationPrediction,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    prediction = await _avec_connexion(tenant, lambda conn: calibration.enregistrer(
        conn, tenant, id=payload.id, decision_id=payload.decision_id,
        confidence=payload.confidence, outcome=payload.outcome))
    return {"tenant": tenant, "prediction": boucle_routes._assainir(prediction.as_dict())}


@router.post("/calibration/predictions/{prediction_id}/outcome")
async def resoudre_prediction(
    prediction_id: str,
    payload: ResolutionPrediction,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    try:
        prediction = await _avec_connexion(tenant, lambda conn: calibration.resoudre(
            conn, tenant, prediction_id, payload.outcome))
    except LookupError as exc:
        raise HTTPException(404, "Prédiction introuvable") from exc
    return {"tenant": tenant, "prediction": boucle_routes._assainir(prediction.as_dict())}


@router.get("/calibration/rapport")
async def rapport_calibration(
    request: Request,
    decision_id: str | None = Query(None, max_length=200),
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    resultat = await _avec_connexion(tenant, lambda conn: calibration.rapport(
        conn, tenant, decision_id=decision_id))
    return boucle_routes._assainir(resultat)


@router.post("/contrefactuel")
async def comparer_contrefactuel(payload: DemandeContrefactuel):
    try:
        resultat = contrefactuel.comparer(
            payload.options, payload.changements, criteres=payload.criteres)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return boucle_routes._assainir(resultat)


@router.post("/memoire/consolidation")
async def proposer_consolidation(
    payload: DemandeConsolidation,
    request: Request,
    x_persona: str = Header("architecte", max_length=64),
    x_espace: str | None = Header(None, max_length=64),
    x_tenant: str | None = Header(None, alias="X-Tenant"),
):
    """Propose doublons et conflits ; n'écrit jamais sans approbation humaine explicite."""
    boucle_routes._verifier_contexte(x_persona, x_espace)
    tenant = boucle_routes._tenant(request, x_tenant)
    try:
        proposition = consolidation_memoire.proposer(
            payload.memoires, tenant_id=tenant, seuil_similarite=payload.seuil_similarite)
        plan = None
        if payload.ids:
            if not payload.acteur:
                raise ValueError("acteur obligatoire pour approuver une consolidation")
            plan = consolidation_memoire.approuver(
                proposition, acteur=payload.acteur, ids=payload.ids)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    resultat = {"tenant": tenant, "proposition": proposition.as_dict(), "ecritures": False}
    if plan is not None:
        resultat["plan"] = plan
    return boucle_routes._assainir(resultat)
