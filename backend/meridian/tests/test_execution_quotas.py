"""Quota de runs actifs par tenant (création refusée en 429)."""
import os

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.outbound.postgres import execution_depot as depot
from meridian.application.execution.modele import CommandeExecution, QuotaDepasse
from meridian.adapters.inbound.http.runs import construire_router
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _commande(cle):
    return CommandeExecution(tenant_id="banque", type="test.echo", idempotency_key=cle,
                             payload={"cle": cle}, acteur="test")


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


def test_quota_depot_refuse_un_nouveau_run_et_accepte_le_rejeu(conn, monkeypatch):
    monkeypatch.setenv("EXECUTION_MAX_ACTIFS_PAR_TENANT", "2")
    premier, _ = depot.creer_run(conn, _commande("q1"))
    depot.creer_run(conn, _commande("q2"))

    with pytest.raises(QuotaDepasse) as refus:
        depot.creer_run(conn, _commande("q3"))
    assert "2/2" in str(refus.value)

    # Le rejeu idempotent du premier run reste accepté même au quota.
    encore, cree = depot.creer_run(conn, _commande("q1"))
    assert cree is False
    assert encore["run_id"] == premier["run_id"]

    depot.demander_annulation(conn, "banque", premier["run_id"])
    troisieme, cree = depot.creer_run(conn, _commande("q3"))
    assert cree is True
    assert troisieme["etat"] == "QUEUED"


def test_quota_route_429_message_clair(conn, monkeypatch):
    monkeypatch.setenv("EXECUTION_MAX_ACTIFS_PAR_TENANT", "1")
    client = _client(conn)
    premier = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "route-q1"},
                          headers={"X-Tenant": "banque"})
    assert premier.status_code == 202, premier.text

    refuse = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "route-q2"},
                         headers={"X-Tenant": "banque"})
    assert refuse.status_code == 429
    assert "quota de runs actifs atteint" in refuse.json()["detail"]

    rejeu = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "route-q1"},
                        headers={"X-Tenant": "banque"})
    assert rejeu.status_code == 200

    client.post(f"/api/runs/{premier.json()['run_id']}/cancel", headers={"X-Tenant": "banque"})
    apres = client.post("/api/runs", json={"type": "test.echo", "idempotency_key": "route-q2"},
                        headers={"X-Tenant": "banque"})
    assert apres.status_code == 202


def test_quota_valeur_invalide_retombe_sur_le_defaut(monkeypatch):
    monkeypatch.setenv("EXECUTION_MAX_ACTIFS_PAR_TENANT", "pas-un-nombre")
    assert depot.max_actifs_par_tenant() == 20
    monkeypatch.setenv("EXECUTION_MAX_ACTIFS_PAR_TENANT", "0")
    assert depot.max_actifs_par_tenant() == 20
