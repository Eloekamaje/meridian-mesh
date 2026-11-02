"""API du pilotage capacité / charge / prévision / budget.

Les routes sont génériques : le fournisseur est un attribut de source, jamais une route ni un modèle.
Les permissions sont vérifiées avant les agrégations.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Optional

import psycopg
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from meridian.adapters.outbound.postgres import planification as depot
from meridian.adapters.outbound.postgres import rls
from meridian.application import tenant_context
from meridian.adapters.outbound.connectors import auth_source
from meridian.adapters.outbound.travail import source_finance, source_incidents, source_people, source_travail
from meridian.application.planification import alertes, budget, capacite, previsions, roles, scenario, sync
from meridian.domain import artefacts as domain_artefacts
from meridian.domain import planification as domaine
from meridian.adapters.outbound.diagram_export import export_svg_document

_SCHEMA_PRET = False
_VERROU_SCHEMA = threading.Lock()


def _dsn() -> str:
    valeur = os.environ.get("JUMEAU_PG_DSN") or os.environ.get("JUMEAU_WORKER_PG_DSN")
    if not valeur:
        raise HTTPException(503, "Postgres non configuré pour la planification")
    return valeur


@contextmanager
def _connexion(tenant: str | None = None):
    global _SCHEMA_PRET
    with psycopg.connect(_dsn(), autocommit=True, connect_timeout=5) as conn:
        if not _SCHEMA_PRET:
            with _VERROU_SCHEMA:
                if not _SCHEMA_PRET:
                    depot.appliquer_schema(conn)
                    _SCHEMA_PRET = True
        if tenant and rls.est_actif():
            with rls.contexte_tenant(conn, tenant):
                yield conn
        else:
            yield conn


def _tenant(request: Request) -> str:
    return (getattr(request.state, "tenant", None)
            or request.headers.get("X-Tenant")
            or tenant_context.courant_explicite()
            or os.environ.get("JUMEAU_TENANT") or "local")


def _acteur(request: Request) -> str:
    return (getattr(request.state, "acteur", None)
            or getattr(request.state, "utilisateur", None) or "demo")


def _role(conn, request: Request, action: str) -> str:
    role = roles.role_effectif(depot, conn, _tenant(request), _acteur(request))
    # En demo locale uniquement, l'acteur demo est administrateur pour permettre le bootstrap.
    # En proxy/OIDC, aucun rôle explicite ne donne jamais l'administration.
    if role == "observateur" and os.environ.get("AUTH_MODE", "demo").lower() == "demo":
        role = "admin"
    try:
        roles.exiger(role, action)
    except roles.AccesRefuse as erreur:
        raise HTTPException(403, str(erreur)) from erreur
    return role


def _secret_webhook(source: dict) -> str:
    reference = (source.get("configuration") or {}).get("webhook_secret_ref")
    if not reference:
        raise HTTPException(503, "webhook non configuré pour cette source")
    try:
        secret = auth_source.PATSource(reference).token()
    except Exception as erreur:  # noqa: BLE001
        raise HTTPException(503, "secret de webhook indisponible") from erreur
    if not secret:
        raise HTTPException(503, "secret de webhook indisponible")
    return secret


def _signature(corps: bytes, secret: str, entetes, provider: str) -> bool:
    fournisseur = str(provider or "").lower()
    if fournisseur == "jira":
        fourni = entetes.get("x-hub-signature") or entetes.get("x-hub-signature-256") or ""
        if not fourni.startswith("sha256="):
            return False
        attendu = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
        return hmac.compare_digest(fourni[7:], attendu)
    if fournisseur in {"linear"}:
        fourni = entetes.get("linear-signature") or ""
        attendu = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
        return hmac.compare_digest(fourni, attendu)
    if fournisseur in {"github", "gitlab"}:
        fourni = entetes.get("x-hub-signature-256") or ""
        if not fourni.startswith("sha256="):
            return False
        attendu = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
        return hmac.compare_digest(fourni[7:], attendu)
    # Azure DevOps et webhooks génériques : secret partagé dans un en-tête dédié.
    return hmac.compare_digest(entetes.get("x-planification-secret") or "", secret)


def _identifiant_webhook(entetes, corps: bytes) -> str:
    for nom in ("x-atlassian-webhook-identifier", "x-github-delivery", "linear-delivery",
                "x-planification-delivery"):
        if entetes.get(nom):
            return str(entetes[nom])
    return hashlib.sha256(corps).hexdigest()


def _equipes_visibles(conn, request: Request, role: str) -> set[str] | None:
    """None = tenant/portefeuille ; un ensemble = périmètre équipe explicite."""
    if role in {"admin", "pmo", "sponsor", "audit"}:
        return None
    affectations = depot.roles(conn, _tenant(request), _acteur(request))
    if any(a.get("perimetre_type") in {"tenant", "programme", "portefeuille"} for a in affectations):
        return None
    return {str(a["perimetre_id"]) for a in affectations
            if a.get("perimetre_type") == "equipe" and a.get("perimetre_id")}


def _source_publique(source: dict) -> dict:
    return {
        "id": source.get("id"), "provider": source.get("provider"), "usage": source.get("usage"),
        "prioritaire": source.get("prioritaire", False), "nom": source.get("nom"), "perimetre": source.get("perimetre"),
        "capacites": source.get("capacites") or {}, "etat": source.get("etat"),
        "curseur": source.get("curseur"), "derniere_erreur": source.get("derniere_erreur"),
        "a_secret": bool(source.get("secret_ref")), "maj_le": source.get("maj_le"),
    }


class SourceCreate(BaseModel):
    id: Optional[str] = None
    provider: str = "csv"
    usage: str = "travail"
    prioritaire: bool = False
    nom: str
    perimetre: Optional[str] = None
    secret_ref: Optional[str] = None
    configuration: dict = Field(default_factory=dict)


class PrevisionDemande(BaseModel):
    equipe_id: Optional[str] = None
    date_depart: Optional[date] = None
    seed: int = 42
    simulations: int = 2000
    restant_items: Optional[int] = None
    restant_points: Optional[float] = None
    historique_debit: list[float] = Field(default_factory=list)
    historique_velocite: list[float] = Field(default_factory=list)
    historique_cycle: list[float] = Field(default_factory=list)
    duree_cycle_jours: float = 10.0
    delai_fixe_jours: float = 0.0


class ScenarioDemande(BaseModel):
    base: dict = Field(default_factory=dict)
    scenarios: list[dict] = Field(default_factory=list)
    date_depart: Optional[date] = None


class CalibrationCreate(BaseModel):
    date_reelle: date


class DiagrammeCompile(BaseModel):
    html: str
    titre: str = "Diagramme"


class RoleCreate(BaseModel):
    acteur: str
    role: str
    perimetre_type: str = "tenant"
    perimetre_id: Optional[str] = None
    debut: Optional[date] = None
    fin: Optional[date] = None


class PlanCreate(BaseModel):
    id: Optional[str] = None
    nom: str
    equipe_id: Optional[str] = None
    horizon: Optional[str] = None
    statut: str = "brouillon"
    auteur: Optional[str] = None
    hypotheses: list = Field(default_factory=list)
    lignes: list[dict] = Field(default_factory=list)


class BudgetCreate(BaseModel):
    id: Optional[str] = None
    initiative_id: Optional[str] = None
    objet_source_type: Optional[str] = None
    objet_source_id: Optional[str] = None
    libelle: str
    devise: str = "EUR"
    enveloppe: float = 0
    periode: Optional[str] = None
    source: Optional[str] = None


def _sync_en_thread(dsn: str, tenant: str, source_id: str) -> dict:
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        if rls.est_actif():
            with rls.contexte_tenant(conn, tenant):
                return _sync_avec(conn, tenant, source_id)
        return _sync_avec(conn, tenant, source_id)


def _sync_avec(conn, tenant: str, source_id: str) -> dict:
    source = depot.lire_source(conn, tenant, source_id)
    if source is None:
        raise ValueError("source introuvable")
    usage = source.get("usage") or "travail"
    adapter = {"travail": source_travail, "people": source_people,
               "finance": source_finance, "incidents": source_incidents}.get(usage)
    if adapter is None:
        raise ValueError(f"usage de source inconnu : {usage!r}")
    return sync.synchroniser(depot, conn, source, adapter(source))


def construire_router() -> APIRouter:
    router = APIRouter(prefix="/planification", tags=["planification"])

    @router.get("/equipes")
    async def lister_equipes(request: Request):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_equipe")
            visibles = _equipes_visibles(conn, request, role)
            equipes = depot.equipes(conn, _tenant(request))
            if visibles is not None:
                equipes = [e for e in equipes if e["id"] in visibles]
            return {"equipes": equipes}

    @router.get("/equipes/{equipe_id}")
    async def detail_equipe(equipe_id: str, request: Request):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_equipe")
            visibles = _equipes_visibles(conn, request, role)
            equipes = {e["id"]: e for e in depot.equipes(conn, _tenant(request))}
            if equipe_id not in equipes or (visibles is not None and equipe_id not in visibles):
                raise HTTPException(404, "équipe introuvable")
            membres = depot.membres(conn, _tenant(request), equipe_id)
            if role in {"observateur", "membre"}:
                membres = [m for m in membres if m.get("acteur") == _acteur(request)]
            return {"equipe": equipes[equipe_id], "membres": membres,
                    "competences": depot.competences(conn, _tenant(request), equipe_id)}

    @router.get("/capacite")
    async def lire_capacite(request: Request, equipe_id: Optional[str] = None,
                            debut: Optional[date] = None, fin: Optional[date] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_charge")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            return capacite.resume(depot, conn, _tenant(request), equipe_id=equipe_id,
                                   equipe_ids=visibles, debut=debut, fin=fin)

    @router.get("/previsions")
    async def lister_previsions(request: Request, equipe_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_prevision")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            previsions = depot.previsions(conn, _tenant(request), equipe_id)
            if visibles is not None:
                previsions = [p for p in previsions if p.get("equipe_id") in visibles]
            return {"previsions": previsions}

    @router.post("/previsions")
    async def calculer_prevision(payload: PrevisionDemande, request: Request):
        tenant = _tenant(request)
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_prevision")
            visibles = _equipes_visibles(conn, request, role)
            if payload.equipe_id and visibles is not None and payload.equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            if payload.equipe_id:
                return previsions.prevoir_equipe(
                    depot, conn, tenant, payload.equipe_id,
                    date_depart=payload.date_depart, seed=payload.seed,
                    simulations=payload.simulations)
            if not any((payload.restant_items, payload.restant_points,
                        payload.historique_debit, payload.historique_velocite,
                        payload.historique_cycle)):
                raise HTTPException(400, "périmètre restant ou historique requis")
            resultat = previsions.prevoir_explicite(payload.model_dump(), date_depart=payload.date_depart)
            if payload.date_depart:
                resultat["date_depart"] = payload.date_depart.isoformat()
            return resultat

    @router.get("/artefacts")
    async def lister_artefacts(request: Request, type: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_charge")
            return {"artefacts": depot.artefacts(conn, _tenant(request), type)}

    @router.get("/artefacts/{artefact_id}")
    async def lire_artefact(artefact_id: str, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_charge")
            resultat = depot.artefact(conn, _tenant(request), artefact_id)
            if resultat is None:
                raise HTTPException(404, "artefact introuvable")
            return resultat

    @router.post("/artefacts", status_code=201)
    async def enregistrer_artefact(payload: dict, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "proposer_plan")
            try:
                return depot.enregistrer_artefact(conn, _tenant(request), payload)
            except ValueError as erreur:
                raise HTTPException(400, str(erreur)) from erreur

    @router.post("/artefacts/compiler", status_code=201)
    async def compiler_diagramme(payload: DiagrammeCompile, request: Request):
        if len(payload.html) > 2_000_000:
            raise HTTPException(413, "diagramme trop volumineux")
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "proposer_plan")
            try:
                svg = export_svg_document(payload.html, Path(f"{payload.titre}.html"),
                                          system_fonts=True)
                artefact = domain_artefacts.envelopper(
                    "svg", payload.titre, {"svg": svg}, source="design-diagram")
                return depot.enregistrer_artefact(conn, _tenant(request), artefact)
            except ValueError as erreur:
                raise HTTPException(400, str(erreur)) from erreur

    @router.get("/temps")
    async def lister_temps(request: Request, equipe_id: Optional[str] = None,
                           debut: Optional[date] = None, fin: Optional[date] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_charge")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            lignes = depot.temps(conn, _tenant(request), equipe_id, debut, fin)
            if visibles is not None:
                lignes = [l for l in lignes if l.get("equipe_id") in visibles]
            agrege = {}
            for ligne in lignes:
                cle = (ligne.get("equipe_id"), ligne.get("unite") or "heures",
                       ligne.get("periode") or str(ligne.get("date_travail") or "")[:7])
                agrege[cle] = agrege.get(cle, 0.0) + float(ligne.get("valeur") or 0)
            return {"temps": [{"equipe_id": e, "unite": u, "periode": p, "valeur": v}
                              for (e, u, p), v in sorted(agrege.items())]}

    @router.get("/allocations")
    async def lister_allocations(request: Request, equipe_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_charge")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            lignes = depot.allocations(conn, _tenant(request), equipe_id)
            if visibles is not None:
                lignes = [l for l in lignes if l.get("equipe_id") in visibles]
            if role in {"observateur", "membre"}:
                lignes = [l for l in lignes if not l.get("acteur") or l.get("acteur") == _acteur(request)]
            return {"allocations": lignes}

    @router.get("/absences")
    async def lister_absences(request: Request, equipe_id: Optional[str] = None,
                              debut: Optional[date] = None, fin: Optional[date] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_charge")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            lignes = depot.absences(conn, _tenant(request), equipe_id, debut, fin)
            if visibles is not None:
                lignes = [l for l in lignes if l.get("equipe_id") in visibles]
            # Agrégat : jamais le nom d'une personne absent·e.
            agrege = {}
            for ligne in lignes:
                cle = (ligne.get("equipe_id"), ligne.get("unite") or "jours")
                agrege[cle] = agrege.get(cle, 0.0) + float(ligne.get("valeur") or 0)
            return {"absences": [{"equipe_id": e, "unite": u, "valeur": v}
                                 for (e, u), v in sorted(agrege.items())]}

    @router.get("/taux")
    async def lister_taux(request: Request, equipe_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_budget")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            lignes = depot.taux(conn, _tenant(request), equipe_id)
            if visibles is not None:
                lignes = [l for l in lignes if l.get("equipe_id") in visibles]
            return {"taux": lignes}

    @router.get("/plans")
    async def lister_plans(request: Request, equipe_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_charge")
            visibles = _equipes_visibles(conn, request, role)
            if equipe_id and visibles is not None and equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            plans = depot.plans(conn, _tenant(request), equipe_id)
            if visibles is not None:
                plans = [p for p in plans if p.get("equipe_id") in visibles]
            return {"plans": plans}

    @router.post("/plans", status_code=201)
    async def creer_plan(payload: PlanCreate, request: Request):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "proposer_plan")
            visibles = _equipes_visibles(conn, request, role)
            if payload.equipe_id and visibles is not None and payload.equipe_id not in visibles:
                raise HTTPException(403, "équipe hors de votre périmètre")
            identifiant = depot.enregistrer_plan(conn, _tenant(request), payload.model_dump(),
                                                 payload.lignes)
            return {"id": identifiant}

    @router.get("/plans/{plan_id}")
    async def lire_plan(plan_id: str, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_charge")
            resultat = depot.plan(conn, _tenant(request), plan_id)
            if resultat is None:
                raise HTTPException(404, "plan introuvable")
            return resultat

    @router.get("/dependances")
    async def lister_dependances(request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_charge")
            return {"dependances": depot.dependances(conn, _tenant(request))}

    @router.get("/alertes")
    async def lister_alertes(request: Request):
        with _connexion(_tenant(request)) as conn:
            role = _role(conn, request, "lire_resume")
            visibles = _equipes_visibles(conn, request, role)
            return {"alertes": alertes.lister(depot, conn, _tenant(request), equipe_ids=visibles)}

    @router.post("/scenarios")
    async def simuler_scenarios(payload: ScenarioDemande, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "simuler")
            if not payload.base or not payload.scenarios:
                raise HTTPException(400, "base et scénarios requis")
            return scenario.comparer(payload.base, payload.scenarios,
                                     date_depart=payload.date_depart)

    @router.get("/valeurs")
    async def lister_valeurs(request: Request, initiative_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_budget")
            return {"valeurs": depot.valeurs(conn, _tenant(request), initiative_id)}

    @router.post("/previsions/{prevision_id}/calibrer")
    async def calibrer_prevision(prevision_id: str, payload: CalibrationCreate, request: Request):
        tenant = _tenant(request)
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "proposer_plan")
            prevision = depot.prevision(conn, tenant, prevision_id)
            if prevision is None:
                raise HTTPException(404, "prévision introuvable")
            return depot.enregistrer_calibration(conn, tenant, prevision, payload.date_reelle)

    @router.get("/calibrations")
    async def lister_calibrations(request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_prevision")
            return {"calibrations": depot.calibrations(conn, _tenant(request))}

    @router.get("/budgets")
    async def lire_budgets(request: Request, initiative_id: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_budget")
            return budget.resume(depot, conn, _tenant(request), initiative_id)

    @router.post("/budgets", status_code=201)
    async def creer_budget(payload: BudgetCreate, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "proposer_plan")
            identifiant = depot.enregistrer_budget(conn, _tenant(request), payload.model_dump())
            return {"id": identifiant}

    @router.get("/sources")
    async def lister_sources(request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_resume")
            return {"sources": [_source_publique(s) for s in depot.lister_sources(conn, _tenant(request))]}

    @router.post("/sources", status_code=201)
    async def creer_source(payload: SourceCreate, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "synchroniser")
            source = depot.creer_source(conn, _tenant(request), payload.model_dump())
            return _source_publique(source)

    @router.post("/webhooks/{source_id}", status_code=202)
    async def recevoir_webhook(source_id: str, request: Request, background_tasks: BackgroundTasks):
        tenant = _tenant(request)
        with _connexion(tenant) as conn:
            source = depot.lire_source(conn, tenant, source_id)
            if source is None:
                raise HTTPException(404, "source introuvable")
            if (source.get("usage") or "travail") != "travail":
                raise HTTPException(400, "webhook réservé aux sources de travail")
            secret = _secret_webhook(source)
            corps = await request.body()
            if not _signature(corps, secret, request.headers, source.get("provider")):
                raise HTTPException(401, "signature de webhook invalide")
            identifiant = _identifiant_webhook(request.headers, corps)
            nouveau = depot.enregistrer_webhook(conn, tenant, source_id, identifiant,
                                                source.get("provider"))
        if not nouveau:
            return {"ok": True, "duplicate": True}
        background_tasks.add_task(_sync_en_thread, _dsn(), tenant, source_id)
        return {"ok": True, "queued": True}

    @router.post("/sources/{source_id}/sync")
    async def synchroniser_source(source_id: str, request: Request):
        tenant = _tenant(request)
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "synchroniser")
            if depot.lire_source(conn, tenant, source_id) is None:
                raise HTTPException(404, "source introuvable")
        try:
            return await asyncio.to_thread(_sync_en_thread, _dsn(), tenant, source_id)
        except (ValueError, RuntimeError) as erreur:
            raise HTTPException(400, str(erreur)) from erreur

    @router.get("/sante")
    async def sante(request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "lire_resume")
            return depot.planification_sante(conn, _tenant(request))

    @router.get("/roles")
    async def lister_roles(request: Request, acteur: Optional[str] = None):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "gerer_roles")
            return {"roles": depot.roles(conn, _tenant(request), acteur)}

    @router.post("/roles", status_code=201)
    async def creer_role(payload: RoleCreate, request: Request):
        with _connexion(_tenant(request)) as conn:
            _role(conn, request, "gerer_roles")
            try:
                return roles.affecter(depot, conn, _tenant(request), payload.acteur, payload.role,
                                      perimetre_type=payload.perimetre_type,
                                      perimetre_id=payload.perimetre_id,
                                      debut=payload.debut, fin=payload.fin)
            except ValueError as erreur:
                raise HTTPException(400, str(erreur)) from erreur

    return router
