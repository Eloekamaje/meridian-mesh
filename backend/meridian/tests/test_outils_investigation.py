"""Outils read-only : code, CMDB et gateway."""
from __future__ import annotations

from meridian.adapters.outbound.postgres.outils_investigation import (
    OutilBindings,
    OutilCMDB,
    OutilCode,
    OutilGateway,
)
from meridian.domain.decouverte_liens import Binding


def test_l_outil_code_cite_les_lignes_sans_executer():
    outil = OutilCode({"src/ComptesClient.java": """
class ComptesClient {
  String url = "${comptes.base-url}";
}
"""})

    resultat = outil.appeler({"reference": "${comptes.base-url}"})

    assert resultat["candidats"] == []
    assert resultat["evidence_ids"] == ["src/ComptesClient.java:3"]
    assert "ligne(s) de code" in resultat["resume"]


def test_l_outil_cmdb_propose_un_twin_avec_preuve():
    outil = OutilCMDB([{
        "service": "comptes-api", "twin_id": "comptes",
        "application_id": "comptes", "evidence_id": "cmdb:1",
    }])

    resultat = outil.appeler({"reference": "http://comptes-api:8080/accounts/1"})

    assert resultat["candidats"][0]["twin_id"] == "comptes"
    assert resultat["evidence_ids"] == ["cmdb:1"]


def test_l_outil_gateway_suit_route_service_twin():
    outil = OutilGateway([
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", evidence_ids=("gateway:1",)),
        Binding(kind="SERVICE", nom="comptes-api", valeur="comptes",
                environment="prod", evidence_ids=("service:1",)),
    ])

    resultat = outil.appeler({"reference": "http://gateway.internal/accounts/42"})

    assert resultat["candidats"][0]["twin_id"] == "comptes"
    assert "route /accounts" in resultat["candidats"][0]["reason"]


def test_l_outil_gateway_ne_devine_pas_si_le_service_est_inconnu():
    outil = OutilGateway([
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", evidence_ids=("gateway:1",)),
    ])

    resultat = outil.appeler({"reference": "http://gateway.internal/accounts/42"})

    assert resultat["candidats"] == []
    assert resultat["evidence_ids"] == ["gateway:1"]
    assert "non rattaché" in resultat["resume"]


def test_l_outil_bindings_resout_la_chaine_complete():
    outil = OutilBindings([
        Binding(kind="PROPERTY", nom="comptes.base-url",
                valeur="http://gateway.internal/accounts", environment="prod"),
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod"),
        Binding(kind="SERVICE", nom="comptes-api", valeur="comptes",
                environment="prod"),
    ], "prod")

    resultat = outil.appeler({"reference": "${comptes.base-url}"})

    assert resultat["candidats"][0]["twin_id"] == "comptes"


def test_l_outil_servicenow_rattache_un_ci_au_registre():
    from meridian.adapters.outbound.postgres.outils_investigation import OutilServiceNow

    outil = OutilServiceNow(
        lambda recherche: [{"cle": "comptes-api", "nom": "Comptes API"}],
        [{"twin_id": "comptes", "service": "comptes-api", "application_id": "comptes"}])

    resultat = outil.appeler({"reference": "comptes"})

    assert resultat["candidats"][0]["twin_id"] == "comptes"
    assert resultat["evidence_ids"] == ["servicenow:ci:comptes-api"]


def test_l_outil_servicenow_ne_devine_pas_un_twin_sans_registre():
    from meridian.adapters.outbound.postgres.outils_investigation import OutilServiceNow

    outil = OutilServiceNow(lambda recherche: [{"cle": "inconnu", "nom": "Inconnu"}], [])

    resultat = outil.appeler({"reference": "inconnu"})

    assert resultat["candidats"] == []
    assert resultat["evidence_ids"] == ["servicenow:ci:inconnu"]


def test_l_outil_apm_rattache_les_dependances_observees():
    from meridian.adapters.outbound.postgres.outils_investigation import OutilAPM

    outil = OutilAPM(
        lambda: ["Appelle paiements-api", "Appelé par antifraude-api"],
        [{"twin_id": "paiements", "service": "paiements-api"},
         {"twin_id": "antifraude", "service": "antifraude-api"}])

    resultat = outil.appeler({"service": "comptes-api"})

    assert {c["twin_id"] for c in resultat["candidats"]} == {"paiements", "antifraude"}
    assert "datadog:dependances:paiements-api" in resultat["evidence_ids"]
    assert "datadog:dependances:antifraude-api" in resultat["evidence_ids"]


def test_l_outil_runtime_reutilise_les_assertions_observees():
    from meridian.adapters.outbound.postgres.outils_investigation import OutilRuntime
    from meridian.domain.interfaces import Assertion, InterfaceGraph

    graphe = InterfaceGraph(assertions=[Assertion(
        subject="comptes-api", predicate="CONSOMME",
        object="paiements-api : POST /v1/paiements", mode="observed",
        source="apm", locator="otlp:1", environment="prod", confidence=0.95,
        evidence="trace:1")])

    resultat = OutilRuntime(graphe, [
        {"twin_id": "paiements", "service": "paiements-api"}]).appeler(
        {"reference": "POST /v1/paiements"})

    assert resultat["candidats"][0]["twin_id"] == "paiements"
    assert resultat["evidence_ids"] == [
        "runtime:otlp:1:paiements-api : POST /v1/paiements"]


def test_l_outil_portail_lit_owner_et_implementation():
    from meridian.adapters.outbound.postgres.outils_investigation import OutilPortail

    outil = OutilPortail([{
        "api_id": "comptes.accounts.read", "operation": "GET /accounts/{id}",
        "owner_twin_id": "comptes", "implementation_twin_id": "comptes-api",
        "service": "comptes-api", "evidence_id": "portail:42",
    }])

    resultat = outil.appeler({"reference": "GET /accounts/{id}"})

    assert resultat["candidats"][0]["twin_id"] == "comptes"
    assert resultat["evidence_ids"] == ["portail:42"]
