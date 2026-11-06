"""Adapters Bedrock : embeddings Titan et vision Converse, sans appel AWS réel."""
import json

from meridian.adapters.outbound import bedrock_vision, embeddings


class _Corps:
    def __init__(self, data): self.data = data
    def read(self): return json.dumps(self.data).encode()


class _Client:
    def __init__(self): self.appels = []
    def invoke_model(self, **kwargs):
        self.appels.append(kwargs)
        return {"body": _Corps({"embedding": [0.1, 0.2]})}
    def converse(self, **kwargs):
        self.appels.append(kwargs)
        return {"output": {"message": {"content": [{"text": "OK"}]}}}


def test_bedrock_est_le_provider_par_defaut_en_mode_bedrock(monkeypatch):
    monkeypatch.setenv("JUMEAU_MODELE", "bedrock")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert embeddings.modele().startswith("amazon.titan")


def test_titan_appelle_bedrock_runtime_avec_la_region_canadienne(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_REGION", "ca-central-1")
    client = _Client()
    from meridian.adapters.outbound import bedrock_router
    monkeypatch.setattr(bedrock_router, "client", lambda *a, **k: client)
    vecteurs = embeddings.embed(["un texte"])
    assert vecteurs == [[0.1, 0.2]]
    assert client.appels[0]["modelId"] == "amazon.titan-embed-text-v2:0"


def test_bedrock_vision_utilise_converse(monkeypatch):
    monkeypatch.setenv("BEDROCK_VISION_MODEL", "amazon.nova-pro-v1:0")
    client = _Client()
    from meridian.adapters.outbound import bedrock_router
    monkeypatch.setattr(bedrock_router, "client", lambda *a, **k: client)
    assert bedrock_vision.decrire(b"png", "image/png", "Décris") == "OK"
    assert client.appels[0]["modelId"] == "amazon.nova-pro-v1:0"
