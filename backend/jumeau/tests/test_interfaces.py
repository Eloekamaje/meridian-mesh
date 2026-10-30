"""Le graphe d'interfaces : lecture OpenAPI et configuration, provenance et identifiants stables."""
import hashlib
import json

from jumeau import interfaces

OPENAPI_JSON = json.dumps({
    "openapi": "3.0.3",
    "info": {"title": "Comptes", "version": "1.4.2"},
    "servers": [{"url": "https://api.example.test/v1"}],
    "paths": {
        "/comptes": {"get": {"operationId": "listerComptes"}},
        "/comptes/{id}": {
            "get": {"operationId": "lireCompte"},
            "delete": {"operationId": "supprimerCompte"},
        },
    },
}, ensure_ascii=False)

OPENAPI_YAML = """
openapi: 3.1.0
info:
  title: Paiements
  version: "2.0.0"
servers:
  - url: https://paiements.example.test
paths:
  /paiements:
    post:
      operationId: creerPaiement
"""


def test_openapi_json_operations_version_assertions_et_preuve():
    g = interfaces.parse_openapi("comptes", OPENAPI_JSON, "openapi.json", "prod")
    contrat = g.contracts[0]
    assert contrat.format == "openapi" and contrat.version == "1.4.2"
    assert contrat.digest == hashlib.sha256(OPENAPI_JSON.encode("utf-8")).hexdigest()
    assert [o.name for o in g.operations] == ["listerComptes", "lireCompte", "supprimerCompte"]
    assert [(o.method, o.path, o.protocol, o.version, o.environment) for o in g.operations] == [
        ("GET", "/comptes", "rest", "1.4.2", "prod"),
        ("GET", "/comptes/{id}", "rest", "1.4.2", "prod"),
        ("DELETE", "/comptes/{id}", "rest", "1.4.2", "prod"),
    ]
    assert g.bindings[0].url == "https://api.example.test/v1"
    assert [(a.predicate, a.object, a.mode, a.source, a.locator, a.environment) for a in g.assertions] == [
        ("EXPOSE", "GET /comptes", "declared", "openapi", "openapi.json", "prod"),
        ("EXPOSE", "GET /comptes/{id}", "declared", "openapi", "openapi.json", "prod"),
        ("EXPOSE", "DELETE /comptes/{id}", "declared", "openapi", "openapi.json", "prod"),
    ]
    assert all(a.confidence >= 0.9 and a.evidence == contrat.digest for a in g.assertions)
    assert g.partial is False and g.diagnostics == []


def test_openapi_yaml_et_ids_stables():
    premier = interfaces.parse_openapi("paiements", OPENAPI_YAML, "openapi.yaml", "recette")
    second = interfaces.parse_openapi("paiements", OPENAPI_YAML, "openapi.yaml", "recette")
    assert premier.contracts[0].version == "2.0.0"
    assert [(o.method, o.path, o.name) for o in premier.operations] == [("POST", "/paiements", "creerPaiement")]
    assert [(a.object, a.mode) for a in premier.assertions] == [("POST /paiements", "declared")]
    assert [c.id for c in premier.contracts] == [c.id for c in second.contracts]
    assert [o.id for o in premier.operations] == [o.id for o in second.operations]
    assert [b.id for b in premier.bindings] == [b.id for b in second.bindings]


def test_openapi_invalide_rend_un_resultat_partiel_explicite_sans_crash():
    g = interfaces.parse_openapi("comptes", "{pas: [du json", "openapi.json")
    assert g.partial is True and g.diagnostics
    assert g.contracts[0].digest == hashlib.sha256(b"{pas: [du json").hexdigest()
    assert g.operations == [] and g.assertions == []


def test_openapi_sans_paths_signale_le_document_partiel():
    g = interfaces.parse_openapi("comptes", json.dumps({"openapi": "3.0.0", "info": {"version": "1"}}), "spec.json")
    assert g.partial is True
    assert any("paths" in diagnostic for diagnostic in g.diagnostics)
    assert g.contracts[0].version == "1" and g.operations == []


def test_config_properties_urls_commentaires_placeholders_doublons_et_secrets():
    properties = """
# api.url=http://ignore.example.test
! wsdl.url=https://ignore.example.test/Service?wsdl
api.url=http://alice:s3cr3t@api.example.test/v1
api.url.alias=http://api.example.test/v1
wsdl.endpoint=https://svc.example.test/Service?wsdl
placeholder.url=${API_URL}
templated.url=http://${HOST}/api
secret.token=super-secret-value
"""
    g = interfaces.parse_config("crm", properties, "application.properties", "prod")
    urls = {b.url: b for b in g.bindings}
    assert set(urls) == {"http://api.example.test/v1", "https://svc.example.test/Service?wsdl"}
    assert urls["http://api.example.test/v1"].protocol == "rest"
    assert urls["https://svc.example.test/Service?wsdl"].protocol == "soap"
    assert all(b.environment == "prod" for b in g.bindings)
    assert len(g.assertions) == 2 and all(a.predicate == "CONSOMME" for a in g.assertions)
    assert all(a.confidence < 0.7 for a in g.assertions)
    assert "ignore.example.test" not in json.dumps(g.as_dict())
    assert "super-secret-value" not in json.dumps(g.as_dict())
    assert "${" not in json.dumps(g.as_dict())


def test_config_yaml_ne_recopie_pas_les_valeurs_de_secrets():
    yaml = """
services:
  facturation:
    url: "https://fact.example.test/api"  # endpoint public
    token: "jeton-a-ne-pas-copier"
  stock:
    endpoint: https://stock.example.test/ws/StockService.wsdl
"""
    g = interfaces.parse_config("erp", yaml, "application.yml")
    assert {b.url for b in g.bindings} == {"https://fact.example.test/api",
                                           "https://stock.example.test/ws/StockService.wsdl"}
    assert {b.protocol for b in g.bindings} == {"rest", "soap"}
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    assert "jeton-a-ne-pas-copier" not in rendu and "fact.example.test/api" in rendu


def test_config_env_deduit_et_ignore_les_lignes_desactivees():
    env = """
ORDERS_URL=https://orders.example.test
ORDERS_ALIAS=https://orders.example.test
LEGACY_URL=http://legacy.example.test/old
UNRESOLVED=${ORDERS_URL}
# DISABLED=https://disabled.example.test
TOKEN=abc123
"""
    g = interfaces.parse_config("ventes", env, ".env")
    assert {b.url for b in g.bindings} == {"https://orders.example.test", "http://legacy.example.test/old"}
    assert len(g.bindings) == len(g.assertions) == 2
    rendu = json.dumps(g.as_dict())
    assert "disabled.example.test" not in rendu and "abc123" not in rendu


def test_url_avec_identifiants_et_secret_de_requete_est_redigee():
    g = interfaces.parse_config(
        "crm", "db.url=http://alice:s3cr3t@db.example.test:5432/x\n"
               "api.url=https://api.example.test/v1?token=abc123&name=public\n", "application.properties")
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    assert [b.url for b in g.bindings] == ["http://db.example.test:5432/x",
                                           "https://api.example.test/v1?token=***&name=public"]
    assert "alice" not in rendu and "s3cr3t" not in rendu and "abc123" not in rendu


def test_une_assertion_declaree_n_est_jamais_observed():
    g = interfaces.merge([
        interfaces.parse_openapi("comptes", OPENAPI_JSON, "openapi.json"),
        interfaces.parse_config("comptes", "api.url=https://api.example.test\n", "application.properties"),
    ])
    assert g.assertions
    assert all(a.mode == "declared" and a.observed_at is None for a in g.assertions)
    assert {a["mode"] for a in g.as_dict()["assertions"]} == {"declared"}


def test_index_par_application_et_predicat_et_merge_sans_fusion_d_identite():
    openapi = interfaces.parse_openapi("comptes", OPENAPI_JSON, "openapi.json", "prod")
    config = interfaces.parse_config("comptes", "api.url=https://api.example.test\n", "application.properties", "prod")
    g = interfaces.merge([openapi, config])
    index = g.index()
    assert [c.id for c in index["applications"]["comptes"]["contracts"]] == [openapi.contracts[0].id]
    assert [o.id for o in index["applications"]["comptes"]["operations"]] == [o.id for o in openapi.operations]
    assert {a.predicate for a in index["predicates"]["EXPOSE"]} == {"EXPOSE"}
    assert {a.predicate for a in index["predicates"]["CONSOMME"]} == {"CONSOMME"}
    assert len(interfaces.merge([g, g]).contracts) == 1
    assert len(interfaces.merge([g, g]).operations) == len(openapi.operations)


def test_as_dict_est_serialisable_en_json():
    g = interfaces.merge([
        interfaces.parse_openapi("comptes", OPENAPI_JSON, "openapi.json", "prod"),
        interfaces.parse_config("comptes", "wsdl.url=https://svc.example.test/Service?wsdl\n", "application.properties"),
    ])
    rendu = json.loads(json.dumps(g.as_dict(), ensure_ascii=False))
    assert rendu["contracts"][0]["application_id"] == "comptes"
    assert rendu["operations"][0]["contract_id"] == rendu["contracts"][0]["id"]
    assert rendu["bindings"] and rendu["assertions"]
    assert rendu["partial"] is False and rendu["diagnostics"] == []
