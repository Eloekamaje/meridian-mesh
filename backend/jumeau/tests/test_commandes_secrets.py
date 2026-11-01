"""La commande ne persiste jamais un secret fourni par le client."""
import pytest

server = pytest.importorskip("server")


def test_un_secret_brut_est_retire_de_la_configuration():
    source = server._proteger_source(
        {"connecteur": "postgresql", "config": {"hote": "db.test", "secret": "s3cr3t", "token": "jeton"}},
        {},
    )
    assert source["config"] == {"hote": "db.test"}


def test_une_connexion_declaree_remplace_le_secret_par_sa_reference():
    source = server._proteger_source(
        {"connecteur": "github", "config": {"connexion": "gh-acme", "secret": "s3cr3t"}},
        {"gh-acme": "vault:meridian/github#jeton"},
    )
    assert source["config"]["secret"] == "vault:meridian/github#jeton"
    assert "s3cr3t" not in str(source)
