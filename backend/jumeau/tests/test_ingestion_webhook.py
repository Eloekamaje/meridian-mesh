"""Webhook d'accélération : signature, branche/dépôt, SHA inchangé et enfilement pull-first."""
import hashlib
import hmac
import json
import os

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jumeau.source_routes import construire_router
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg

TENANT = "banque"
SECRET = "secret-webhook"


def _source(conn):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        ("tbt", TENANT, "TBT", "equipe-tbt"))
    source_id = conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, url, branche, curseur) "
        "VALUES (%s, 'tbt', 'GIT', 'tbt-repo', '/depots/tbt', %s, 'main', 'ancien-sha') RETURNING id",
        (TENANT, "https://github.com/acme/tbt.git")).fetchone()[0]
    return source_id


def _client(conn, secret=SECRET):
    schema = conn.execute("SHOW search_path").fetchone()[0]

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                               options=f"-c search_path={schema}")

    app = FastAPI()
    app.include_router(construire_router(
        connect=connecter,
        resoudre_tenant=lambda request, x_tenant: x_tenant or TENANT,
        secret_webhook=secret,
    ), prefix="/api")
    return TestClient(app)


def _post(client, source_id, payload, *, secret=SECRET, event="push"):
    corps = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return client.post(f"/api/boucle/sources/{source_id}/webhook", content=corps,
                       headers={"X-Hub-Signature-256": signature, "X-GitHub-Event": event,
                                "Content-Type": "application/json"})


def _payload(*, ref="refs/heads/main", repo="acme/tbt", after="nouveau-sha"):
    return {"ref": ref, "after": after, "repository": {"full_name": repo}}


def test_un_push_sur_la_bonne_branche_enfile_un_run(conn):
    source_id = _source(conn)
    r = _post(_client(conn), source_id, _payload())
    assert r.status_code == 202, r.text
    corps = r.json()
    assert corps["cree"] is True and corps["etat"] == "QUEUED"
    assert conn.execute("SELECT count(*) FROM ingestion_run WHERE source_id = %s", (source_id,)).fetchone()[0] == 1


def test_une_signature_invalide_est_refusee(conn):
    source_id = _source(conn)
    r = _post(_client(conn), source_id, _payload(), secret="mauvais")
    assert r.status_code == 401
    assert conn.execute("SELECT count(*) FROM ingestion_run WHERE source_id = %s", (source_id,)).fetchone()[0] == 0


def test_une_autre_branche_ou_un_autre_depot_est_ignore(conn):
    source_id = _source(conn)
    client = _client(conn)
    for payload in (_payload(ref="refs/heads/develop"), _payload(repo="acme/autre")):
        r = _post(client, source_id, payload)
        assert r.status_code == 202, r.text
        assert r.json()["ignore"] is True
    assert conn.execute("SELECT count(*) FROM ingestion_run WHERE source_id = %s", (source_id,)).fetchone()[0] == 0


def test_le_sha_deja_ingere_et_le_ping_sont_ignores(conn):
    source_id = _source(conn)
    client = _client(conn)
    r = _post(client, source_id, _payload(after="ancien-sha"))
    assert r.status_code == 202 and r.json()["raison"] == "sha inchangé"
    r = _post(client, source_id, {}, event="ping")
    assert r.status_code == 202 and r.json()["raison"] == "ping"
    assert conn.execute("SELECT count(*) FROM ingestion_run WHERE source_id = %s", (source_id,)).fetchone()[0] == 0


def test_sans_secret_le_webhook_est_indisponible(conn, monkeypatch):
    monkeypatch.delenv("JUMEAU_WEBHOOK_SECRET", raising=False)
    source_id = _source(conn)
    r = _post(_client(conn, secret=""), source_id, _payload())
    assert r.status_code == 503
