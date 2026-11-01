"""Identité : demo explicite, proxy de confiance et OIDC HS256 ; le client ne choisit jamais l'acteur."""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt

import auth


def _client():
    app = FastAPI()

    @app.get("/api/qui")
    def qui(request: Request):
        return {"acteur": request.state.acteur}

    auth.installer(app)
    return TestClient(app)


def test_demo_utilise_l_acteur_demo_et_ignore_l_en_tete_client(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    client = _client()
    assert client.get("/api/qui").json() == {"acteur": "demo"}
    assert client.get("/api/qui", headers={}).json() == {"acteur": "demo"}


def test_proxy_exige_le_secret_et_prend_l_utilisateur_authentifie(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy")
    monkeypatch.setenv("AUTH_PROXY_SECRET", "secret-proxy")
    client = _client()
    entetes = {"X-Auth-Proxy-Secret": "secret-proxy", "X-Auth-Request-User": "alice",
               "X-Auth-Request-Tenant": "banque"}
    assert client.get("/api/qui", headers=entetes).json() == {"acteur": "alice"}
    assert client.get("/api/qui", headers={**entetes, "X-Auth-Proxy-Secret": "faux"}).status_code == 401
    assert client.get("/api/qui", headers={"X-Auth-Proxy-Secret": "secret-proxy"}).status_code == 403


def test_oidc_verifie_la_signature_et_prend_l_identite_du_jeton(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_OIDC_SECRET", "secret-oidc")
    monkeypatch.setenv("AUTH_AUDIENCE", "meridian")
    monkeypatch.setenv("AUTH_ISSUER", "idp-test")
    jeton = jwt.encode({"sub": "u1", "name": "Alice", "tenant": "banque",
                        "aud": "meridian", "iss": "idp-test"}, "secret-oidc", algorithm="HS256")
    client = _client()
    assert client.get("/api/qui", headers={"Authorization": f"Bearer {jeton}"}).json() == {"acteur": "Alice"}
    assert client.get("/api/qui", headers={"Authorization": "Bearer invalide"}).status_code == 401


def test_verifier_config_refuse_un_mode_ou_un_secret_manquant(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy")
    monkeypatch.delenv("AUTH_PROXY_SECRET", raising=False)
    try:
        auth.verifier_config()
    except RuntimeError as erreur:
        assert "AUTH_PROXY_SECRET" in str(erreur)
    else:
        raise AssertionError("configuration proxy sans secret acceptée")


def test_demo_refuse_en_production(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="demo"):
        auth.verifier_config()


def _client_tenant():
    app = FastAPI()

    @app.get("/api/tenant")
    def tenant(request: Request):
        return {"tenant": getattr(request.state, "tenant", None)}

    auth.installer(app)
    return TestClient(app)


def test_proxy_extrait_le_tenant_de_confiance(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy")
    monkeypatch.setenv("AUTH_PROXY_SECRET", "secret-proxy")
    client = _client_tenant()
    entetes = {"X-Auth-Proxy-Secret": "secret-proxy", "X-Auth-Request-Tenant": "Banque",
               "X-Auth-Request-User": "alice"}

    assert client.get("/api/tenant", headers=entetes).json() == {"tenant": "banque"}
    assert client.get("/api/tenant", headers={**entetes, "X-Auth-Request-Tenant": "Banque Client"}).status_code == 403


def test_oidc_extrait_le_tenant_du_jeton_et_refuse_le_conflit(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_OIDC_SECRET", "secret-oidc")
    jeton = jwt.encode({"sub": "u1", "tenant": "banque", "name": "Alice"}, "secret-oidc", algorithm="HS256")
    client = _client_tenant()
    entetes = {"Authorization": f"Bearer {jeton}"}

    assert client.get("/api/tenant", headers=entetes).json() == {"tenant": "banque"}
    assert client.get("/api/tenant", headers={**entetes, "X-Tenant": "assurance"}).status_code == 403
    assert client.get("/api/tenant", headers={**entetes, "X-Tenant": "banque"}).json() == {"tenant": "banque"}


def test_oidc_sans_claim_tenant_est_refuse(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_OIDC_SECRET", "secret-oidc")
    jeton = jwt.encode({"sub": "u1", "name": "Alice"}, "secret-oidc", algorithm="HS256")
    client = _client_tenant()

    assert client.get("/api/tenant", headers={"Authorization": f"Bearer {jeton}"}).status_code == 403
