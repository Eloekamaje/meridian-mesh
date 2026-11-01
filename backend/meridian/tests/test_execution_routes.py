import os

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.outbound.postgres import execution_depot as depot
from meridian.application.execution.modele import EtatRun
from meridian.adapters.inbound.http.runs import construire_router
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _client(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                               options=f"-c search_path={schema}")

    app = FastAPI()
    app.include_router(construire_router(
        connect=connecter,
        resoudre_tenant=lambda request, x_tenant: x_tenant or "banque",
    ), prefix="/api")
    return TestClient(app)


def test_creation_202_idempotence_et_lecture(conn):
    client = _client(conn)
    corps = {"type": "test.echo", "payload": {"x": 1}, "idempotency_key": "route-1"}
    r = client.post("/api/runs", json=corps, headers={"X-Tenant": "banque"})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["etat"] == "QUEUED"
    assert run["acteur"] == "demo"
    assert r.headers["location"].endswith(run["run_id"])

    encore = client.post("/api/runs", json=corps, headers={"X-Tenant": "banque"})
    assert encore.status_code == 200
    assert encore.json()["run_id"] == run["run_id"]

    lu = client.get(f"/api/runs/{run['run_id']}", headers={"X-Tenant": "banque"})
    assert lu.status_code == 200
    assert lu.json()["run_id"] == run["run_id"]

    autre = client.get(f"/api/runs/{run['run_id']}", headers={"X-Tenant": "autre"})
    assert autre.status_code == 404


def test_annulation_http(conn):
    client = _client(conn)
    run = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "route-2"},
                      headers={"X-Tenant": "banque"}).json()
    r = client.post(f"/api/runs/{run['run_id']}/cancel", headers={"X-Tenant": "banque"})
    assert r.status_code == 200
    assert r.json()["etat"] == "CANCELLED"



def test_sse_rejoue_le_journal_et_termine(conn):
    client = _client(conn)
    run = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "sse-1"},
                      headers={"X-Tenant": "banque"}).json()
    pris = depot.reclamer_run(conn, "w-test", 30)
    depot.terminer(conn, "banque", run["run_id"], "w-test", int(pris["fencing_token"]),
                   EtatRun.SUCCEEDED, {"ok": True})

    r = client.get(f"/api/runs/{run['run_id']}/events",
                   headers={"X-Tenant": "banque", "Last-Event-ID": "2"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in r.text
    assert "run.succeeded" in r.text
    assert "run.queued" not in r.text


def test_validation_type_payload_et_idempotence(conn):
    client = _client(conn)
    mauvais_type = client.post("/api/runs", json={"type": "Demo.Echo"}, headers={"X-Tenant": "banque"})
    assert mauvais_type.status_code == 422

    cle_vide = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "   "},
                           headers={"X-Tenant": "banque"})
    assert cle_vide.status_code == 400

    gros = client.post("/api/runs", json={"type": "test.echo", "payload": {"x": "a" * (257 * 1024)}},
                       headers={"X-Tenant": "banque"})
    assert gros.status_code == 413

    run = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "cache-1"},
                      headers={"X-Tenant": "banque"})
    assert run.headers["cache-control"] == "no-store"


def test_conflit_idempotence_409(conn):
    client = _client(conn)
    corps = {"type": "test.echo", "payload": {"x": 1}, "idempotency_key": "conflit-route"}
    assert client.post("/api/runs", json=corps, headers={"X-Tenant": "banque"}).status_code == 202
    autre = {"type": "test.echo", "payload": {"x": 2}, "idempotency_key": "conflit-route"}
    r = client.post("/api/runs", json=autre, headers={"X-Tenant": "banque"})
    assert r.status_code == 409


def test_acteur_header_ne_change_pas_acteur(conn):
    client = _client(conn)
    r = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "no-acteur"},
                    headers={"X-Tenant": "banque", "X-Acteur": "support"})
    assert r.status_code == 202
    assert r.json()["acteur"] == "demo"


def test_journal_etapes_et_reprise_http(conn):
    client = _client(conn)
    run = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "steps-1"},
                      headers={"X-Tenant": "banque"}).json()
    pris = depot.reclamer_run(conn, "w-test", 30)
    depot.demarrer_etape(conn, "banque", run["run_id"], "contexte", seq=0)
    depot.terminer_etape(conn, "banque", run["run_id"], "contexte", {"question": "x"})

    etapes = client.get(f"/api/runs/{run['run_id']}/steps", headers={"X-Tenant": "banque"})
    assert etapes.status_code == 200, etapes.text
    assert etapes.json()["etapes"][0]["nom"] == "contexte"
    assert etapes.json()["etapes"][0]["sortie"] == {"question": "x"}

    vivant = client.post(f"/api/runs/{run['run_id']}/resume", headers={"X-Tenant": "banque"})
    assert vivant.status_code == 409

    conn.execute("UPDATE execution_run SET bail_jusqu_a = now() - interval '1 hour' "
                 "WHERE run_id = %s", (run["run_id"],))
    repris = client.post(f"/api/runs/{run['run_id']}/resume", headers={"X-Tenant": "banque"})
    assert repris.status_code == 200, repris.text
    assert repris.json()["etat"] == "QUEUED"

    inconnu = client.post("/api/runs/inconnu/resume", headers={"X-Tenant": "banque"})
    assert inconnu.status_code == 404
    autre = client.get(f"/api/runs/{run['run_id']}/steps", headers={"X-Tenant": "autre"})
    assert autre.status_code == 404


def test_routes_execution_posent_le_contexte_tenant_sous_rls(conn, monkeypatch):
    from contextlib import contextmanager

    from meridian.adapters.inbound.http import runs as routes_execution

    vus = []

    @contextmanager
    def contexte(conn_, tenant):
        vus.append(tenant)
        yield tenant

    monkeypatch.setattr(routes_execution.rls, "est_actif", lambda: True)
    monkeypatch.setattr(routes_execution.rls, "contexte_tenant", contexte)
    client = _client(conn)

    run = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "rls-route"},
                      headers={"X-Tenant": "banque"})
    assert run.status_code == 202, run.text
    lu = client.get(f"/api/runs/{run.json()['run_id']}", headers={"X-Tenant": "banque"})
    assert lu.status_code == 200
    assert vus and set(vus) == {"banque"}
