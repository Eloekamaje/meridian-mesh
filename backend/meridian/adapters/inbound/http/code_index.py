"""API de lecture de l'index legacy fédéré : résumé, couverture, observations et liens.

Le routeur est strictement en lecture : il ne reçoit aucun fichier et n'écrit
jamais de ligne. Le tenant vient du contexte de requête, le jumeau doit lui
appartenir, et toutes les lectures du magasin filtrent le couple.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request

from meridian.adapters.outbound.postgres import code_index_store
from meridian.adapters.outbound.postgres import depot as jumeau_depot

_LIMITE_DEFAUT = code_index_store.LIMITE_DEFAUT
_LIMITE_MAX = code_index_store.LIMITE_MAX
_DSN_MANQUANT = "Couche cognitive non configurée (JUMEAU_PG_DSN)"
_DSN_INDISPONIBLE = "Couche cognitive indisponible"


def construire_router(
    *,
    connect: Callable[[], Any] | None = None,
    resoudre_tenant: Callable[[Request, str | None], str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/jumeaux", tags=["code-index"])

    def _connect():
        if connect is not None:
            return connect()
        dsn = os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise HTTPException(503, _DSN_MANQUANT)
        return psycopg.connect(dsn, connect_timeout=5, autocommit=True)

    def _tenant(request: Request, x_tenant: str | None) -> str:
        if resoudre_tenant is None:
            raise HTTPException(503, "Résolution de tenant non configurée")
        return resoudre_tenant(request, x_tenant)

    def _limite(valeur: str | None) -> int:
        if valeur is None:
            return _LIMITE_DEFAUT
        try:
            nombre = int(valeur)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "limite invalide") from exc
        if nombre < 1 or nombre > _LIMITE_MAX:
            raise HTTPException(400, f"limite doit être comprise entre 1 et {_LIMITE_MAX}")
        return nombre

    def _lire(action, tenant: str, jumeau_id: str):
        conn = _connect()
        try:
            jumeau = jumeau_depot.jumeau_par_id(conn, jumeau_id)
            tenant_jumeau = jumeau.get("tenant_id") if isinstance(jumeau, Mapping) else None
            if not jumeau or tenant_jumeau != tenant:
                raise LookupError(jumeau_id)
            return action(conn)
        finally:
            fermer = getattr(conn, "close", None)
            if fermer:
                fermer()

    async def _executer(action, tenant: str, jumeau_id: str):
        try:
            return await asyncio.to_thread(_lire, action, tenant, jumeau_id)
        except HTTPException:
            raise
        except LookupError as exc:
            raise HTTPException(404, "Jumeau introuvable") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except psycopg.Error as exc:
            raise HTTPException(503, _DSN_INDISPONIBLE) from exc

    @router.get("/{jumeau_id}/code-index/resume")
    async def resume(
        jumeau_id: str,
        request: Request,
        x_tenant: str | None = Header(None, alias="X-Tenant"),
    ):
        """Compteurs de l'index du jumeau : observations, couverture et liens."""
        tenant = _tenant(request, x_tenant)
        donnees = await _executer(
            lambda conn: code_index_store.resume(conn, tenant, jumeau_id),
            tenant, jumeau_id)
        return {"tenant": tenant, "jumeau_id": jumeau_id, **donnees}

    @router.get("/{jumeau_id}/code-index/coverage")
    async def coverage(
        jumeau_id: str,
        request: Request,
        statut: str | None = Query(None, max_length=40),
        limite: str | None = Query(None, max_length=20),
        x_tenant: str | None = Header(None, alias="X-Tenant"),
    ):
        """Couverture explicite du jumeau, éventuellement filtrée par statut."""
        tenant = _tenant(request, x_tenant)
        maximum = _limite(limite)
        lignes = await _executer(
            lambda conn: code_index_store.lire_couverture(
                conn, tenant, jumeau_id, statut=statut, limite=maximum),
            tenant, jumeau_id)
        return {"tenant": tenant, "jumeau_id": jumeau_id, "limite": maximum,
                "couverture": lignes}

    @router.get("/{jumeau_id}/code-index/observations")
    async def observations(
        jumeau_id: str,
        request: Request,
        kind: str | None = Query(None, max_length=60),
        fichier: str | None = Query(None, max_length=1000),
        limite: str | None = Query(None, max_length=20),
        x_tenant: str | None = Header(None, alias="X-Tenant"),
    ):
        """Observations du jumeau, filtrées par type et fichier."""
        tenant = _tenant(request, x_tenant)
        maximum = _limite(limite)
        lignes = await _executer(
            lambda conn: code_index_store.lire_observations(
                conn, tenant, jumeau_id, kind=kind, fichier=fichier, limite=maximum),
            tenant, jumeau_id)
        return {"tenant": tenant, "jumeau_id": jumeau_id, "limite": maximum,
                "observations": lignes}

    @router.get("/{jumeau_id}/code-index/links")
    async def links(
        jumeau_id: str,
        request: Request,
        kind: str | None = Query(None, max_length=60),
        limite: str | None = Query(None, max_length=20),
        x_tenant: str | None = Header(None, alias="X-Tenant"),
    ):
        """Liens prouvés du jumeau, filtrés par famille."""
        tenant = _tenant(request, x_tenant)
        maximum = _limite(limite)
        lignes = await _executer(
            lambda conn: code_index_store.lire_liens(
                conn, tenant, jumeau_id, kind=kind, limite=maximum),
            tenant, jumeau_id)
        return {"tenant": tenant, "jumeau_id": jumeau_id, "limite": maximum,
                "liens": lignes}

    return router
