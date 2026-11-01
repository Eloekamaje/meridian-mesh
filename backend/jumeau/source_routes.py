"""API de l'alimentation pull-first des sources : santé, ingestion manuelle, pause/reprise, journal des runs.

Le routeur ne déclenche jamais l'ingestion dans la requête HTTP : il enfile un run durable et rend ``202`` avec
son identifiant, le worker le réclame ensuite. Aucune réponse ne contient d'emplacement, d'URL ou de secret :
:mod:`jumeau.ingestion_runtime` ne projette que des champs sûrs.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Callable
from urllib.parse import urlparse

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from jumeau import ingestion_runtime as runtime

journal = logging.getLogger("meridian.ingestion.http")


def _signature_valide(corps: bytes, entete: str | None, secret: str) -> bool:
    """Signature GitHub ``sha256=...`` (ou hex brut) en comparaison à temps constant."""
    if not entete or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", entete) or hmac.compare_digest(digest, entete)


def _depot_correspond(repo: str, url: str | None) -> bool:
    """« org/repo » d'un webhook GitHub contre le chemin de l'URL de la source."""
    if not repo or not url:
        return True
    chemin = urlparse(url).path.strip("/")
    if chemin.endswith(".git"):
        chemin = chemin[:-4]
    return chemin.lower() == repo.lower()


def construire_router(
    *,
    connect: Callable[[], Any] | None = None,
    resoudre_tenant: Callable[[Request, str | None], str] | None = None,
    secret_webhook: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/boucle/sources", tags=["sources"])

    def _connect():
        if connect is not None:
            return connect()
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, "Couche cognitive non configurée (JUMEAU_PG_DSN)")
        return psycopg.connect(dsn, autocommit=True, connect_timeout=5)

    def _avec(action):
        conn = _connect()
        try:
            return action(conn)
        finally:
            fermer = getattr(conn, "close", None)
            if fermer:
                fermer()

    def _secret() -> str:
        return (secret_webhook or os.environ.get("JUMEAU_WEBHOOK_SECRET", "")).strip()

    def _tenant(request: Request, x_tenant: str | None) -> str:
        if resoudre_tenant is None:
            raise HTTPException(503, "Résolution de tenant non configurée")
        return resoudre_tenant(request, x_tenant)

    def _erreurs(exc: Exception) -> HTTPException:
        if isinstance(exc, runtime.SourceIntrouvable):
            return HTTPException(404, "Source introuvable")
        if isinstance(exc, runtime.TransitionInvalide):
            return HTTPException(409, str(exc))
        if isinstance(exc, ValueError):
            return HTTPException(400, str(exc))
        return HTTPException(503, "runtime d'ingestion indisponible")

    async def _executer(action, tenant: str):
        try:
            return await asyncio.to_thread(_avec, action)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - l'API traduit, le worker garde le détail durable
            journal.warning("sources %s : %s", tenant, type(exc).__name__)
            raise _erreurs(exc) from exc

    @router.get("/sante")
    async def sante(request: Request, x_tenant: str | None = Header(None)):
        """État des sources planifiées du tenant : lag, dernière erreur assainie, run courant. Jamais URL/secret."""
        tenant = _tenant(request, x_tenant)
        donnees = await _executer(lambda conn: runtime.sante_sources(conn, tenant), tenant)
        return JSONResponse(content=donnees, headers={"Cache-Control": "no-store"})

    @router.post("/{source_id}/webhook")
    async def webhook(
        source_id: int,
        request: Request,
        x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
        x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    ):
        """Accélérateur pull-first : vérifie la signature, puis enfile un run ; le worker fait l'ingestion.

        Le SHA est toujours revérifié par le gardien. Un webhook qui ne concerne pas la branche/dépôt suivi,
        ou qui rejoue le SHA courant, est acquitté sans créer de run.
        """
        secret = _secret()
        if not secret:
            raise HTTPException(503, "Webhook non configuré (JUMEAU_WEBHOOK_SECRET)")
        corps = await request.body()
        if not _signature_valide(corps, x_hub_signature_256, secret):
            raise HTTPException(401, "Signature invalide")
        if (x_github_event or "").lower() == "ping":
            return JSONResponse(status_code=202, content={"ignore": True, "raison": "ping"})
        try:
            payload = json.loads(corps or b"{}")
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "Payload JSON invalide") from exc
        if not isinstance(payload, dict):
            raise HTTPException(400, "Payload JSON invalide")

        def action(conn):
            ligne = conn.execute(
                "SELECT tenant_id, url, branche, curseur FROM source WHERE id = %s",
                (source_id,),
            ).fetchone()
            if not ligne:
                raise runtime.SourceIntrouvable("source introuvable")
            tenant, url, branche, curseur = ligne
            ref = str(payload.get("ref") or "")
            depot = payload.get("repository")
            repo = str((depot.get("full_name") if isinstance(depot, dict) else "") or "")
            tete = payload.get("head_commit")
            after = str(payload.get("after") or (tete.get("id") if isinstance(tete, dict) else "") or "")
            if payload.get("deleted"):
                return {"ignore": True, "raison": "branche supprimée"}
            if ref and not ref.startswith("refs/heads/"):
                return {"ignore": True, "raison": "référence non suivie"}
            if ref and ref.removeprefix("refs/heads/") != (branche or "main"):
                return {"ignore": True, "raison": "branche non suivie"}
            if not _depot_correspond(repo, url):
                return {"ignore": True, "raison": "dépôt non suivi"}
            if after and curseur and after == curseur:
                return {"ignore": True, "raison": "sha inchangé"}
            resultat = runtime.enfiler_source(conn, source_id, tenant, force=True)
            run = runtime.run_public(resultat["run"])
            return {"source_id": source_id, "tenant": tenant, "run_id": run["id"],
                    "etat": run["etat"], "cree": resultat["cree"]}

        resultat = await _executer(lambda conn: action(conn), "webhook")
        return JSONResponse(status_code=202, content=resultat, headers={"Cache-Control": "no-store"})

    @router.post("/{source_id}/ingest")
    async def ingerer(source_id: int, request: Request, x_tenant: str | None = Header(None)):
        """Enfile une ingestion explicite (même hors échéance) et rend ``202`` avec l'identifiant du run."""
        tenant = _tenant(request, x_tenant)
        resultat = await _executer(
            lambda conn: runtime.enfiler_source(conn, source_id, tenant, force=True), tenant)
        run = runtime.run_public(resultat["run"])
        corps = {"source_id": source_id, "tenant": tenant, "run_id": run["id"],
                 "etat": run["etat"], "cree": resultat["cree"]}
        return JSONResponse(
            status_code=202,
            content=corps,
            headers={"Cache-Control": "no-store",
                     "Location": f"/api/boucle/sources/{source_id}/runs"},
        )

    @router.post("/{source_id}/pause")
    async def pause(source_id: int, request: Request, x_tenant: str | None = Header(None)):
        tenant = _tenant(request, x_tenant)
        schedule = await _executer(
            lambda conn: runtime.pause_source(conn, source_id, tenant), tenant)
        return JSONResponse(content={"ok": True, "source_id": source_id,
                                     "etat": schedule["etat"], "schedule": schedule},
                            headers={"Cache-Control": "no-store"})

    @router.post("/{source_id}/resume")
    async def reprendre(source_id: int, request: Request, x_tenant: str | None = Header(None)):
        tenant = _tenant(request, x_tenant)
        schedule = await _executer(
            lambda conn: runtime.resume_source(conn, source_id, tenant), tenant)
        return JSONResponse(content={"ok": True, "source_id": source_id,
                                     "etat": schedule["etat"], "schedule": schedule},
                            headers={"Cache-Control": "no-store"})

    @router.get("/{source_id}/runs")
    async def runs(source_id: int, request: Request, x_tenant: str | None = Header(None),
                   limite: int = Query(20, ge=1, le=200)):
        tenant = _tenant(request, x_tenant)
        lignes = await _executer(
            lambda conn: runtime.runs_source(conn, source_id, tenant, limite=limite), tenant)
        return JSONResponse(content={"source_id": source_id, "tenant": tenant, "runs": lignes,
                                     "limite": limite},
                            headers={"Cache-Control": "no-store"})

    return router
