import pytest

from meridian.adapters.outbound.connectors import auth_source


def test_pat_utilise_la_reference_vault(monkeypatch):
    monkeypatch.setattr("meridian.adapters.outbound.connectors.naissance.resoudre_secret", lambda reference: f"token:{reference}")
    source = auth_source.depuis_config({"auth_mode": "pat", "secret_ref": "vault:meridian/git#jeton"})
    assert source.mode == auth_source.AUTH_PAT
    assert source.token() == "token:vault:meridian/git#jeton"


def test_configuration_persistee_ne_contient_jamais_le_secret(monkeypatch):
    config = auth_source.configuration_pour_source({
        "auth_mode": "pat", "url": "https://github.com/acme/repo",
        "secret": "ne-doit-pas-sortir",
    })
    assert config["auth_mode"] == "pat"
    assert "secret" not in config


def test_mode_inconnu_refuse():
    with pytest.raises(auth_source.AuthSourceInvalide):
        auth_source.depuis_config({"auth_mode": "magique"})
