"""Lecture des sources documentaires d'un tenant pour le chat."""
from __future__ import annotations

import asyncio
import hashlib
import os

from meridian.application import chunking
from meridian.application import documentation as application
from meridian.adapters.outbound.connectors import confluence  # noqa: F401  (enregistre la fabrique)
from meridian.adapters.outbound.connectors import sharepoint  # noqa: F401  (enregistre la fabrique)
from meridian.adapters.outbound.connectors import lecteurs
from meridian.adapters.outbound.neo4j import graph_store
from meridian.adapters.outbound.postgres import chunk_store
from meridian.adapters.outbound.postgres import rls


def _sources(tenant: str) -> list[dict]:
    import psycopg

    dsn = os.getenv("JUMEAU_PG_DSN")
    if not dsn:
        return []
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        with rls.contexte_tenant(conn, tenant):
            rows = conn.execute(
                "SELECT id, type, nom, emplacement, url, secret_ref, configuration, jumeau_id "
            "FROM source WHERE tenant_id = %s AND type IN ('CONFLUENCE', 'SHAREPOINT')",
            (tenant,),
        ).fetchall()
    colonnes = ("id", "type", "nom", "emplacement", "url", "secret_ref", "configuration", "jumeau_id")
    return [dict(zip(colonnes, row)) for row in rows]


def _indexer(tenant: str, documents: list[dict]) -> None:
    for doc in documents:
        if not doc.get("source_id") or not doc.get("lignes"):
            continue
        chunks = chunking.decouper(doc["lignes"])
        for chunk in chunks:
            chunk["locator"] = lecteurs.locator(
                doc.get("systeme") or "", doc.get("espace") or "", doc.get("ref") or "",
                doc.get("version") or "", chunk["debut"], chunk["fin"])
            chunk["texte_hash"] = hashlib.sha256(chunk["texte"].encode()).hexdigest()[:24]
        chunk_store.indexer(
            tenant, doc["source_id"], doc.get("twin_id") or "", doc.get("ref") or "",
            doc.get("version") or "", doc.get("titre") or "", chunks,
            acl=doc.get("acl") if isinstance(doc.get("acl"), dict) else {})


def indexer_source(tenant: str, source: dict, *, limite: int = 500) -> int:
    """Indexe tout le contenu énumérable d'une source (backfill explicite)."""
    total = 0
    for reader in lecteurs.lecteurs_de([source]):
        try:
            references = reader.parcourir(limite=limite)
        except Exception:
            continue
        for ref in references:
            try:
                doc = reader.lire(ref, 1, 500)
            except Exception:
                continue
            document = {
                "source_id": source.get("id"), "twin_id": source.get("jumeau_id") or "",
                "systeme": reader.systeme, "espace": reader.espace, "ref": str(ref),
                "version": doc.get("version") or "", "titre": doc.get("titre") or "",
                "lignes": doc.get("lignes") or [], "acl": getattr(reader, "acl", None),
            }
            _indexer(tenant, [document])
            total += 1
    return total


def _proximite(tenant: str, twin_ids) -> dict[str, float]:
    if not twin_ids:
        return {}
    contexte = None
    try:
        contexte = graph_store.ouvrir()
        scores = {}
        for twin_id in list(twin_ids)[:10]:
            for voisin in contexte["store"].voisins(tenant, str(twin_id), profondeur=2, sens="les_deux"):
                identifiant = str(voisin.get("id") or "")
                if identifiant:
                    scores[identifiant] = max(
                        scores.get(identifiant, 0.0),
                        1.0 / (1.0 + max(1, int(voisin.get("profondeur") or 1))))
        return scores
    except Exception:
        return {}
    finally:
        if contexte is not None:
            contexte["fermer"]()


def _chercher(tenant: str, question: str, limite: int, twin_ids=(), *,
              acteur: str = "", role: str = "", espace: str = "") -> list[dict]:
    if os.getenv("ACL_SYNC", "manual").strip().lower() == "on_search":
        synchroniser_acl(tenant)
    sources = _sources(tenant)
    documents = []
    if sources:
        documents = application.collecter(lecteurs.lecteurs_de(sources), question, limite=limite)
        documents = [doc for doc in documents
                     if chunk_store._acl_autorise(
                         doc.get("acl"), acteur=acteur, role=role, espace=espace)]
        _indexer(tenant, documents)
    hybrides = chunk_store.chercher(
        tenant, question, twin_ids=tuple(twin_ids or ()), limite=limite,
        acteur=acteur, role=role, espace=espace,
        proximite=_proximite(tenant, twin_ids))
    resultat = []
    vus = set()
    for chunk in hybrides:
        cle = chunk.get("locator") or (chunk.get("texte"), chunk.get("document_ref"))
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append({
            "source": "documentation", "systeme": "",
            "titre": chunk.get("titre") or "", "locator": chunk.get("locator") or "",
            "extrait": str(chunk.get("texte") or "")[:1200], "score": chunk.get("score"),
        })
    for doc in documents:
        cle = doc.get("locator")
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append(doc)
    return resultat[:limite]


def synchroniser_acl(tenant: str, source: dict | None = None) -> int:
    """Applique l'ACL de configuration de la source aux chunks déjà indexés."""
    sources = [source] if source else _sources(tenant)
    total = 0
    for item in sources:
        configuration = item.get("configuration") if isinstance(item.get("configuration"), dict) else {}
        acl = configuration.get("acl") if isinstance(configuration.get("acl"), dict) else {}
        total += chunk_store.mettre_a_jour_acl(tenant, item.get("id"), acl)
    return total


async def indexer_toutes(tenant: str, *, limite: int = 500) -> int:
    return await asyncio.to_thread(
        lambda: sum(indexer_source(tenant, source, limite=limite) for source in _sources(tenant)))


async def chercher(tenant: str, question: str, *, limite: int = 4, twin_ids=(),
                   acteur: str = "", role: str = "", espace: str = "") -> list[dict]:
    try:
        return await asyncio.to_thread(
            _chercher, tenant, question, limite, tuple(twin_ids or ()),
            acteur=acteur, role=role, espace=espace)
    except Exception:
        return []
