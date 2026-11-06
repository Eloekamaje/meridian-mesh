"""Pas de vecteur factice en production : sans provider, le retrieval reste lexical."""
import pytest

from meridian.adapters.outbound import embeddings


def test_sans_provider_aucun_vecteur_n_est_invente(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    with pytest.raises(embeddings.EmbeddingIndisponible):
        embeddings.embed(["un texte"])
    assert embeddings.modele() == "lexical-only"
