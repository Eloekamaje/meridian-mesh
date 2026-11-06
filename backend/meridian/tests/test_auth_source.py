import pytest

from meridian.adapters.outbound.connectors import auth_source


def test_pat_utilise_la_reference_vault(monkeypatch):
    monkeypatch.setattr("meridian.adapters.outbound.connectors.naissance.resoudre_secret", lambda reference: f"token:{reference}")
    source = auth_source.depuis_config({"auth_mode": "pat", "secret_ref": "vault:meridian/git#jeton"})
    assert source.mode == auth_source.AUTH_PAT
    assert source.token() == "token:vault:meridian/git#jeton"


def test_configuration_persistee_refuse_un_secret_brut(monkeypatch):
    with pytest.raises(auth_source.AuthSourceInvalide):
        auth_source.configuration_pour_source({
            "auth_mode": "pat", "url": "https://github.com/acme/repo",
            "secret": "ne-doit-pas-sortir",
        })


def test_secret_absent_reste_actionnable(monkeypatch):
    from meridian.adapters.outbound.connectors import naissance

    def absent(_reference):
        raise naissance.SecretAbsent("secret absent : redéclarez")

    monkeypatch.setattr(naissance, "resoudre_secret", absent)
    with pytest.raises(naissance.SecretAbsent, match="redéclarez"):
        auth_source.PATSource("vault:meridian/github/gh-x#jeton").token()


def test_reference_aws_arn_acceptee():
    configuration = auth_source.configuration_pour_source({
        "auth_mode": "pat",
        "secret_ref": "aws:arn:aws:secretsmanager:eu-west-1:123456789012:secret:github#jeton",
    })
    assert configuration["secret_ref"].startswith("aws:arn:aws:secretsmanager:")


def test_mode_inconnu_refuse():
    with pytest.raises(auth_source.AuthSourceInvalide):
        auth_source.depuis_config({"auth_mode": "magique"})
