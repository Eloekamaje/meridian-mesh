"""Le ré-embedding ne mélange jamais les modèles et refuse sans provider."""
from meridian.adapters.outbound import embeddings
from meridian.adapters.outbound.postgres import chunk_store


def test_reembedder_refuse_sans_provider(monkeypatch):
    monkeypatch.setattr(embeddings, "statut", lambda: {
        "semantique": False, "modele": "lexical-only", "dimension": 0,
    })
    resultat = chunk_store.reembedder("demo")
    assert resultat["ok"] is False
    assert "provider" in resultat["erreur"]
