"""Recherche active de preuves et de contradictions dans le canonique.

Le SourcePlan ne reste pas déclaratif : il interroge les Claims par pertinence et remonte les
contradictions ouvertes des Twins concernés. Aucun appel réseau, aucun secret.
"""
from __future__ import annotations

from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import pg_recherche

__all__ = ["rechercher"]


def rechercher(conn, tenant_id: str, *, question: str, twin_ids=(), limite: int = 20) -> dict:
    """Rend les Claims pertinents, les preuves CONTRE et les contradictions ouvertes."""
    query = str(question or "").strip()
    twins = tuple(str(t) for t in twin_ids or () if t)
    claims = pg_recherche.rechercher_claims(conn, tenant_id, query, limite=limite) if query else []
    contradictions = []
    contre = []
    if twins:
        with conn.cursor(row_factory=dict_row) as cur:
            contradictions = cur.execute(
                "SELECT c.id, c.jumeau_id, c.claim_id, c.enonce, c.preuve_a, c.preuve_b, "
                "       c.systeme_a, c.systeme_b, c.cree_le "
                "FROM contradiction c JOIN jumeau j ON j.id = c.jumeau_id "
                "WHERE j.tenant_id = %s AND c.jumeau_id = ANY(%s) AND c.statut = 'OUVERTE' "
                "ORDER BY c.id LIMIT %s",
                (tenant_id, list(twins), max(1, min(int(limite), 50))),
            ).fetchall()
        with conn.cursor(row_factory=dict_row) as cur:
            contre = cur.execute(
                "SELECT p.id AS preuve_id, p.locator, p.chemin, cp.claim_id "
                "FROM claim_preuve cp JOIN preuve p ON p.id = cp.preuve_id "
                "JOIN claim c ON c.id = cp.claim_id "
                "WHERE c.tenant_id = %s AND c.jumeau_id = ANY(%s) AND cp.role = 'CONTRE' "
                "ORDER BY p.id DESC LIMIT %s",
                (tenant_id, list(twins), max(1, min(int(limite), 50))),
            ).fetchall()
    return {
        "tenant": tenant_id,
        "question": query,
        "twin_ids": list(twins),
        "claims": [dict(ligne) for ligne in claims],
        "contradictions": [dict(ligne) for ligne in contradictions],
        "contre": [dict(ligne) for ligne in contre],
    }
