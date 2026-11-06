"""Indexation et recherche de chunks : embeddings, ACL JSONB et classement hybride."""
from __future__ import annotations

import os
import psycopg
import pytest

from meridian.adapters.outbound import embeddings
from meridian.adapters.outbound.postgres import chunk_store

pytestmark = pytest.mark.skipif(
    not os.environ.get("JUMEAU_PG_DSN"), reason="Postgres requis")


def _connexion_test(conn):
    schema = conn.execute("SELECT current_schema()").fetchone()[0]

    def ouvrir():
        c = psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True)
        c.execute(f"SET search_path TO {schema}")
        return c

    return ouvrir


def test_indexer_et_chercher_avec_embedding(conn, monkeypatch):
    monkeypatch.setattr(chunk_store, "_connexion", _connexion_test(conn))
    monkeypatch.setattr(embeddings, "embed", lambda textes: [[1.0, 0.0] for _ in textes])
    tenant = "test-chunk"
    chunks = [
        {"ordinal": 0, "section": "Sécurité",
         "texte": "Les mots de passe sont hachés avec bcrypt.",
         "locator": "doc://1#L1-L1", "texte_hash": "h1"},
        {"ordinal": 1, "section": "Architecture",
         "texte": "FastAPI et PostgreSQL composent le socle.",
         "locator": "doc://1#L2-L2", "texte_hash": "h2"},
    ]
    assert chunk_store.indexer(tenant, None, "conduit", "doc-1", "v1", "Conduit", chunks) == 2
    resultats = chunk_store.chercher(tenant, "protéger les mots de passe", limite=2)
    assert resultats
    assert resultats[0]["section"] == "Sécurité"
    assert resultats[0]["embedding_model"] == embeddings.modele()
    assert resultats[0]["embedding_dim"] == 2


def test_mettre_a_jour_acl_avec_jsonb(conn, monkeypatch):
    monkeypatch.setattr(chunk_store, "_connexion", _connexion_test(conn))
    monkeypatch.setattr(embeddings, "embed", lambda textes: [[1.0, 0.0] for _ in textes])
    tenant = "test-chunk-acl"
    chunk_store.indexer(tenant, None, "conduit", "doc-1", "v1", "Conduit", [
        {"ordinal": 0, "section": "", "texte": "Un texte.", "locator": "doc://1#L1-L1",
         "texte_hash": "h1"},
    ], acl={"roles": ["Architecte"]})
    assert chunk_store.mettre_a_jour_acl(tenant, None, {"public": True}) == 1
    resultats = chunk_store.chercher(tenant, "texte", limite=1)
    assert resultats and resultats[0]["acl"].get("public") is True
