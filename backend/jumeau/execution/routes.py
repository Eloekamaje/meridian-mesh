"""Adapter HTTP du runtime d'exécution.

Le routeur ne contient aucune règle d'état : il traduit une requête en commande,
puis délègue au dépôt. Les longues exécutions ne bloquent jamais la requête HTTP :
elles retournent `202 + run_id` et le client reprend le flux SSE depuis le journal.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from jumeau import rls
from jumeau.execution import depot
from jumeau.execution.modele import (
    ApprobationIntrouvable,
    CommandeExecution,
    ConflitApprobation,
    ConflitIdempotence,
    ETATS_TERMINAUX,
    Priorite,
    QuotaDepasse,
    RunIntrouvable,
    TransitionInvalide,
)

journal = logging.getLogger("meridian.execution.http")
TAILLE_PAYLOAD_MAX = 256 * 1024


class CreerRunIn(BaseModel):
    type: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=300)
    priorite: str = "standard"
    deadline_at: datetime | None = None
    correlation_id: str | None = Field(default=None, max_length=200)
    causation_id: str | None = Field(default=None, max_length=200)


class ApprobationIn(BaseModel):
    approuve: bool | None = None
    decision: str | None = Field(default=None, pattern=r"^(approuver|rejeter)$")
    etape: str | None = Field(default=None, min_length=1, max_length=200)
    outil: str | None = Field(default=None, min_length=1, max_length=200)
    cible: str | None = Field(default=None, min_length=1, max_length=500)
    operation: str | None = Field(default=None, min_length=1, max_length=200)
    motif: str | None = Field(default=None, max_length=2000)


def _decision_approuvee(data: ApprobationIn) -> bool:
    if data.approuve is None and data.decision is None:
        raise HTTPException(400, "approuve ou decision est requis")
    if data.approuve is not None and data.decision is not None:
        if data.approuve != (data.decision == "approuver"):
            raise HTTPException(400, "approuve et decision se contredisent")
        return data.approuve
    if data.approuve is not None:
        return data.approuve
    return data.decision == "approuver"


def construire_router(
    *,
    connect: Callable[[], Any] | None = None,
    resoudre_tenant: Callable[[Request, str | None], str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/runs", tags=["runs"])

    def _connect():
        if connect is not None:
            return connect()
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
        return psycopg.connect(dsn, autocommit=True, connect_timeout=5)

    def _avec(action, tenant: str | None = None):
        """Exécute l'action avec le contexte tenant quand RLS est actif.

        Le contexte est posé à l'intérieur d'une transaction pour que
        `set_config(..., true)` couvre bien l'action, même sur une connexion
        autocommit. RLS reste opt-in : sans `JUMEAU_RLS=1`, aucun SQL de policy
        n'est exécuté.
        """
        conn = _connect()
        try:
            if tenant is None or not rls.est_actif():
                return action(conn)
            with conn.transaction():
                with rls.contexte_tenant(conn, tenant):
                    return action(conn)
        finally:
            close = getattr(conn, "close", None)
            if close:
                close()

    def _tenant(request: Request, x_tenant: str | None) -> str:
        if resoudre_tenant is None:
            raise HTTPException(503, "Résolution de tenant non configurée")
        return resoudre_tenant(request, x_tenant)

    def _public(run):
        return depot.run_public(run)

    @router.post("")
    async def creer_run(data: CreerRunIn, request: Request, x_tenant: str | None = Header(None)):
        try:
            tenant = _tenant(request, x_tenant)
            priorite = Priorite(data.priorite)
            deadline = data.deadline_at
            if deadline is not None and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            cle = (data.idempotency_key or "").strip()
            if data.idempotency_key is not None and not cle:
                raise ValueError("idempotency_key ne peut pas être vide")
            if len(json.dumps(data.payload, ensure_ascii=False, default=str)) > TAILLE_PAYLOAD_MAX:
                raise HTTPException(413, "payload de run trop volumineux")
            commande = CommandeExecution(
                tenant_id=tenant,
                type=data.type,
                payload=data.payload,
                idempotency_key=cle or uuid4().hex,
                acteur=str(getattr(request.state, "utilisateur", None) or "demo")[:200],
                priorite=priorite,
                deadline_at=deadline,
                correlation_id=data.correlation_id,
                causation_id=data.causation_id,
            )
            run, cree = await asyncio.to_thread(
                _avec, lambda conn: depot.creer_run(conn, commande), tenant)
        except HTTPException:
            raise
        except QuotaDepasse as exc:
            raise HTTPException(429, str(exc)) from exc
        except ConflitIdempotence as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RunIntrouvable) as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        corps = _public(run)
        entetes = {"Cache-Control": "no-store"}
        try:
            entetes["Location"] = str(request.url_for("lire_run", run_id=corps["run_id"]))
        except Exception:
            entetes["Location"] = f"/api/runs/{corps['run_id']}"
        return JSONResponse(status_code=202 if cree else 200, content=corps, headers=entetes)

    @router.get("/approvals")
    async def lister_approbations(
        request: Request,
        x_tenant: str | None = Header(None),
        run_id: str | None = Query(None, max_length=200),
        statut: str = Query("PROPOSE", pattern=r"^(PROPOSE|APPROUVE|REJETE)$"),
        limite: int = Query(50, ge=1, le=200),
        avant_id: int | None = Query(None, ge=1),
    ):
        """Approbations du tenant, bornées et filtrées ; aucun payload n'est exposé."""
        try:
            tenant = _tenant(request, x_tenant)
            lignes = await asyncio.to_thread(
                _avec,
                lambda conn: depot.lister_approbations(
                    conn, tenant, run_id=run_id, statut=statut, limite=limite,
                    avant_id=avant_id,
                ),
                tenant,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        return JSONResponse(
            content={
                "approbations": [depot.approbation_resume(ligne) for ligne in lignes],
                "limite": limite,
            },
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/approvals/{approbation_id}")
    async def lire_approbation(
        approbation_id: int,
        request: Request,
        x_tenant: str | None = Header(None),
    ):
        try:
            tenant = _tenant(request, x_tenant)
            ligne = await asyncio.to_thread(
                _avec,
                lambda conn: depot.obtenir_approbation_par_id(conn, tenant, approbation_id),
                tenant,
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        if ligne is None:
            raise HTTPException(404, "approbation introuvable")
        return JSONResponse(
            content={"approbation": depot.approbation_resume(ligne)},
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/{run_id}")
    async def lire_run(run_id: str, request: Request, x_tenant: str | None = Header(None)):
        try:
            tenant = _tenant(request, x_tenant)
            run = await asyncio.to_thread(_avec, lambda conn: depot.obtenir_run(conn, tenant, run_id), tenant)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        if run is None:
            raise HTTPException(404, "run introuvable")
        return JSONResponse(content=_public(run), headers={"Cache-Control": "no-store"})

    @router.post("/{run_id}/cancel")
    async def annuler_run(run_id: str, request: Request, x_tenant: str | None = Header(None)):
        try:
            tenant = _tenant(request, x_tenant)
            run = await asyncio.to_thread(
                _avec, lambda conn: depot.demander_annulation(conn, tenant, run_id), tenant)
        except HTTPException:
            raise
        except RunIntrouvable as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        return JSONResponse(content=_public(run), headers={"Cache-Control": "no-store"})

    @router.get("/{run_id}/steps")
    async def etapes_run(run_id: str, request: Request, x_tenant: str | None = Header(None)):
        """Journal des étapes d'un run, avec les checkpoints persistés."""
        try:
            tenant = _tenant(request, x_tenant)
            run = await asyncio.to_thread(
                _avec, lambda conn: depot.obtenir_run(conn, tenant, run_id), tenant)
            if run is None:
                raise HTTPException(404, "run introuvable")
            lignes = await asyncio.to_thread(
                _avec, lambda conn: depot.etapes_run(conn, tenant, run_id), tenant)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        return JSONResponse(
            content={"run_id": run_id, "etapes": [depot.etape_public(ligne) for ligne in lignes]},
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/{run_id}/resume")
    async def reprendre_run(run_id: str, request: Request, x_tenant: str | None = Header(None)):
        """Remet en file un run RUNNING dont le bail a expiré (reprise après crash)."""
        try:
            tenant = _tenant(request, x_tenant)
            run = await asyncio.to_thread(
                _avec, lambda conn: depot.reprendre_run(conn, tenant, run_id), tenant)
        except HTTPException:
            raise
        except RunIntrouvable as exc:
            raise HTTPException(404, str(exc)) from exc
        except TransitionInvalide as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        return JSONResponse(content=_public(run), headers={"Cache-Control": "no-store"})

    @router.post("/{run_id}/approval")
    async def decider_approbation(run_id: str, data: ApprobationIn, request: Request,
                                  x_tenant: str | None = Header(None)):
        tenant = _tenant(request, x_tenant)
        approuve = _decision_approuvee(data)
        acteur = str(getattr(request.state, "utilisateur", None) or "demo")[:200]
        try:
            resultat = await asyncio.to_thread(_avec, lambda conn: depot.decider_approbation(
                conn, tenant, run_id, approuve=approuve, acteur=acteur, motif=data.motif,
                etape=data.etape, cible=data.cible, operation=data.operation, outil=data.outil,
            ), tenant)
        except HTTPException:
            raise
        except (RunIntrouvable, ApprobationIntrouvable) as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ConflitApprobation, TransitionInvalide) as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        return JSONResponse(
            content={
                "run": _public(resultat["run"]),
                "effet": depot.effet_public(resultat["effet"]),
                "approbation": depot.approbation_public(resultat["approbation"]),
            },
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/{run_id}/events")
    async def evenements_run(run_id: str, request: Request, x_tenant: str | None = Header(None),
                             after: int = Query(0, ge=0),
                             last_event_id: str | None = Header(None, alias="Last-Event-ID")):
        tenant = _tenant(request, x_tenant)
        try:
            initial = await asyncio.to_thread(
                _avec, lambda conn: depot.obtenir_run(conn, tenant, run_id), tenant)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "runtime d'exécution indisponible") from exc
        if initial is None:
            raise HTTPException(404, "run introuvable")
        depart = after
        if last_event_id:
            try:
                depart = max(depart, int(last_event_id))
            except (TypeError, ValueError):
                pass

        def etat_et_evenements(conn, apres):
            run = depot.obtenir_run(conn, tenant, run_id)
            evts = depot.evenements(conn, tenant, run_id, apres)
            # Si l'état terminal est visible mais l'événement terminal ne l'est pas encore,
            # relire dans la même connexion : la transaction terminale a forcément commité l'événement.
            if run is not None and run["etat"] in ETATS_TERMINAUX and not evts:
                evts = depot.evenements(conn, tenant, run_id, apres)
            return run, evts

        async def flux():
            dernier = depart
            dernier_ping = time.monotonic()
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    run, evts = await asyncio.to_thread(
                        _avec, lambda conn: etat_et_evenements(conn, dernier), tenant)
                except Exception:
                    journal.exception("SSE run %s : lecture impossible", run_id)
                    yield "event: error\ndata: {\"message\":\"runtime indisponible\"}\n\n"
                    return
                if run is None:
                    yield "event: error\ndata: {\"message\":\"run introuvable\"}\n\n"
                    return
                for evenement in evts:
                    dernier = max(dernier, int(evenement["id"]))
                    charge = json.dumps(depot.evenement_public(evenement), ensure_ascii=False)
                    yield f"id: {dernier}\nevent: run\ndata: {charge}\n\n"
                if run["etat"] in ETATS_TERMINAUX and not evts:
                    yield f"event: done\ndata: {json.dumps({'run_id': run_id, 'etat': run['etat']})}\n\n"
                    return
                if time.monotonic() - dernier_ping >= 15:
                    yield ": ping\n\n"
                    dernier_ping = time.monotonic()
                await asyncio.sleep(0.5)

        return StreamingResponse(
            flux(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
