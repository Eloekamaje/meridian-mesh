"""Mise à jour de la branche suivie : validation, isolation tenant et run forcé, sans toucher au dépôt."""
import os

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jumeau import ingestion_runtime as runtime
from jumeau.source_routes import construire_router
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg

TENANT = "banque"
AUTRE = "autre"
ENTETES = {"X-Tenant": TENANT}


def _source(conn, *, tenant=TENANT, emplacement="/depots/tbt"):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        ("tbt", tenant, "TBT", "equipe-tbt"))
    return conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, 'tbt', 'GIT', %s, %s) RETURNING id",
        (tenant, f"tbt-repo-{tenant}", emplacement)).fetchone()[0]


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


def _runs(conn, source_id):
    return conn.execute("SELECT count(*) FROM ingestion_run WHERE source_id = %s",
                        (source_id,)).fetchone()[0]


def test_patch_branche_met_a_jour_et_enfile_un_run_force(conn, tmp_path):
    emplacement = tmp_path / "depot-absent"
    source_id = _source(conn, emplacement=str(emplacement))
    runtime.planifier_source(conn, source_id, 3600, TENANT)
    conn.execute("UPDATE source_schedule SET next_run_at = now() + interval '1 day' WHERE source_id = %s",
                 (source_id,))

    reponse = _client(conn).patch(f"/api/boucle/sources/{source_id}/branche",
                                  headers=ENTETES, json={"branche": "feature/api-v2"})

    assert reponse.status_code == 202, reponse.text
    corps = reponse.json()
    assert corps["source_id"] == source_id and corps["tenant"] == TENANT
    assert corps["branche"] == "feature/api-v2"
    assert corps["etat"] == "QUEUED" and corps["cree"] is True
    assert conn.execute("SELECT branche FROM source WHERE id = %s", (source_id,)).fetchone()[0] == "feature/api-v2"
    assert _runs(conn, source_id) == 1
    assert not emplacement.exists()


@pytest.mark.parametrize("branche", ["-main", "feature api", "", "a..b", "/main", "main/", "main.lock"])
def test_une_branche_invalide_est_refusee_sans_run(conn, branche):
    source_id = _source(conn)
    reponse = _client(conn).patch(f"/api/boucle/sources/{source_id}/branche",
                                  headers=ENTETES, json={"branche": branche})
    assert reponse.status_code == 400, reponse.text
    assert conn.execute("SELECT branche FROM source WHERE id = %s", (source_id,)).fetchone()[0] is None
    assert _runs(conn, source_id) == 0


def test_une_source_inconnue_rend_404(conn):
    reponse = _client(conn).patch("/api/boucle/sources/999999/branche",
                                  headers=ENTETES, json={"branche": "develop"})
    assert reponse.status_code == 404


def test_isolation_tenant_aucune_mise_a_jour_ni_run(conn):
    source_id = _source(conn)
    reponse = _client(conn).patch(f"/api/boucle/sources/{source_id}/branche",
                                  headers={"X-Tenant": AUTRE}, json={"branche": "develop"})
    assert reponse.status_code == 404
    assert conn.execute("SELECT branche FROM source WHERE id = %s", (source_id,)).fetchone()[0] is None
    assert _runs(conn, source_id) == 0
