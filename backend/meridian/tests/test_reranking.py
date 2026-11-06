"""Reranking : pluggable, désactivé par défaut, jamais une source de vérité."""
from meridian.adapters.outbound import reranking


def test_aucun_reranker_ne_change_l_ordre(monkeypatch):
    monkeypatch.delenv("RERANK_PROVIDER", raising=False)
    chunks = [{"texte": "a"}, {"texte": "b"}]
    assert reranking.rerank("q", chunks) == chunks


def test_bedrock_sans_modele_garde_les_candidats(monkeypatch):
    monkeypatch.setenv("RERANK_PROVIDER", "bedrock")
    monkeypatch.delenv("BEDROCK_RERANK_MODEL", raising=False)
    chunks = [{"texte": "a"}]
    assert reranking.rerank("q", chunks) == chunks
