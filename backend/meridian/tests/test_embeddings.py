"""Pas de vecteur factice en production : sans provider, le retrieval reste lexical."""
import pytest

from meridian.adapters.outbound import embeddings


def test_sans_provider_aucun_vecteur_n_est_invente(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    with pytest.raises(embeddings.EmbeddingIndisponible):
        embeddings.embed(["un texte"])
    assert embeddings.modele() == "lexical-only"
    assert embeddings.statut()["semantique"] is False


def test_statut_bedrock_est_expose_sans_secret(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "ca-central-1")
    monkeypatch.setenv("BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
    monkeypatch.setenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024")
    from meridian.adapters.outbound import bedrock_router

    class _Session:
        def get_credentials(self):
            return object()

    monkeypatch.setattr(bedrock_router, "session", lambda: _Session())
    statut = embeddings.statut()
    assert statut["semantique"] is True
    assert statut["dimension"] == 1024
    assert "ca-central-1" in statut["detail"]
