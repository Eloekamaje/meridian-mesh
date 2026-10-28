"""Le serveur impose la référence du jeton d'une source : celle de sa connexion, de son connecteur seulement."""
import os

import pytest

ENV = {"MONGO_URL": "mongodb://127.0.0.1:1", "DB_NAME": "test_proteger_source"}  # client paresseux : pas de connexion
avant = {k: os.environ.get(k) for k in ENV}
os.environ.update({k: v for k, v in ENV.items() if avant[k] is None})
try:
    server = pytest.importorskip("server")
finally:  # ne pas laisser ces variables activer les tests qui dépendent d'un vrai Mongo
    for k, v in avant.items():
        if v is None:
            os.environ.pop(k, None)

CONNEXIONS = {"gh-ana": "vault:gh", "cf-ana": "vault:cf"}


def source(connecteur, connexion, secret="env:MERIDIAN_AUTRE"):
    return {"connecteur": connecteur, "config": {"connexion": connexion, "secret": secret}}


def test_la_reference_vient_de_la_connexion_du_connecteur():
    assert server._proteger_source(source("confluence", "cf-ana"), CONNEXIONS)["config"]["secret"] == "vault:cf"
    assert server._proteger_source(source("github", "gh-ana"), CONNEXIONS)["config"]["secret"] == "vault:gh"


def test_jamais_la_connexion_ou_le_secret_d_un_autre_connecteur():
    assert server._proteger_source(source("confluence", "gh-ana"), CONNEXIONS)["config"]["secret"] == ""
    assert server._proteger_source(source("github", "cf-ana"), CONNEXIONS)["config"]["secret"] == ""
    assert server._proteger_source(source("confluence", None), CONNEXIONS)["config"]["secret"] == ""
