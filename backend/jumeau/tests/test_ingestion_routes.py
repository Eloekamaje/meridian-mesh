"""API de l'alimentation pull-first : 202 + run id, pause/reprise, journal et santé sans secret."""
import os

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jumeau import ingestion_runtime as runtime
from jumeau.source_routes import construire_router
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg

TENANT = "banque"
AUTRE = "autre"
ENTETES = {"X-Tenant": TENANT}


def _source(conn, *, nom="tbt-repo", tenant=TENANT, jumeau="tbt",
            emplacement="/depots/tbt"):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        (jumeau, tenant, jumeau.upper(), "equipe-" + jumeau))
    return conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, %s, 'GIT', %s, %s) RETURNING id",
        (tenant, jumeau, nom, emplacement)).fetchone()[0]


def _client(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                               options=f"-c search_path={schema}")

    app = FastAPI()
    app.include_router(construire_router(
        connect=connecter,
        resoudre_tenant=lambda request, x_tenant: x_tenant or TENANT,
    ), prefix="/api")
    return TestClient(app)


def test_ingestion_manuelle_rend_202_et_un_run_unique(conn):
    source_id = _source(conn)
    client = _client(conn)

    premier = client.post(f"/api/boucle/sources/{source_id}/ingest", headers=ENTETES)
    assert premier.status_code == 202, premier.text
    corps = premier.json()
    assert corps["source_id"] == source_id and corps["tenant"] == TENANT
    assert corps["cree"] is True and corps["etat"] == "QUEUED"
    assert premier.headers["location"].endswith(f"/{source_id}/runs")

    encore = client.post(f"/api/boucle/sources/{source_id}/ingest", headers=ENTETES)
    assert encore.status_code == 202
    assert encore.json()["run_id"] == corps["run_id"]
    assert encore.json()["cree"] is False

    runs = client.get(f"/api/boucle/sources/{source_id}/runs", headers=ENTETES)
    assert runs.status_code == 200
    assert [run["id"] for run in runs.json()["runs"]] == [corps["run_id"]]
    assert runs.json()["runs"][0]["etat"] == "QUEUED"


def test_pause_et_reprise_via_api(conn):
    source_id = _source(conn)
    client = _client(conn)

    pause = client.post(f"/api/boucle/sources/{source_id}/pause", headers=ENTETES)
    assert pause.status_code == 200
    assert pause.json()["schedule"]["etat"] == "paused"

    sante = client.get("/api/boucle/sources/sante", headers=ENTETES).json()
    assert sante["sources"][0]["etat"] == "paused"
    assert sante["sources"][0]["sante"] == "en_pause"

    reprise = client.post(f"/api/boucle/sources/{source_id}/resume", headers=ENTETES)
    assert reprise.status_code == 200
    assert reprise.json()["schedule"]["etat"] == "active"


def test_isolation_tenant_sur_les_routes(conn):
    source_id = _source(conn)
    client = _client(conn)

    assert client.get(f"/api/boucle/sources/{source_id}/runs",
                      headers={"X-Tenant": AUTRE}).status_code == 404
    assert client.post(f"/api/boucle/sources/{source_id}/pause",
                       headers={"X-Tenant": AUTRE}).status_code == 404
    assert client.post(f"/api/boucle/sources/{source_id}/ingest",
                       headers={"X-Tenant": AUTRE}).status_code == 404
    assert client.get("/api/boucle/sources/sante", headers={"X-Tenant": AUTRE}).json()["sources"] == []


def test_sante_ne_divulgue_ni_url_ni_secret(conn):
    source_id = _source(
        conn, nom="depot-secret",
        emplacement="https://user:secret-token@git.exemple.fr/depot?token=secret-token")
    conn.execute("UPDATE source SET url = %s, secret_ref = %s WHERE id = %s",
                 ("https://user:secret-token@git.exemple.fr/depot", "env:JETON_DEPOT", source_id))
    runtime.planifier_source(conn, source_id, 60, TENANT)
    conn.execute(
        "UPDATE source_schedule SET last_error = %s WHERE source_id = %s",
        ("échec https://user:secret-token@git.exemple.fr/depot token=secret-token", source_id))

    reponse = _client(conn).get("/api/boucle/sources/sante", headers=ENTETES)

    assert reponse.status_code == 200
    assert reponse.json()["tenant"] == TENANT
    for interdit in ("secret-token", "https://", "env:JETON_DEPOT", "/depots/"):
        assert interdit not in reponse.text
