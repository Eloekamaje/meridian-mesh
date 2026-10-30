"""Identité : demo explicite, proxy de confiance et OIDC HS256 ; le header client ne gagne jamais."""
import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from jose import jwt

import auth


def _client():
    app = FastAPI()

    @app.get("/api/qui")
    def qui(x_persona: str = Header("architecte")):
        return {"persona": x_persona}

    auth.installer(app)
    return TestClient(app)


def test_demo_accepte_les_personas_connues_et_refuse_les_autres(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    client = _client()
    assert client.get("/api/qui").json() == {"persona": "architecte"}
    assert client.get("/api/qui", headers={"X-Persona": "support"}).json() == {"persona": "support"}
    assert client.get("/api/qui", headers={"X-Persona": "intrus"}).status_code == 401


def test_proxy_exige_le_secret_et_ignore_le_header_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "proxy")
    monkeypatch.setenv("AUTH_PROXY_SECRET", "secret-proxy")
    monkeypatch.setenv("AUTH_PERSONA_MAP", '{"grp-arch": "architecte"}')
    client = _client()
    entetes = {"X-Auth-Proxy-Secret": "secret-proxy", "X-Auth-Request-Groups": "grp-arch", "X-Persona": "support"}
    assert client.get("/api/qui", headers=entetes).json() == {"persona": "architecte"}
    assert client.get("/api/qui", headers={**entetes, "X-Auth-Proxy-Secret": "faux"}).status_code == 401


def test_oidc_verifie_la_signature_et_la_persona(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("AUTH_OIDC_SECRET", "secret-oidc")
    monkeypatch.setenv("AUTH_AUDIENCE", "meridian")
    monkeypatch.setenv("AUTH_ISSUER", "idp-test")
    jeton = jwt.encode({"sub": "u1", "name": "Alice", "persona": "support", "aud": "meridian", "iss": "idp-test"},
                       "secret-oidc", algorithm="HS256")
    client = _client()
    assert client.get("/api/qui", headers={"Authorization": f"Bearer {jeton}", "X-Persona": "architecte"}).json() == {"persona": "support"}
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
