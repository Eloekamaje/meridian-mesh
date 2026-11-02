"""API générique de pilotage : sources, synchro, capacité, prévision, rôles."""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from meridian.adapters.inbound.http import planification as http
from meridian.tests.conftest import DSN, besoin_pg

pytestmark = besoin_pg


@pytest.fixture
def api(monkeypatch, tmp_path):
    import psycopg
    schema = f"test_plan_api_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    dsn = make_conninfo(DSN, options=f"-c search_path={schema}")
    csv = tmp_path / "travail.csv"
    csv.write_text(
        "external_id,titre,equipe_id,equipe_nom,type,statut,priorite,estimation,unite,"
        "cycle_id,cycle_nom,cycle_debut,cycle_fin,cycle_termine,maj_source\n"
        "A-1,Premier,A,Équipe A,story,a_faire,haute,3,points,S1,Sprint 1,2026-01-01,2026-01-14,true,2026-01-10\n",
        encoding="utf-8")
    monkeypatch.setenv("JUMEAU_PG_DSN", dsn)
    monkeypatch.setenv("AUTH_MODE", "demo")
    http._SCHEMA_PRET = False
    app = FastAPI()
    app.include_router(http.construire_router())
    with TestClient(app) as client:
        yield client, csv
    http._SCHEMA_PRET = False
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


def test_source_sync_et_capacite(api):
    client, csv = api
    entetes = {"X-Tenant": "demo"}
    source = client.post("/planification/sources", headers=entetes, json={
        "id": "csv-api", "provider": "csv", "usage": "travail", "nom": "CSV API",
        "configuration": {"chemin": str(csv)}})
    assert source.status_code == 201, source.text
    sync = client.post("/planification/sources/csv-api/sync", headers=entetes)
    assert sync.status_code == 200, sync.text
    assert sync.json()["ecrits"] == 1
    equipes = client.get("/planification/equipes", headers=entetes)
    assert equipes.status_code == 200
    assert equipes.json()["equipes"][0]["id"] == "A"
    capacite = client.get("/planification/capacite?equipe_id=A", headers=entetes)
    assert capacite.status_code == 200
    charge = capacite.json()["equipes"][0]["charges"][0]
    assert charge["total"] == 3 and charge["capacite"] is None
    alertes = client.get("/planification/alertes", headers=entetes)
    assert alertes.status_code == 200
    assert any(a["type"] == "non_estime" for a in alertes.json()["alertes"]) is False


def test_prevision_explicite_et_role(api):
    client, _ = api
    entetes = {"X-Tenant": "demo"}
    r = client.post("/planification/previsions", headers=entetes, json={
        "restant_points": 20, "historique_velocite": [5, 6, 7], "duree_cycle_jours": 14,
        "seed": 3, "simulations": 300})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True and data["p50"] <= data["p85"] <= data["p95"]
    role = client.post("/planification/roles", headers=entetes, json={
        "acteur": "alice", "role": "scrum_master", "perimetre_type": "equipe", "perimetre_id": "A"})
    assert role.status_code == 201, role.text
    assert client.get("/planification/roles", headers=entetes).status_code == 200


def test_plan_et_scenario_sont_generiques(api):
    client, _ = api
    entetes = {"X-Tenant": "demo"}
    plan = client.post("/planification/plans", headers=entetes, json={
        "nom": "Plan trimestre", "equipe_id": "A", "horizon": "2026-Q1",
        "hypotheses": ["capacité constante"],
        "lignes": [{"element_id": "A:1", "equipe_id": "A", "valeur": 3, "unite": "points"}]})
    assert plan.status_code == 201, plan.text
    scenario = client.post("/planification/scenarios", headers=entetes, json={
        "base": {"restant_points": 20, "historique_velocite": [5, 6, 7],
                 "duree_cycle_jours": 14, "seed": 2, "simulations": 300},
        "scenarios": [{"nom": "+20 %", "capacite_delta_pct": 20}]})
    assert scenario.status_code == 200, scenario.text
    assert scenario.json()["reference"]["ok"] is True


def test_webhook_hmac_et_deduplication(api, monkeypatch):
    import hashlib
    import hmac
    client, csv = api
    monkeypatch.setenv("MERIDIAN_TEST_WEBHOOK", "secret-webhook")
    entetes = {"X-Tenant": "demo"}
    source = client.post("/planification/sources", headers=entetes, json={
        "id": "csv-webhook", "provider": "csv", "usage": "travail", "nom": "CSV webhook",
        "configuration": {"chemin": str(csv), "webhook_secret_ref": "env:MERIDIAN_TEST_WEBHOOK"}})
    assert source.status_code == 201, source.text
    corps = b'{"event":"updated"}'
    signature = hmac.new(b"secret-webhook", corps, hashlib.sha256).hexdigest()
    entetes_webhook = {**entetes, "X-Planification-Secret": "secret-webhook",
                       "X-Planification-Delivery": "evt-1"}
    premier = client.post("/planification/webhooks/csv-webhook", headers=entetes_webhook, content=corps)
    assert premier.status_code == 202, premier.text
    assert premier.json()["queued"] is True
    second = client.post("/planification/webhooks/csv-webhook", headers=entetes_webhook, content=corps)
    assert second.status_code == 202 and second.json()["duplicate"] is True
    invalide = client.post("/planification/webhooks/csv-webhook", headers={
        **entetes, "X-Planification-Secret": "faux", "X-Planification-Delivery": "evt-2"}, content=corps)
    assert invalide.status_code == 401


def test_artefact_persiste_et_se_recharge(api):
    client, _ = api
    entetes = {"X-Tenant": "demo"}
    artefact = {
        "type": "planification.capacite", "titre": "Capacité", "version": "1.0",
        "source": "test", "equipes": [],
    }
    cree = client.post("/planification/artefacts", headers=entetes, json=artefact)
    assert cree.status_code == 201, cree.text
    identifiant = cree.json()["artefact_id"]
    relu = client.get(f"/planification/artefacts/{identifiant}", headers=entetes)
    assert relu.status_code == 200
    assert relu.json()["titre"] == "Capacité"
    assert relu.json()["type"] == "planification.capacite"


def test_artefact_svg_compile_est_accepte(api):
    client, _ = api
    entetes = {"X-Tenant": "demo"}
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
    cree = client.post("/planification/artefacts", headers=entetes, json={
        "type": "svg", "titre": "Diagramme", "version": "1.0", "source": "design-diagram",
        "svg": svg})
    assert cree.status_code == 201, cree.text
    assert cree.json()["type"] == "svg"


def test_compilation_design_diagram_sans_opencode(api):
    from pathlib import Path
    client, _ = api
    racine = Path(__file__).resolve().parents[3]
    html = (racine / "docs/diagrammes/architecture.html").read_text(encoding="utf-8")
    r = client.post("/planification/artefacts/compiler", headers={"X-Tenant": "demo"},
                    json={"html": html, "titre": "Architecture compilée"})
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "svg"
    assert r.json()["svg"].startswith("<?xml")
