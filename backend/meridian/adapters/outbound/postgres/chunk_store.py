"""Stockage des chunks documentaires et recherche hybride (lexicale + vecteurs + graphe)."""
from __future__ import annotations

import logging
import os

from psycopg.types.json import Jsonb

from meridian.adapters.outbound import embeddings
from meridian.adapters.outbound import reranking
from meridian.adapters.outbound.postgres import rls
from meridian.application import retrieval_hybride

__all__ = ["chercher", "indexer", "reembedder"]

journal = logging.getLogger("meridian.chunk_store")


def _connexion():
    import psycopg
    dsn = os.getenv("JUMEAU_PG_DSN")
    if not dsn:
        return None
    return psycopg.connect(dsn, connect_timeout=3)


def indexer(tenant: str, source_id, twin_id: str, document_ref: str, version: str,
            titre: str, chunks: list[dict], *, modele: str | None = None, acl: dict | None = None) -> int:
    """Remplace les chunks d'un document à sa version courante ; les anciennes versions sont retirées."""
    if not chunks:
        return 0
    try:
        vecteurs = embeddings.embed([
            f"{titre}\n{chunk.get('section') or ''}\n{chunk['texte']}" for chunk in chunks])
        modele_vecteurs = modele or embeddings.modele()
        if len(vecteurs) != len(chunks):
            vecteurs = [None] * len(chunks)
            modele_vecteurs = "lexical-only"
    except embeddings.EmbeddingIndisponible:
        vecteurs = [None] * len(chunks)
        modele_vecteurs = "lexical-only"
    conn = _connexion()
    if conn is None:
        return 0
    try:
        with rls.contexte_tenant(conn, tenant):
          conn.execute(
              "DELETE FROM document_chunk WHERE tenant_id = %s AND source_id = %s AND document_ref = %s",
              (tenant, source_id, document_ref))
          for chunk, vecteur in zip(chunks, vecteurs):
              conn.execute(
                  "INSERT INTO document_chunk (tenant_id, source_id, twin_id, document_ref, version, "
                  "ordinal, section, titre, texte, texte_hash, locator, acl, embedding, embedding_model, "
                  "embedding_dim, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
                  "ON CONFLICT (tenant_id, source_id, document_ref, version, ordinal) DO UPDATE SET "
                  "texte = EXCLUDED.texte, texte_hash = EXCLUDED.texte_hash, locator = EXCLUDED.locator, "
                  "acl = EXCLUDED.acl, embedding = EXCLUDED.embedding, "
                  "embedding_model = EXCLUDED.embedding_model, embedding_dim = EXCLUDED.embedding_dim, "
                  "updated_at = now()",
                  (tenant, source_id, twin_id or None, document_ref, version, chunk["ordinal"],
                   chunk.get("section") or "", titre, chunk["texte"], chunk.get("texte_hash") or "",
                   chunk["locator"], Jsonb(acl or {}), vecteur, modele_vecteurs,
                   len(vecteur) if vecteur else None))
        return len(chunks)
    except Exception as exc:
        journal.warning("indexation documentaire échouée (%s)", type(exc).__name__)
        return 0
    finally:
        conn.close()


def mettre_a_jour_acl(tenant: str, source_id, acl: dict | None) -> int:
    conn = _connexion()
    if conn is None:
        return 0
    try:
        with rls.contexte_tenant(conn, tenant):
          resultat = conn.execute(
              "UPDATE document_chunk SET acl = %s, updated_at = now() "
              "WHERE tenant_id = %s AND source_id IS NOT DISTINCT FROM %s",
              (Jsonb(acl or {}), tenant, source_id))
          return int(getattr(resultat, "rowcount", 0) or 0)
    except Exception as exc:
        journal.warning("mise à jour ACL documentaire échouée (%s)", type(exc).__name__)
        return 0
    finally:
        conn.close()


def _acl_autorise(acl, *, acteur: str = "", role: str = "", espace: str = "") -> bool:
    import os
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


def reembedder(tenant: str, *, limite: int = 500, taille_lot: int = 16) -> dict:
    """Re-embedde les chunks absents ou produits par un autre modèle/dimension.

    Le modèle et la dimension courants viennent du provider configuré. Aucun mélange
    silencieux : un chunk d'un autre modèle est ré-embeddé, jamais comparé tel quel.
    """
    etat = embeddings.statut()
    if not etat.get("semantique"):
        return {"ok": False, "erreur": "aucun provider d'embeddings actif",
                "modele": etat.get("modele"), "dimension": etat.get("dimension")}
    modele, dimension = etat.get("modele"), int(etat.get("dimension") or 0)
    conn = _connexion()
    if conn is None:
        return {"ok": False, "erreur": "Postgres indisponible", "modele": modele,
                "dimension": dimension, "reembedes": 0}
    reembedes = 0
    try:
        with rls.contexte_tenant(conn, tenant):
            lignes = conn.execute(
                "SELECT id, texte FROM document_chunk WHERE tenant_id = %s "
                "AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %s "
                "OR embedding_dim IS DISTINCT FROM %s) "
                "ORDER BY updated_at LIMIT %s",
                (tenant, modele, dimension, max(0, limite)),
            ).fetchall()
        for debut in range(0, len(lignes), max(1, taille_lot)):
            lot = lignes[debut:debut + max(1, taille_lot)]
            vecteurs = embeddings.embed([str(ligne[1] or "") for ligne in lot])
            if len(vecteurs) != len(lot):
                return {"ok": False, "erreur": "le provider n'a pas rendu un vecteur par chunk",
                        "modele": modele, "dimension": dimension, "reembedes": reembedes}
            with rls.contexte_tenant(conn, tenant):
                for ligne, vecteur in zip(lot, vecteurs):
                    conn.execute(
                        "UPDATE document_chunk SET embedding = %s, embedding_model = %s, "
                        "embedding_dim = %s, updated_at = now() WHERE id = %s AND tenant_id = %s",
                        (vecteur, modele, len(vecteur), ligne[0], tenant))
                    reembedes += 1
        return {"ok": True, "modele": modele, "dimension": dimension,
                "reembedes": reembedes, "restants": max(0, len(lignes) - reembedes)}
    except embeddings.EmbeddingIndisponible as exc:
        return {"ok": False, "erreur": str(exc), "modele": modele,
                "dimension": dimension, "reembedes": reembedes}
    except Exception as exc:
        return {"ok": False, "erreur": type(exc).__name__, "modele": modele,
                "dimension": dimension, "reembedes": reembedes}
    finally:
        conn.close()


def chercher(tenant: str, question: str, *, twin_ids=(), limite: int = 6,
             proximite: dict | None = None, acteur: str = "", role: str = "",
             espace: str = "") -> list[dict]:
    """Classe les chunks du tenant ; une panne de Postgres rend une liste vide, jamais une erreur de chat."""
    conn = _connexion()
    if conn is None:
        return []
    try:
        with rls.contexte_tenant(conn, tenant):
          rows = conn.execute(
              "SELECT id, source_id, twin_id, document_ref, version, ordinal, section, titre, texte, "
              "locator, acl, embedding, embedding_model, embedding_dim, updated_at FROM document_chunk "
              "WHERE tenant_id = %s ORDER BY updated_at DESC LIMIT 400", (tenant,)
          ).fetchall()
    except Exception as exc:
        journal.warning("recherche documentaire échouée (%s)", type(exc).__name__)
        return []
    finally:
        conn.close()
    colonnes = ("id", "source_id", "twin_id", "document_ref", "version", "ordinal", "section",
                "titre", "texte", "locator", "acl", "embedding", "embedding_model", "embedding_dim", "updated_at")
    chunks = [dict(zip(colonnes, row)) for row in rows]
    chunks = [chunk for chunk in chunks
              if _acl_autorise(chunk.get("acl"), acteur=acteur, role=role, espace=espace)]
    if not chunks:
        return []
    try:
        vecteur = embeddings.embed([question])[0]
    except embeddings.EmbeddingIndisponible:
        vecteur = None
    for chunk in chunks:
        chunk["twin_ids_actifs"] = list(twin_ids or ())
        chunk["score"] = retrieval_hybride.score(
            question, chunk, vecteur_question=vecteur, proximite=proximite)
    chunks.sort(key=lambda c: c["score"], reverse=True)
    chunks = [chunk for chunk in chunks if chunk["score"] > 0]
    return reranking.rerank(question, chunks, top_n=limite)[:limite]
