"""API du noyau de raisonnement : qualifier et construire un dossier sans appeler de modèle.

Ces routes sont volontairement sans effet : elles exposent la politique, les niveaux, les questions,
la critique structurelle et les gates. La génération reste dans l'orchestrateur et le ToolGateway.
"""
from __future__ import annotations

import os
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import auth as auth_identite
from meridian.adapters.outbound.postgres import apprentissage_raisonnement as apprentissage_pg
from meridian.adapters.outbound.postgres import calibration_croyances as calibration_pg
from meridian.adapters.outbound.postgres import execution_defaults
from meridian.adapters.outbound.postgres import execution_depot
from meridian.adapters.outbound.postgres import dossiers_raisonnement
from meridian.application import action_raisonnement, apprentissage_raisonnement, calibration_croyances as calibration_application, evaluation_raisonnement
from meridian.application import epistemie as epistemie_application
from meridian.domain import epistemie as epistemie_domaine
from meridian.application.execution.modele import (
    ApprobationRequise, EffetRejete, EchecEffet, OutilRefuse, TransitionInvalide,
)
from meridian.application import noyau_raisonnement

__all__ = ["construire_router"]


class QualificationRaisonnement(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    contexte: dict[str, Any] = Field(default_factory=dict)


class AnalyseRaisonnement(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    reponse: dict[str, Any] | str = Field(default_factory=dict)
    contexte: dict[str, Any] = Field(default_factory=dict)
    travail_id: str = Field(default="", max_length=128)


class EvaluationRaisonnement(BaseModel):
    dossier: dict[str, Any] = Field(default_factory=dict)


class ResolutionCroyance(BaseModel):
    outcome: bool
    motif: str = Field(min_length=1, max_length=1000)
    preuve: str = Field("", max_length=200)


class RevisionRaisonnement(BaseModel):
    belief_id: str = Field(min_length=1, max_length=80)
    nouveau_statut: str = Field(min_length=1, max_length=20)
    motif: str = Field(min_length=1, max_length=1000)
    preuves_ajoutees: list[str] = Field(default_factory=list)
    preuves_retirees: list[str] = Field(default_factory=list)


class ActionRaisonnement(BaseModel):
    dossier_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=200)
    etape: str = Field(min_length=1, max_length=200)
    outil: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=200)
    cible: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] | None = None
    ecriture: bool = False


class ApprentissageRaisonnement(BaseModel):
    dossier: dict[str, Any] = Field(default_factory=dict)
    retour: str | None = Field(None, max_length=4000)
    persister: bool = False


def construire_router() -> APIRouter:
    router = APIRouter(prefix="/raisonnement", tags=["raisonnement"])

    @router.post("/qualifier")
    def qualifier(payload: QualificationRaisonnement):
        """Qualifie la demande et expose le cadre, les questions et le plan borné."""
        demande = noyau_raisonnement.qualifier(payload.question, payload.contexte)
        cadre = noyau_raisonnement.cadrer(demande, payload.contexte)
        plan = noyau_raisonnement.planifier(demande, cadre)
        return {
            "demande": demande.as_dict(),
            "cadre": cadre.as_dict(),
            "plan": plan.as_dict(),
        }

    @router.post("/analyser")
    def analyser(
        payload: AnalyseRaisonnement,
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Construit un dossier pour une réponse existante et expose les gates."""
        dossier = noyau_raisonnement.analyser_reponse(
            payload.question, payload.reponse, contexte=payload.contexte,
            tenant=x_tenant or "", travail_id=payload.travail_id)
        return dossier.as_dict()

    @router.post("/evaluer")
    def evaluer(payload: EvaluationRaisonnement):
        """Évalue la présence des artefacts de raisonnement d'un dossier existant."""
        return evaluation_raisonnement.evaluer(payload.dossier)

    @router.post("/apprentissage")
    def apprentissage(
        payload: ApprentissageRaisonnement,
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Propose un Learning ; `persister=true` l'écrit comme proposition, jamais comme canonique."""
        learning = apprentissage_raisonnement.proposer(
            payload.dossier, retour=payload.retour)
        if payload.persister and learning is not None:
            dsn = os.environ.get("JUMEAU_PG_DSN")
            if not dsn:
                raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
            tenant = x_tenant or os.environ.get("JUMEAU_TENANT") or "local"
            dossier_id = str(payload.dossier.get("id") or "dossier")
            learning["persiste"] = apprentissage_pg.persister_dsn(
                dsn, tenant, dossier_id, learning)
        return {"learning": learning}

    @router.post("/apprentissage/{learning_id}/promouvoir")
    def promouvoir_learning(
        learning_id: str,
        motif: str = Query("", max_length=2000),
        acteur: str = Depends(auth_identite.acteur),
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Promotion humaine explicite d'un Learning proposé ; aucune promotion automatique."""
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        tenant = x_tenant or os.environ.get("JUMEAU_TENANT") or "local"
        try:
            objet = apprentissage_pg.promouvoir_dsn(dsn, tenant, learning_id, acteur, motif)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"learning": objet}

    @router.post("/dossiers/{dossier_id}/croyances/{belief_id}/resoudre")
    def resoudre_croyance(
        dossier_id: str,
        belief_id: str,
        payload: ResolutionCroyance,
        acteur: str = Depends(auth_identite.acteur),
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Résout une croyance par un outcome : révision + calibration, sans promotion implicite."""
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        tenant = x_tenant or os.environ.get("JUMEAU_TENANT") or "local"
        dossier = dossiers_raisonnement.lire_dsn(dsn, tenant, dossier_id)
        if dossier is None:
            raise HTTPException(404, "Dossier de raisonnement introuvable")
        beliefs = list(dossier.get("beliefs") or ())
        trouvee = next((b for b in beliefs if b.get("id") == belief_id), None)
        if trouvee is None:
            raise HTTPException(404, "Croyance introuvable")
        try:
            croyance, revision = calibration_application.resoudre(
                epistemie_domaine.Belief(**trouvee),
                outcome=payload.outcome, motif=payload.motif,
                acteur=acteur, preuve=payload.preuve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        beliefs = [croyance.as_dict() if b.get("id") == belief_id else b for b in beliefs]
        dossier["beliefs"] = beliefs
        dossier["revisions"] = [*(dossier.get("revisions") or ()), revision.as_dict()]
        # Résoudre d'abord la prédiction originale, puis persister la croyance révisée :
        # sinon l'upsert de la croyance mettrait la confiance à jour avant la mesure.
        calibration = calibration_pg.resoudre_dsn(
            dsn, tenant, dossier_id, belief_id, payload.outcome)
        dossiers_raisonnement.enregistrer_dsn(
            dsn, tenant, dossier, dossier.get("travail_id") or "")
        return {"dossier": dossier, "belief": croyance.as_dict(),
                "revision": revision.as_dict(), "calibration": calibration}

    @router.get("/calibration")
    def calibration(
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        return calibration_pg.rapport_dsn(
            dsn, x_tenant or os.environ.get("JUMEAU_TENANT") or "local")

    @router.post("/dossiers/{dossier_id}/reviser")
    def reviser_croyance(
        dossier_id: str,
        payload: RevisionRaisonnement,
        acteur: str = Depends(auth_identite.acteur),
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Révision humaine d'une croyance : conserve l'ancien statut et la preuve du changement."""
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        tenant = x_tenant or os.environ.get("JUMEAU_TENANT") or "local"
        dossier = dossiers_raisonnement.lire_dsn(dsn, tenant, dossier_id)
        if dossier is None:
            raise HTTPException(404, "Dossier de raisonnement introuvable")
        beliefs = list(dossier.get("beliefs") or ())
        trouve = next((b for b in beliefs if b.get("id") == payload.belief_id), None)
        if trouve is None:
            raise HTTPException(404, "Croyance introuvable")
        try:
            belief = epistemie_domaine.Belief(**trouve)
            revision = epistemie_application.reviser(
                belief, nouveau_statut=payload.nouveau_statut, motif=payload.motif,
                acteur=acteur, preuves_ajoutees=payload.preuves_ajoutees,
                preuves_retirees=payload.preuves_retirees)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        trouve["statut"] = revision.nouveau_statut
        dossier["beliefs"] = beliefs
        dossier["revisions"] = [*(dossier.get("revisions") or ()), revision.as_dict()]
        dossiers_raisonnement.enregistrer_dsn(
            dsn, tenant, dossier, dossier.get("travail_id") or "")
        return dossier

    @router.post("/actions")
    def action(
        payload: ActionRaisonnement,
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        """Exécute une action gouvernée par le dossier et le ToolGateway, jamais directement."""
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Runtime d'action non configuré (JUMEAU_PG_DSN)")
        outils = execution_defaults.outils_depuis_env()
        if not outils:
            raise HTTPException(503, "Aucun outil d'action configuré (EXECUTION_TOOLS)")
        tenant = x_tenant or os.environ.get("JUMEAU_TENANT") or "local"
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
            dossier = dossiers_raisonnement.lire(conn, tenant, payload.dossier_id)
            if dossier is None:
                raise HTTPException(404, "Dossier de raisonnement introuvable")
            run = execution_depot.obtenir_run(conn, tenant, payload.run_id)
            if run is None:
                raise HTTPException(404, "Run d'action introuvable")
        gateway = execution_defaults.ToolGateway(
            lambda: psycopg.connect(dsn, connect_timeout=5, autocommit=True),
            allowlist=execution_defaults.allowlist_depuis_env(),
            outils=outils,
        )
        try:
            effet = action_raisonnement.executer(
                gateway, dossier, run, etape=payload.etape, outil=payload.outil,
                operation=payload.operation, cible=payload.cible,
                payload=payload.payload, ecriture=payload.ecriture,
            )
        except ApprobationRequise as exc:
            return JSONResponse(
                status_code=202,
                content={
                    "statut": "approbation_requise", "run_id": exc.run_id,
                    "etape": exc.etape, "outil": exc.outil, "cible": exc.cible,
                    "operation": exc.operation,
                },
                headers={"Cache-Control": "no-store"},
            )
        except (action_raisonnement.ActionRefusee, OutilRefuse) as exc:
            raise HTTPException(403, str(exc)) from exc
        except (EffetRejete, TransitionInvalide, EchecEffet) as exc:
            raise HTTPException(409, str(exc)) from exc
        return execution_depot.effet_public(effet)

    @router.get("/dossiers/{dossier_id}")
    def lire_dossier(
        dossier_id: str,
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        dossier = dossiers_raisonnement.lire_dsn(
            dsn, x_tenant or os.environ.get("JUMEAU_TENANT") or "local", dossier_id)
        if dossier is None:
            raise HTTPException(404, "Dossier de raisonnement introuvable")
        return dossier

    @router.get("/dossiers")
    def lister_dossiers(
        travail_id: str | None = Query(None, max_length=128),
        limite: int = Query(50, ge=1, le=200),
        x_tenant: str | None = Header(None, alias="X-Tenant", max_length=128),
    ):
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Persistance Postgres non configurée (JUMEAU_PG_DSN)")
        return dossiers_raisonnement.lister_dsn(
            dsn, x_tenant or os.environ.get("JUMEAU_TENANT") or "local",
            travail_id=travail_id, limite=limite)

    return router
