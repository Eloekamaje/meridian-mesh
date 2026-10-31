"""Contrat de l'adaptateur HTTP : politique, transport injecté, réponses bornées et secrets absents."""
import json

import pytest
import requests

from jumeau import http_adapter
from jumeau.http_adapter import HTTPInvalide, HTTPRefuse, creer_adaptateur_http


class Reponse:
    """Réponse minimale compatible avec ce que l'adaptateur lit d'une réponse requests."""

    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class FauxTransport:
    """Transport injecté : mémorise les appels et rend la réponse ou l'erreur préparée, sans réseau."""

    def __init__(self):
        self.appels = []
        self.reponse = Reponse()
        self.erreur = None

    def __call__(self, methode, url, **options):
        self.appels.append({"method": methode, "url": url, **options})
        if self.erreur is not None:
            raise self.erreur
        return self.reponse


@pytest.fixture
def transport():
    return FauxTransport()


def test_get_json_reussi_et_options_du_transport(transport):
    transport.reponse = Reponse(
        200, json.dumps({"ok": True}).encode(), {"Content-Type": "application/json; charset=utf-8"})
    adaptateur = creer_adaptateur_http(
        "https://api.exemple.fr/v1", headers={"Accept": "application/json"}, transport=transport)

    resultat = adaptateur(path="/sante?x=1")

    assert resultat == {
        "status": 200,
        "content_type": "application/json; charset=utf-8",
        "body": {"ok": True},
    }
    assert transport.appels == [{
        "method": "GET",
        "url": "https://api.exemple.fr/v1/sante?x=1",
        "headers": {"Accept": "application/json"},
        "timeout": 5.0,
        "allow_redirects": False,
    }]


def test_json_parse_meme_sans_type_json(transport):
    transport.reponse = Reponse(200, b'{"ok": true}', {"Content-Type": "text/plain"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    assert adaptateur(path="/json") == {
        "status": 200, "content_type": "text/plain", "body": {"ok": True}}


def test_texte_tronque(monkeypatch, transport):
    monkeypatch.setattr(http_adapter, "MAX_TEXTE", 5)
    transport.reponse = Reponse(200, b"abcdefghij", {"Content-Type": "text/plain"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    resultat = adaptateur(path="/texte")

    assert resultat["body"] == "abcde"


def test_http_localhost_autorise_https_public_requis(transport):
    adaptateur = creer_adaptateur_http("http://localhost:8080", transport=transport)
    assert callable(adaptateur)
    assert callable(creer_adaptateur_http("http://127.0.0.1", transport=transport))

    with pytest.raises(HTTPInvalide, match="HTTPS"):
        creer_adaptateur_http("http://api.exemple.fr", transport=transport)
    with pytest.raises(HTTPInvalide, match="identifiants"):
        creer_adaptateur_http("https://user:motdepasse@api.exemple.fr", transport=transport)


def test_allowlist_d_hotes(transport):
    adaptateur = creer_adaptateur_http(
        "https://api.exemple.fr", allowlist_hosts=("api.exemple.fr",), transport=transport)
    assert callable(adaptateur)

    with pytest.raises(HTTPInvalide, match="allowlist"):
        creer_adaptateur_http(
            "https://api.exemple.fr", allowlist_hosts=("autre.exemple.fr",), transport=transport)


def test_methode_refusee_par_defaut_puis_autorisee_explicitement(transport):
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)
    with pytest.raises(HTTPRefuse) as refus:
        adaptateur(method="POST", path="/objets")
    assert refus.value.statut == "methode_refusee"
    assert transport.appels == []

    transport.reponse = Reponse(201, b'{"cree": true}', {"Content-Type": "application/json"})
    adaptateur = creer_adaptateur_http(
        "https://api.exemple.fr", allow_methods=("GET", "POST"), transport=transport)
    assert adaptateur(method="post", path="/objets", json={"nom": "x"})["body"] == {"cree": True}
    assert transport.appels[-1]["method"] == "POST"
    assert transport.appels[-1]["json"] == {"nom": "x"}


def test_entetes_porteurs_de_secret_refuses(transport):
    for entetes in (
        {"Authorization": "Bearer jeton"},
        {"Cookie": "session=abc"},
        {"X-Api-Key": "cle"},
        {"X-Custom": "secret"},
        {"Host": "interne.exemple.fr"},
    ):
        with pytest.raises(HTTPInvalide):
            creer_adaptateur_http("https://api.exemple.fr", headers=entetes, transport=transport)


@pytest.mark.parametrize("chemin", (
    "https://autre.exemple.fr/vol",
    "//autre.exemple.fr/vol",
    "/../admin",
    "/a/%2e%2e/b",
    "/a/%252e%252e/b",
    "/a/%2e%2e?q=1",
    "/ok%0d%0aX",
    "/tools/call",
    "/tools/./call",
    "/v1/tools/call?q=1",
))
def test_chemins_hors_hote_ou_tools_call_refuses(transport, chemin):
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    with pytest.raises(HTTPRefuse) as refus:
        adaptateur(path=chemin)

    assert refus.value.statut in ("chemin_refuse", "outil_refuse")
    assert transport.appels == []


def test_tools_call_reste_refuse_avec_post_autorise(transport):
    adaptateur = creer_adaptateur_http(
        "https://api.exemple.fr", allow_methods=("GET", "POST"), transport=transport)

    with pytest.raises(HTTPRefuse) as refus:
        adaptateur(method="POST", path="/tools/call", json={})

    assert refus.value.statut == "outil_refuse"
    assert transport.appels == []


def test_redirection_refusee(transport):
    transport.reponse = Reponse(302, b"", {"Location": "https://autre.exemple.fr"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    with pytest.raises(HTTPRefuse) as refus:
        adaptateur(path="/redirection")

    assert refus.value.statut == "redirection"
    assert transport.appels[0]["allow_redirects"] is False


def test_timeout_et_erreur_de_transport_sanitises(transport):
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)
    transport.erreur = requests.exceptions.Timeout("GET https://api.exemple.fr secret")
    with pytest.raises(HTTPRefuse) as delai:
        adaptateur(path="/lent")
    assert delai.value.statut == "timeout"
    assert "secret" not in str(delai.value)

    transport.erreur = RuntimeError("mot de passe secret")
    with pytest.raises(HTTPRefuse) as panne:
        adaptateur(path="/panne")
    assert panne.value.statut == "transport"
    assert "secret" not in str(panne.value)


def test_reponse_trop_volumineuse_refusee(monkeypatch, transport):
    monkeypatch.setattr(http_adapter, "MAX_OCTETS", 10)
    transport.reponse = Reponse(200, b"x" * 11, {"Content-Type": "text/plain"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    with pytest.raises(HTTPRefuse) as refus:
        adaptateur(path="/gros")

    assert refus.value.statut == "reponse_trop_volumineuse"


def test_aucune_mutation_ni_entete_sensible_renvoye(transport):
    entetes = {"Accept": "application/json"}
    methodes = ["GET"]
    transport.reponse = Reponse(
        200, b'{"ok": true}',
        {"Content-Type": "application/json", "Set-Cookie": "session=abc", "Authorization": "Bearer x"})
    adaptateur = creer_adaptateur_http(
        "https://api.exemple.fr", headers=entetes, allow_methods=methodes, transport=transport)

    resultat = adaptateur(path="/sante")

    assert entetes == {"Accept": "application/json"}
    assert methodes == ["GET"]
    assert set(resultat) == {"status", "content_type", "body"}
    assert "Set-Cookie" not in resultat
    assert "Authorization" not in resultat


def test_transport_par_defaut_est_requests_request(monkeypatch, transport):
    monkeypatch.setattr(http_adapter.requests, "request", transport)
    transport.reponse = Reponse(200, b"ok", {"Content-Type": "text/plain"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr")

    assert adaptateur(path="/defaut")["body"] == "ok"
    assert transport.appels[0]["allow_redirects"] is False


def test_params_forwardes_sans_mutation(transport):
    params = {"page": "1"}
    transport.reponse = Reponse(200, b"ok", {"Content-Type": "text/plain"})
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    assert adaptateur(path="/liste", params=params)["body"] == "ok"
    assert params == {"page": "1"}
    assert transport.appels[0]["params"] == {"page": "1"}


def test_options_inconnues_et_corps_de_lecture_refuses(transport):
    adaptateur = creer_adaptateur_http("https://api.exemple.fr", transport=transport)

    with pytest.raises(HTTPInvalide):
        adaptateur(path="/x", allow_redirects=True)
    with pytest.raises(HTTPRefuse):
        adaptateur(path="/x", json={"a": 1})
    assert transport.appels == []
