"""Mapper CBM : routes, appels HTTP et variables d'environnement vers les liens."""
from __future__ import annotations

from meridian.adapters.outbound.connectors.cbm_liens import extraire_observations
from meridian.adapters.outbound.connectors.decouverte_composants import extraire_depot
from meridian.domain.code_index import Observation
from meridian.domain.liens_composants import SourceDepot


def _obs(kind, symbol="", *, file="src/App.java", attributes=None):
    return Observation(
        provider="cbm", parser="cbm-graph", parser_version="1",
        file=file, language="java", kind=kind, symbol=symbol,
        start=1, end=1, attributes=attributes or {},
    )


def test_cbm_route_devient_une_interface():
    extraction = extraire_observations(
        [_obs("cbm_route", "/accounts", attributes={"method": "GET", "route": "/accounts"})],
        "comptes", "comptes-api", "prod", service_name="comptes-api")

    interface = extraction.interfaces[0]
    assert interface.operation == "GET /accounts"
    assert interface.source_kind == "CODE"
    assert interface.service_name == "comptes-api"
    assert interface.preuves[0].locator == "cbm:src/App.java:1"


def test_cbm_http_calls_devient_un_appel():
    extraction = extraire_observations(
        [_obs("cbm_relation_http_calls", "demo.Client.get",
              attributes={"target": "comptes-api", "method": "GET",
                          "path": "/accounts/42"})],
        "antifraude", "antifraude-api", "prod")

    appel = extraction.appels[0]
    assert appel.methode == "GET"
    assert appel.chemin == "/accounts/42"
    assert appel.cible == "comptes-api"
    assert appel.cible_type == "SERVICE"


def test_cbm_http_calls_sans_hote_garde_l_operation():
    extraction = extraire_observations(
        [_obs("cbm_relation_http_calls", "GET /accounts/42",
              attributes={"target": "GET /accounts/42"})],
        "antifraude", "antifraude-api", "prod")

    appel = extraction.appels[0]
    assert appel.methode == "GET"
    assert appel.cible == "/accounts/42"
    assert appel.cible_type == "CHEMIN"
    assert appel.chemin == "/accounts/42"


def test_cbm_env_url_devient_configuration_et_appel():
    extraction = extraire_observations(
        [_obs("cbm_env", "COMPTES_URL",
              file="conf/app.env",
              attributes={"name": "COMPTES_URL",
                          "value": "http://comptes-api:8080/accounts"})],
        "antifraude", "antifraude-api", "prod")

    assert extraction.configurations[0].cle == "COMPTES_URL"
    assert extraction.appels[0].cible == "http://comptes-api:8080/accounts"
    assert extraction.appels[0].chemin == "/accounts"


def test_cbm_jndi_devient_un_appel():
    extraction = extraire_observations(
        [_obs("jee_injection", "paymentEvents",
              attributes={"lookup": "java:comp/env/jms/PaymentEvents"})],
        "front", "front-api", "prod")

    appel = extraction.appels[0]
    assert appel.protocole == "JNDI"
    assert appel.cible_type == "JNDI"
    assert appel.cible == "java:comp/env/jms/PaymentEvents"


def test_cbm_servlet_devient_une_interface():
    extraction = extraire_observations(
        [_obs("web_servlet", "LegacyServlet",
              attributes={"name": "LegacyServlet",
                          "url_patterns": ["/legacy/accounts"]})],
        "legacy", "legacy-api", "prod")

    assert extraction.interfaces[0].operation == "ANY /legacy/accounts"


def test_cbm_env_avec_secret_est_ignore():
    extraction = extraire_observations(
        [_obs("cbm_env", "DB_URL",
              attributes={"name": "DB_URL",
                          "value": "https://user:pass@example.test/db"})],
        "app", "api", "prod")

    assert extraction.configurations == ()
    assert extraction.appels == ()


def test_extraire_depot_ne_relit_pas_un_fichier_couvert_par_cbm():
    source = SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        fichiers={"src/App.java": """
@RestController
public class App {
    @GetMapping("/lu-par-le-parser-local")
    public String local() { return "ok"; }
}
"""})

    extraction = extraire_depot(source, [
        _obs("cbm_route", "/lu-par-cbm", attributes={"method": "GET", "route": "/lu-par-cbm"}),
    ])

    assert {interface.operation for interface in extraction.interfaces} == {"GET /lu-par-cbm"}


def test_extraire_depot_reste_le_repli_sans_observation():
    source = SourceDepot(
        application_id="comptes", composant_id="comptes-api", environment="prod",
        fichiers={"src/App.java": """
@RestController
public class App {
    @GetMapping("/lu-par-le-parser-local")
    public String local() { return "ok"; }
}
"""})

    extraction = extraire_depot(source)

    assert {interface.operation for interface in extraction.interfaces} == {
        "GET /lu-par-le-parser-local"
    }
