"""Recherche dans le Postgres canonique, sans OpenSearch ni projection.

La recherche combine `websearch_to_tsquery` (index GIN) et un repli `ILIKE` pour les
requêtes courtes ou partielles. Aucun appel réseau, aucun secret.
"""
from __future__ import annotations

from psycopg.rows import dict_row

MAX_RESULTATS = 50


def _tenant(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id vide : recherche refusée")
    return tenant_id.strip()


def _limite(limite: int) -> int:
    return max(1, min(int(limite), MAX_RESULTATS))


def rechercher_jumeaux(conn, tenant_id: str, requete: str, limite: int = 20) -> list[dict]:
    """Twin applicatifs ou métier, classés par pertinence, dans le tenant."""
    tenant, texte = _tenant(tenant_id), str(requete or "").strip()
    if not texte:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            SELECT id, nom, mission, type,
                   ts_rank_cd(to_tsvector('french', coalesce(nom, '') || ' ' || coalesce(mission, '')),
                              websearch_to_tsquery('french', %s)) AS score
            FROM jumeau
            WHERE tenant_id = %s
              AND (to_tsvector('french', coalesce(nom, '') || ' ' || coalesce(mission, ''))
                   @@ websearch_to_tsquery('french', %s)
                   OR nom ILIKE '%%' || %s || '%%'
                   OR mission ILIKE '%%' || %s || '%%')
            ORDER BY score DESC, nom, id LIMIT %s
            """, (texte, tenant, texte, texte, texte, _limite(limite))).fetchall()


def rechercher_claims(conn, tenant_id: str, requete: str, limite: int = 20) -> list[dict]:
    """Claims du tenant classés par pertinence, avec leur preuve la plus récente."""
    tenant, texte = _tenant(tenant_id), str(requete or "").strip()
    if not texte:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            SELECT c.id, c.jumeau_id, c.predicat, c.objet, c.mode, c.statut, c.maturite,
                   ts_rank_cd(to_tsvector('french', coalesce(c.sujet, '') || ' ' || coalesce(c.predicat, '')
                                          || ' ' || coalesce(c.objet, '')),
                              websearch_to_tsquery('french', %s)) AS score
            FROM claim c
            WHERE c.tenant_id = %s AND c.valide_jusqua IS NULL
              AND (to_tsvector('french', coalesce(c.sujet, '') || ' ' || coalesce(c.predicat, '')
                               || ' ' || coalesce(c.objet, '')) @@ websearch_to_tsquery('french', %s)
                   OR c.objet ILIKE '%%' || %s || '%%')
            ORDER BY score DESC, c.id LIMIT %s
            """, (texte, tenant, texte, texte, _limite(limite))).fetchall()
