"""Index global des communautés : rapports précompilés, recherche lexicale + vecteurs."""
from __future__ import annotations

import os

from meridian.adapters.outbound import embeddings
from meridian.adapters.outbound.postgres import rls
from meridian.application import retrieval_hybride

__all__ = ["chercher", "lister", "remplacer"]


def _acl_autorise(acl, *, acteur="", role="", espace="") -> bool:
    strict = os.getenv("ACL_STRICT", "0").strip().lower() in {"1", "true", "oui", "yes"}
    if not isinstance(acl, dict) or not acl:
        return not strict
    if acl.get("public") is True:
        return True
    for cle, valeur in (("users", acteur), ("roles", role), ("espaces", espace)):
        autorises = acl.get(cle) or ()
        if isinstance(autorises, str):
            autorises = [autorises]
        if valeur and valeur in autorises:
            return True
    return False


def _connexion():
    import psycopg
    dsn = os.getenv("JUMEAU_PG_DSN")
    return psycopg.connect(dsn, connect_timeout=3) if dsn else None


def remplacer(tenant: str, communautes: list[dict]) -> int:
    conn = _connexion()
    if conn is None:
        return 0
    try:
        with rls.contexte_tenant(conn, tenant):
          with conn:
            conn.execute("DELETE FROM graph_community WHERE tenant_id = %s", (tenant,))
            for communaute in communautes:
                rapport = str(communaute.get("rapport") or communaute.get("resume") or "")
                try:
                    vecteur = embeddings.embed([rapport])[0]
                except embeddings.EmbeddingIndisponible:
                    vecteur = None
                conn.execute(
                    "INSERT INTO graph_community (tenant_id, community_id, level, membres, domaines, "
                    "relations, rapport, fingerprint, acl, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (tenant, communaute.get("id") or communaute.get("fingerprint"),
                     int(communaute.get("level") or 1),
                     list(communaute.get("membres") or ()), list(communaute.get("domain") or ()),
                     int(communaute.get("relations") or 0), rapport,
                     communaute.get("fingerprint") or "",
                     communaute.get("acl") if isinstance(communaute.get("acl"), dict) else {}, vecteur))
        return len(communautes)
    except Exception:
        return 0
    finally:
        conn.close()


def lister(tenant: str, *, limite: int = 50) -> list[dict]:
    conn = _connexion()
    if conn is None:
        return []
    try:
        with rls.contexte_tenant(conn, tenant):
          with conn:
            rows = conn.execute(
                "SELECT community_id, level, membres, domaines, relations, rapport, fingerprint, acl, embedding "
                "FROM graph_community WHERE tenant_id = %s ORDER BY level, relations DESC LIMIT %s",
                (tenant, limite)).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    colonnes = ("id", "level", "membres", "domain", "relations", "rapport", "fingerprint", "acl", "embedding")
    return [dict(zip(colonnes, row)) for row in rows]


def chercher(tenant: str, question: str, *, limite: int = 5,
             acteur: str = "", role: str = "", espace: str = "") -> list[dict]:
    communautes = [c for c in lister(tenant, limite=200)
                   if _acl_autorise(c.get("acl"), acteur=acteur, role=role, espace=espace)]
    if not communautes:
        return []
    try:
        vecteur = embeddings.embed([question])[0]
    except embeddings.EmbeddingIndisponible:
        vecteur = None
    for communaute in communautes:
        chunk = {"texte": communaute.get("rapport") or "", "embedding": communaute.get("embedding"),
                 "updated_at": None}
        communaute["score"] = retrieval_hybride.score(question, chunk, vecteur_question=vecteur)
    communautes.sort(key=lambda c: c.get("score", 0), reverse=True)
    return communautes[:limite]
