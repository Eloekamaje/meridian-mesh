"""Injection du runtime d'analyse dans la route cognitive, sans Postgres réel."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import cognitif
from meridian.domain import naissance_relationnelle as domaine


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


def test_lister_les_relations_utilise_le_tenant(monkeypatch):
    vus = {}

    async def avec(tenant, action):
        vus["tenant"] = tenant
        return [{"id": "relation-1", "state": "supposee"}]

    monkeypatch.setattr(cognitif, "_avec_connexion", avec)
    r = _client().get("/api/boucle/relations", headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert vus["tenant"] == "banque"
    assert r.json()["propositions"][0]["id"] == "relation-1"


def test_revue_d_une_relation_retourne_l_etat(monkeypatch):
    proposition = domaine.PropositionRelation(
        tenant_id="banque", consumer_id="a", provider_id="b", object="GET /articles",
        consumer_owner="alice", provider_owner="bob", state="confirmee")

    async def avec(tenant, action):
        return proposition

    monkeypatch.setattr(cognitif, "_avec_connexion", avec)
    r = _client().post("/api/boucle/relations/relation-1/revue",
                       json={"decision": "confirmer"}, headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert r.json()["relation"]["state"] == "confirmee"


def test_lister_les_resolutions_utilise_le_tenant(monkeypatch):
    vus = {}

    async def avec(tenant, action):
        vus["tenant"] = tenant
        return [{"id": "resolution-1", "status": "open"}]

    monkeypatch.setattr(cognitif, "_avec_connexion", avec)
    r = _client().get("/api/boucle/resolutions", headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert vus["tenant"] == "banque"
    assert r.json()["resolutions"][0]["id"] == "resolution-1"


def test_resoudre_une_resolution_retourne_l_etat(monkeypatch):
    async def avec(tenant, action):
        return {"id": "resolution-1", "status": "resolved", "evidence_ids": ["export:1"]}

    monkeypatch.setattr(cognitif, "_avec_connexion", avec)
    r = _client().post("/api/boucle/resolutions/resolution-1/resoudre",
                       json={"evidence_ids": ["export:1"]}, headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert r.json()["resolution"]["status"] == "resolved"


def test_enqueter_une_resolution_utilise_la_boucle(monkeypatch):
    vus = {}

    def enqueter(conn, tenant, case_id):
        vus.update({"tenant": tenant, "case_id": case_id})
        return {
            "case": {"id": case_id, "status": "open", "attempts": 1},
            "investigation": {"arret": "sources épuisées", "candidats": []},
        }

    async def avec(tenant, action):
        vus["tenant"] = tenant
        return action(None)

    monkeypatch.setattr(cognitif, "_avec_connexion", avec)
    monkeypatch.setattr(cognitif.investigation_liens_pg, "enqueter_case", enqueter)

    r = _client().post("/api/boucle/resolutions/resolution-1/enqueter",
                       headers={"X-Tenant": "banque"})

    assert r.status_code == 200, r.text
    assert vus == {"tenant": "banque", "case_id": "resolution-1"}
    assert r.json()["investigation"]["arret"] == "sources épuisées"
