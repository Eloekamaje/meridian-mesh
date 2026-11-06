"""Mémoire pertinente pour le chat : retrieval borné, sans casser le tour si Postgres manque."""
from __future__ import annotations

import asyncio
import os

__all__ = ["recuperer"]


def _lire(tenant: str, question: str, twin_ids, limite: int, consommateur=None,
          twin_proprietaire=None):
    from meridian.adapters.outbound.postgres import retrieval_memoire
    import psycopg

    dsn = os.getenv("JUMEAU_PG_DSN")
    if not dsn:
        return []
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        candidats = retrieval_memoire.recuperer(
            conn, tenant, question=question, twin_ids=tuple(twin_ids or ()), limite=limite,
            consommateur=consommateur, twin_proprietaire=twin_proprietaire)
    return [c.as_dict() if hasattr(c, "as_dict") else dict(c) for c in candidats]


async def recuperer(tenant: str, question: str, twin_ids=(), limite: int = 5,
                    consommateur=None, twin_proprietaire=None) -> list[dict]:
    """Les souvenirs classés pour la question ; panne ou absence de base = pas de mémoire."""
    if not tenant or not question:
        return []
    try:
        return await asyncio.to_thread(
            _lire, tenant, question, tuple(twin_ids or ()), limite, consommateur,
            twin_proprietaire)
    except Exception:
        return []
