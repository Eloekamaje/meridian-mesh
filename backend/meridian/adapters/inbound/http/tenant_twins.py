"""Résolution des Twins visible dans un tenant, pour les routes historiques.

La collection Mongo ``jumeaux`` reste la vitrine du tenant ``demo``. Pour les
autres tenants, la source de vérité est Postgres : les Twins typés y portent
``tenant_id`` et ne doivent jamais être remplacés par la vitrine globale.
"""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
import os
from typing import Any

import psycopg


def _dsn() -> str:
    return str(os.environ.get("JUMEAU_PG_DSN") or "").strip()


def _ligne(twin: dict) -> dict:
    """Ajoute les champs attendus par les routes historiques (Atlas, Flore)."""
    return {
        **twin,
        "reel": True,
        "statut": twin.get("statut") or "actif",
        "sources": twin.get("sources") or {},
        "sources_detail": twin.get("sources_detail") or [],
        "position": twin.get("position"),
        "mission": twin.get("mission") or "",
    }


async def jumeaux_du_tenant(db, tenant: str, projection: dict | None = None,
                            limite: int = 200) -> list[dict]:
    """Liste les Twins du tenant sans jamais exposer la vitrine d'un autre tenant."""
    tenant = str(tenant or "local").strip() or "local"
    if tenant in {"local", "demo"}:
        return await db.jumeaux.find({}, projection or {"_id": 0}).to_list(limite)
    dsn = _dsn()
    if not dsn:
        return []

    def lire() -> list[dict]:
        from meridian.adapters.outbound.postgres import rls, twins_types

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            contexte = rls.contexte_tenant(conn, tenant) if rls.est_actif() else nullcontext()
            with contexte:
                twins = twins_types.lister_twins(conn, tenant, limite=limite)
        return [_ligne(dict(twin)) for twin in twins]

    return await asyncio.to_thread(lire)


async def jumeau_du_tenant(db, tenant: str, jid: str, projection: dict | None = None) -> dict | None:
    """Lit un Twin uniquement s'il appartient au tenant courant."""
    tenant = str(tenant or "local").strip() or "local"
    jid = str(jid or "").strip()
    if not jid:
        return None
    if tenant in {"local", "demo"}:
        return await db.jumeaux.find_one({"id": jid}, projection or {"_id": 0})
    twins = await jumeaux_du_tenant(db, tenant, {"_id": 0}, limite=1000)
    return next((twin for twin in twins if twin.get("id") == jid), None)


__all__ = ["jumeau_du_tenant", "jumeaux_du_tenant"]
