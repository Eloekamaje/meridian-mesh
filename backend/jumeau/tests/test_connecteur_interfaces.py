"""Connecteur de fichiers : OpenAPI/Swagger par contenu, configuration par nom, provenance et aucune fuite."""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from jumeau.connecteur_interfaces import collecter

OPENAPI_JSON = {
    "openapi": "3.0.3",
    "info": {"title": "Comptes", "version": "1.4.2"},
    "servers": [{"url": "https://api.example.test/v1"}],
    "paths": {
        "/comptes": {"get": {"operationId": "listerComptes"}},
        "/comptes/{id}": {"get": {"operationId": "lireCompte"}},
    },
}

OPENAPI_YAML = """
openapi: 3.1.0
info:
  title: Paiements
  version: "2.0.0"
paths:
  /paiements:
    post:
      operationId: creerPaiement
"""

WSDL = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             targetNamespace="urn:stock">
  <portType name="StockPortType">
    <operation name="lireStock"/>
  </portType>
  <binding name="StockBinding" type="StockPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="lireStock">
      <soap:operation soapAction="urn:stock/lireStock"/>
    </operation>
  </binding>
  <service name="StockService">
    <port name="StockPort" binding="StockBinding">
      <soap:address location="https://stock.example.test/ws?token=abc123"/>
    </port>
  </service>
</definitions>
"""


def _ecrire_openapi_json(chemin, donnees=None):
    chemin.write_text(json.dumps(donnees or OPENAPI_JSON), encoding="utf-8")
    return chemin


def test_openapi_json_et_yaml_produisent_des_operations_et_assertions_expose(tmp_path):
    _ecrire_openapi_json(tmp_path / "comptes.json")
    (tmp_path / "contrats").mkdir()
    (tmp_path / "contrats" / "paiements.yaml").write_text(OPENAPI_YAML, encoding="utf-8")

    g = collecter(tmp_path, "gestion", "prod")

    assert g.partial is False and g.diagnostics == []
    assert {c.locator for c in g.contracts} == {"comptes.json", "contrats/paiements.yaml"}
    assert {(o.method, o.path, o.name) for o in g.operations} == {
        ("GET", "/comptes", "listerComptes"),
        ("GET", "/comptes/{id}", "lireCompte"),
        ("POST", "/paiements", "creerPaiement"),
    }
    assert {o.environment for o in g.operations} == {"prod"}
    assert [(a.predicate, a.object, a.mode, a.source, a.environment) for a in g.assertions] == [
        ("EXPOSE", "GET /comptes", "declared", "openapi", "prod"),
        ("EXPOSE", "GET /comptes/{id}", "declared", "openapi", "prod"),
        ("EXPOSE", "POST /paiements", "declared", "openapi", "prod"),
    ]
    assert {a.locator for a in g.assertions} == {"comptes.json", "contrats/paiements.yaml"}


def test_config_produit_des_consommes_candidates(tmp_path):
    (tmp_path / "application.properties").write_text(
        "api.url=http://alice:s3cr3t@api.example.test/v1\n"
        "wsdl.endpoint=https://svc.example.test/Service?wsdl\n", encoding="utf-8")
    (tmp_path / "application.yml").write_text(
        "services:\n  stock:\n    endpoint: https://stock.example.test/ws/StockService.wsdl\n", encoding="utf-8")
    (tmp_path / ".env.prod").write_text("ORDERS_URL=https://orders.example.test\n", encoding="utf-8")
    (tmp_path / "app.conf").write_text("billing=https://billing.example.test/api\n", encoding="utf-8")
    (tmp_path / "service.config").write_text("NOTIFY=https://notify.example.test/hook\n", encoding="utf-8")

    g = collecter(tmp_path, "erp", "recette")

    assert {b.url for b in g.bindings} == {
        "http://api.example.test/v1",
        "https://svc.example.test/Service?wsdl",
        "https://stock.example.test/ws/StockService.wsdl",
        "https://orders.example.test",
        "https://billing.example.test/api",
        "https://notify.example.test/hook",
    }
    assert {b.protocol for b in g.bindings} == {"rest", "soap"}
    assert len(g.assertions) == 6
    assert {a.predicate for a in g.assertions} == {"CONSOMME"}
    assert all(a.mode == "declared" and a.confidence < 0.7 for a in g.assertions)
    assert {a.locator for a in g.assertions} == {
        "application.properties", "application.yml", ".env.prod", "app.conf", "service.config"}
    assert g.partial is False


def test_wsdl_detecte_par_contenu_xml_non_wsdl_et_node_modules_ignores(tmp_path):
    (tmp_path / "stock.wsdl").write_text(WSDL, encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "facturation.xml").write_text(
        WSDL.replace("urn:stock", "urn:facture").replace("stock.example.test", "facture.example.test"),
        encoding="utf-8")
    (tmp_path / "configuration.xml").write_text("<configuration><item/></configuration>", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.wsdl").write_text(WSDL, encoding="utf-8")

    g = collecter(tmp_path, "erp", "prod")

    assert {c.locator for c in g.contracts} == {"stock.wsdl", "services/facturation.xml"}
    assert {c.format for c in g.contracts} == {"wsdl"}
    assert {o.name for o in g.operations} == {"lireStock"}
    assert {b.url for b in g.bindings} == {
        "https://stock.example.test/ws?token=***",
        "https://facture.example.test/ws?token=***",
    }
    assert {a.source for a in g.assertions} == {"wsdl"}
    assert {a.locator for a in g.assertions} == {"stock.wsdl", "services/facturation.xml"}
    assert g.partial is False and g.diagnostics == []
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    assert "abc123" not in rendu and str(tmp_path) not in rendu


def test_node_modules_et_git_sont_ignores(tmp_path):
    for dossier in (".git", "node_modules", "tests", "vendor", "build"):
        (tmp_path / dossier).mkdir()
        _ecrire_openapi_json(tmp_path / dossier / "openapi.json")
    _ecrire_openapi_json(tmp_path / "openapi.json")

    g = collecter(tmp_path, "app")

    assert [c.locator for c in g.contracts] == ["openapi.json"]
    assert {a.locator for a in g.assertions} == {"openapi.json"}


def test_un_nom_openapi_ne_suffit_pas_sans_marqueur_dans_le_contenu(tmp_path):
    (tmp_path / "openapi.json").write_text('{"nom": "pas un contrat"}', encoding="utf-8")

    g = collecter(tmp_path, "app")

    assert g.contracts == [] and g.operations == [] and g.assertions == []
    assert g.partial is False and g.diagnostics == []


def test_fichier_trop_gros_est_ignore_et_le_graphe_est_partiel(tmp_path):
    petit = {"openapi": "3.0.0", "info": {"version": "1"},
             "paths": {"/ok": {"get": {"operationId": "ok"}}}}
    _ecrire_openapi_json(tmp_path / "petit.json", petit)
    gros = {**petit, "description": "x" * 1000}
    _ecrire_openapi_json(tmp_path / "gros.json", gros)

    g = collecter(tmp_path, "app", max_octets=250)

    assert [c.locator for c in g.contracts] == ["petit.json"]
    assert g.partial is True
    assert any("gros.json" in diagnostic and "octets" in diagnostic for diagnostic in g.diagnostics)
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    assert str(tmp_path) not in rendu


def test_les_chemins_sont_relatifs_a_la_racine(tmp_path):
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "api" / "openapi.yaml").write_text(OPENAPI_YAML, encoding="utf-8")
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "application.properties").write_text(
        "api.url=https://api.example.test\n", encoding="utf-8")

    g = collecter(tmp_path, "app")

    assert {c.locator for c in g.contracts} == {"services/api/openapi.yaml"}
    assert {a.locator for a in g.assertions} == {"services/api/openapi.yaml",
                                                 "conf/application.properties"}
    assert all(not Path(a.locator).is_absolute() and ".." not in Path(a.locator).parts
               for a in g.assertions)
    assert all(not Path(c.locator).is_absolute() for c in g.contracts)
    assert str(tmp_path) not in json.dumps(g.as_dict(), ensure_ascii=False)


def test_url_avec_identifiants_et_secret_de_requete_absente_du_json(tmp_path):
    (tmp_path / "application.properties").write_text(
        "db.url=http://alice:s3cr3t@db.example.test:5432/x\n"
        "api.url=https://api.example.test/v1?token=abc123&name=public\n", encoding="utf-8")

    g = collecter(tmp_path, "crm")

    assert {b.url for b in g.bindings} == {
        "http://db.example.test:5432/x",
        "https://api.example.test/v1?token=***&name=public",
    }
    rendu = json.dumps(g.as_dict(), ensure_ascii=False)
    assert "alice" not in rendu and "s3cr3t" not in rendu and "abc123" not in rendu


def test_limite_de_fichiers_tronque_le_parcours(tmp_path):
    petit = {"openapi": "3.0.0", "info": {"version": "1"},
             "paths": {"/ok": {"get": {"operationId": "ok"}}}}
    _ecrire_openapi_json(tmp_path / "a.json", petit)
    _ecrire_openapi_json(tmp_path / "b.json", petit)

    g = collecter(tmp_path, "app", max_fichiers=1)

    assert [c.locator for c in g.contracts] == ["a.json"]
    assert g.partial is True
    assert any("limite" in diagnostic and "tronqué" in diagnostic for diagnostic in g.diagnostics)


def test_parcours_deterministe(tmp_path):
    petit = {"openapi": "3.0.0", "info": {"version": "1"},
             "paths": {"/ok": {"get": {"operationId": "ok"}}}}
    for nom in ("z.json", "a.json", "m.yaml"):
        _ecrire_openapi_json(tmp_path / nom, petit)
    (tmp_path / "application.properties").write_text("api.url=https://api.example.test\n", encoding="utf-8")

    premier = collecter(tmp_path, "app").as_dict()
    second = collecter(tmp_path, "app").as_dict()

    assert premier == second
    assert [c["locator"] for c in premier["contracts"]] == ["a.json", "m.yaml", "z.json"]


def test_aucun_acces_reseau(tmp_path, monkeypatch):
    _ecrire_openapi_json(tmp_path / "openapi.json")
    (tmp_path / "application.properties").write_text("api.url=https://api.example.test\n", encoding="utf-8")

    def interdit(*args, **kwargs):
        raise AssertionError("accès réseau interdit")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)

    g = collecter(tmp_path, "app")

    assert [o.name for o in g.operations] == ["listerComptes", "lireCompte"]
    assert {b.url for b in g.bindings} == {"https://api.example.test/v1", "https://api.example.test"}


def test_cli_imprime_le_json_et_rend_2_si_la_racine_est_invalide(tmp_path):
    _ecrire_openapi_json(tmp_path / "openapi.json")
    backend = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    reussi = subprocess.run(
        [sys.executable, "-m", "jumeau.connecteur_interfaces", str(tmp_path), "app",
         "--environment", "prod"], cwd=backend, env=env, capture_output=True, text=True, timeout=60)
    assert reussi.returncode == 0
    rendu = json.loads(reussi.stdout)
    assert rendu["contracts"][0]["application_id"] == "app"
    assert rendu["contracts"][0]["environment"] == "prod"
    assert rendu["contracts"][0]["locator"] == "openapi.json"

    absent = subprocess.run(
        [sys.executable, "-m", "jumeau.connecteur_interfaces", str(tmp_path / "absent"), "app"],
        cwd=backend, env=env, capture_output=True, text=True, timeout=60)
    assert absent.returncode == 2
    assert absent.stdout == ""


GRAPHQL = "type Query { listerComptes: [Compte] } type Mutation { creerCompte(nom: String!): Compte }"
PROTO = 'syntax = "proto3"; service Comptes { rpc GetCompte (Req) returns (Rep); rpc CreerCompte (Req) returns (Rep); }'
ASYNCAPI = """
asyncapi: '2.6.0'
channels:
  comptes/crees:
    publish:
      operationId: publierCompte
    subscribe:
      operationId: recevoirCompte
"""


def test_graphql_grpc_et_asyncapi_sont_decouverts_par_contenu(tmp_path):
    (tmp_path / "schema.graphql").write_text(GRAPHQL, encoding="utf-8")
    (tmp_path / "comptes.proto").write_text(PROTO, encoding="utf-8")
    (tmp_path / "events.yaml").write_text(ASYNCAPI, encoding="utf-8")

    g = collecter(tmp_path, "comptes", "prod")

    assert g.partial is False and g.diagnostics == []
    assert {(o.protocol, o.method, o.path, o.name) for o in g.operations} == {
        ("graphql", "QUERY", "listerComptes", "listerComptes"),
        ("graphql", "MUTATION", "creerCompte", "creerCompte"),
        ("grpc", "RPC", "Comptes.GetCompte", "GetCompte"),
        ("grpc", "RPC", "Comptes.CreerCompte", "CreerCompte"),
        ("asyncapi", "PUBLISH", "comptes/crees", "publierCompte"),
        ("asyncapi", "SUBSCRIBE", "comptes/crees", "recevoirCompte"),
    }
    assert {a.source for a in g.assertions} == {"graphql", "grpc", "asyncapi"}
    assert {c.format for c in g.contracts} == {"graphql", "grpc", "asyncapi"}
