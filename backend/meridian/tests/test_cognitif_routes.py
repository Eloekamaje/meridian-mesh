"""Injection du runtime d'analyse dans la route cognitive, sans Postgres réel."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import cognitif


class RuntimeFactice:
    pass


def _client():
    app = FastAPI()
    app.include_router(cognitif.router, prefix="/api")
    return TestClient(app)


def test_analyser_injecte_le_runtime_du_bord(monkeypatch):
    runtime = RuntimeFactice()
    vus = {}

    async def executer(**kwargs):
        vus.update(kwargs)
        return {"tenant": kwargs["tenant"], "question": kwargs["payload"].question}

    monkeypatch.setattr(cognitif, "_runtime_analyse", lambda: runtime)
    monkeypatch.setattr(cognitif.analyse_service, "executer", executer)

    r = _client().post("/api/boucle/analyser", json={"question": "impact ?"},
                       headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert vus["runtime"] is runtime
    assert vus["tenant"] == "banque"


def test_analyser_traduit_la_configuration_manquante_en_503(monkeypatch):
    async def executer(**kwargs):
        raise cognitif.ConfigurationManquante("JUMEAU_PG_DSN non défini")

    monkeypatch.setattr(cognitif, "_runtime_analyse", RuntimeFactice)
    monkeypatch.setattr(cognitif.analyse_service, "executer", executer)

    r = _client().post("/api/boucle/analyser", json={"question": "impact ?"},
                       headers={"X-Tenant": "banque"})

    assert r.status_code == 503
