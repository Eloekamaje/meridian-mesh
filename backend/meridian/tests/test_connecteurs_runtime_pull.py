"""Tirage OTLP authentifié (sans réseau : l'ouverture d'URL est simulée)."""
import io
import json
import urllib.error

import pytest

from meridian.adapters.outbound.connectors import connecteurs_runtime_pull as pull

URL = "https://collecteur.exemple.fr/v1/traces"
HOTE = "collecteur.exemple.fr"
JETON = "jeton-tres-secret-123"
TRACE = "0af7651916cd43dd8448eb211c80319c"
DEBUT_NS = 1_761_825_600_000_000_000


def attribut(cle, valeur):
    if isinstance(valeur, int) and not isinstance(valeur, bool):
        contenu = {"intValue": str(valeur)}
    else:
        contenu = {"stringValue": str(valeur)}
    return {"key": cle, "value": contenu}


def span(kind=3, service="app-a", pair="app-b"):
    return {
        "traceId": TRACE, "spanId": "b7ad6b7169203331", "name": "GET /comptes", "kind": kind,
        "startTimeUnixNano": str(DEBUT_NS), "endTimeUnixNano": str(DEBUT_NS + 12_000_000),
        "attributes": [attribut("http.method", "GET"), attribut("http.route", "/comptes"),
                       attribut("http.status_code", 200), attribut("peer.service", pair)],
    }, service


def payload_otlp(kind=3, service="app-a", pair="app-b"):
    le_span, nom = span(kind, service, pair)
    return {
        "resourceSpans": [{
            "resource": {"attributes": [attribut("service.name", nom)]},
            "scopeSpans": [{"scope": {"name": "test"}, "spans": [le_span]}],
        }],
    }


@pytest.fixture
def reseau(monkeypatch):
    """État du faux collecteur : corps, erreur éventuelle, requêtes reçues et délais demandés."""
    etat = {"corps": b"", "erreur": None, "requetes": [], "delais": []}

    def ouvrir(requete, timeout):
        etat["requetes"].append(requete)
        etat["delais"].append(timeout)
        if etat["erreur"] is not None:
            raise etat["erreur"]
        return io.BytesIO(etat["corps"])

    monkeypatch.setattr(pull, "_ouvrir", ouvrir)
    monkeypatch.delenv("JUMEAU_OTLP_HOTES", raising=False)
    monkeypatch.delenv("MERIDIAN_OTLP_TOKEN", raising=False)
    return etat


def test_hote_autorise_tire_et_produit_un_graphe_observe(reseau, monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    reseau["corps"] = json.dumps(payload_otlp()).encode()

    graph = pull.depuis_url("app-a", URL, environment="prod", source="otel")

    assert [(a.subject, a.predicate, a.object) for a in graph.assertions] == [
        ("app-a", "CONSOMME", "app-b : GET /comptes")]
    assert {a.mode for a in graph.assertions} == {"observed"}
    assert not any(a.mode == "declared" for a in graph.assertions)
    assert graph.contracts[0].environment == "prod"
    assert {a.source for a in graph.assertions} == {"otel"}
    requete = reseau["requetes"][0]
    assert requete.full_url == URL
    assert requete.get_header("Accept") == "application/json"
    assert requete.get_header("Authorization") is None
    assert reseau["delais"] == [pull.DELAI]


def test_hote_autorise_par_parametre_et_entetes_sans_secret(reseau):
    reseau["corps"] = json.dumps(payload_otlp()).encode()

    donnees = pull.tirer_otlp(URL, hotes_autorises=["collecteur.exemple.fr"])

    assert donnees["resourceSpans"][0]["scopeSpans"][0]["spans"]
    requete = reseau["requetes"][0]
    assert requete.get_header("Authorization") is None


def test_aucun_hote_autorise_refuse_avant_reseau(reseau):
    with pytest.raises(pull.HoteRefuse, match="aucun hôte"):
        pull.tirer_otlp(URL)
    assert reseau["requetes"] == []


@pytest.mark.parametrize("url", [
    "https://autre.exemple.fr/v1/traces",
    "http://collecteur.exemple.fr/v1/traces",
    "https://user:motdepasse@collecteur.exemple.fr/v1/traces",
    "https://localhost/v1/traces",
    "https://collecteur.localhost/v1/traces",
    "https://127.0.0.1/v1/traces",
    "https://[::1]/v1/traces",
    "https://collecteur.exemple.fr:8443/v1/traces",
])
def test_url_refusee_avant_tout_reseau(reseau, monkeypatch, url):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)

    with pytest.raises(pull.HoteRefuse):
        pull.tirer_otlp(url)
    assert reseau["requetes"] == []


@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_redirection_refusee_sans_secret(reseau, monkeypatch, code):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", JETON)
    reseau["erreur"] = urllib.error.HTTPError(URL, code, "Found", {"Location": "https://evil.example"}, None)

    with pytest.raises(pull.RedirectionRefusee) as erreur:
        pull.tirer_otlp(URL, secret_ref="env:MERIDIAN_OTLP_TOKEN")

    assert erreur.value.statut == code
    assert "redirection" in str(erreur.value).lower()
    assert JETON not in str(erreur.value) and JETON not in repr(erreur.value)
    assert reseau["requetes"][0].get_header("Authorization") == f"Bearer {JETON}"


@pytest.mark.parametrize("code,type_attendu", [
    (401, pull.AccesRefuse), (403, pull.AccesRefuse), (429, pull.ReponseHTTP), (500, pull.ReponseHTTP)])
def test_erreur_http_typee_sans_secret(reseau, monkeypatch, code, type_attendu):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", JETON)
    reseau["erreur"] = urllib.error.HTTPError(URL, code, "refus", {}, None)

    with pytest.raises(type_attendu) as erreur:
        pull.tirer_otlp(URL, secret_ref="env:MERIDIAN_OTLP_TOKEN")

    assert erreur.value.statut == code
    assert JETON not in str(erreur.value) and JETON not in repr(erreur.value)
    assert URL not in str(erreur.value)
    assert reseau["requetes"][0].get_header("Authorization") == f"Bearer {JETON}"


def test_reponse_trop_grosse_refusee(reseau, monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    reseau["corps"] = b"x" * 65

    with pytest.raises(pull.ReponseTropGrande, match="trop volumineuse"):
        pull.tirer_otlp(URL, max_octets=64)


def test_json_invalide_refuse(reseau, monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    reseau["corps"] = b"{pas du json"

    with pytest.raises(pull.JSONInvalide):
        pull.tirer_otlp(URL)


@pytest.mark.parametrize("document", [[], {}, {"resourceSpans": {}}, {"resource_spans": []}])
def test_schema_sans_resource_spans_refuse(reseau, monkeypatch, document):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    reseau["corps"] = json.dumps(document).encode()

    with pytest.raises(pull.SchemaOTLP, match="resourceSpans"):
        pull.tirer_otlp(URL)


def test_secret_absent_ou_mal_forme_refuse_sans_reseau(reseau, monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    with pytest.raises(pull.SecretRefuse):
        pull.tirer_otlp(URL, secret_ref="env:MERIDIAN_OTLP_TOKEN")

    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", "jeton\nInjection")
    with pytest.raises(pull.SecretRefuse, match="mal formé") as erreur:
        pull.tirer_otlp(URL, secret_ref="env:MERIDIAN_OTLP_TOKEN")
    assert "Injection" not in str(erreur.value)
    assert reseau["requetes"] == []


def test_source_injoignable_sans_secret(reseau, monkeypatch):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", JETON)
    reseau["erreur"] = urllib.error.URLError("connexion refusée")

    with pytest.raises(pull.SourceInjoignable) as erreur:
        pull.tirer_otlp(URL, secret_ref="env:MERIDIAN_OTLP_TOKEN")

    assert JETON not in str(erreur.value)
    assert URL not in str(erreur.value)


def test_cli_imprime_le_graphe_sans_ecriture(reseau, monkeypatch, capsys):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    reseau["corps"] = json.dumps(payload_otlp()).encode()

    code = pull.main([URL, "app-a", "--environment", "prod", "--source", "otel"])

    assert code == 0
    sortie = json.loads(capsys.readouterr().out)
    assert sortie["assertions"][0]["predicate"] == "CONSOMME"
    assert sortie["assertions"][0]["mode"] == "observed"
    assert sortie["contracts"][0]["environment"] == "prod"


def test_cli_refus_sans_secret_dans_le_message(reseau, monkeypatch, capsys):
    monkeypatch.setenv("JUMEAU_OTLP_HOTES", HOTE)
    monkeypatch.setenv("MERIDIAN_OTLP_TOKEN", JETON)
    reseau["erreur"] = urllib.error.HTTPError(URL, 401, "refus", {}, None)

    code = pull.main([URL, "app-a", "--secret-ref", "env:MERIDIAN_OTLP_TOKEN"])

    assert code == 2
    sortie = capsys.readouterr()
    assert "tirage impossible" in sortie.err
    assert JETON not in sortie.err and JETON not in sortie.out
