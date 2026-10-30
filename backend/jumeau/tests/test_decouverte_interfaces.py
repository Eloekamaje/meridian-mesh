"""Découverte d'interfaces de bout en bout : collecte, persistance, diff, impacts et journal du run."""
import json

import pytest

from jumeau import decouverte_interfaces, interfaces, interfaces_depot
from jumeau.tests.conftest import besoin_pg


def _openapi(chemins, version="1.0.0"):
    return {
        "openapi": "3.0.3",
        "info": {"title": "Comptes", "version": version},
        "servers": [{"url": "https://api.example.test/v1"}],
        "paths": chemins,
    }


def _ecrire_openapi(racine, chemins, version="1.0.0", nom="openapi.json"):
    (racine / nom).write_text(json.dumps(_openapi(chemins, version), ensure_ascii=False), encoding="utf-8")


def _claims_gsf():
    return [
        {"id": "c1", "predicat": "EXPOSE", "objet": "GET /", "preuve": "server.py#L10", "confiance": 0.7},
        {"id": "c2", "predicat": "EXPOSE", "objet": "GET /status", "preuve": "server.py#L20", "confiance": 0.7},
        {"id": "c3", "predicat": "EXPOSE", "objet": "POST /status", "preuve": "server.py#L30", "confiance": 0.7},
    ]


@besoin_pg
def test_openapi_et_config_persistes_avec_run_ok(conn, tmp_path):
    _ecrire_openapi(tmp_path, {
        "/comptes": {"get": {"operationId": "listerComptes"}, "post": {"operationId": "creerCompte"}},
        "/sante": {"get": {"operationId": "sante"}},
    })
    (tmp_path / "application.properties").write_text(
        "legacy.url=https://legacy.example.test/api\n", encoding="utf-8")

    res = decouverte_interfaces.executer(
        conn, "banque", "comptes", racine=tmp_path, environment="prod", source="files")

    run = res["run"]
    assert run["status"] == "ok" and run["error"] is None
    assert run["id"].startswith("run-") and run["started_at"] and run["ended_at"]
    assert (run["source"], run["environment"]) == ("files", "prod")
    assert (run["stats"]["contracts"], run["stats"]["operations"], run["stats"]["bindings"],
            run["stats"]["assertions"]) == (1, 3, 2, 4)
    assert {(o["method"], o["path"]) for o in res["graphe"]["operations"]} == {
        ("GET", "/comptes"), ("POST", "/comptes"), ("GET", "/sante")}
    assert {a["predicate"] for a in res["graphe"]["assertions"]} == {"EXPOSE", "CONSOMME"}

    ligne = conn.execute(
        "SELECT status, source, environment, stats, changes, impacts, error, started_at, ended_at "
        "FROM discovery_run WHERE tenant_id = %s AND id = %s", ("banque", run["id"])).fetchone()
    assert ligne[0] == "ok" and ligne[1] == "files" and ligne[2] == "prod"
    assert ligne[3]["operations"] == 3 and ligne[3]["assertions"] == 4
    assert isinstance(ligne[4], list) and len(ligne[4]) == run["stats"]["changements"]
    assert ligne[5] == [] and ligne[6] is None and ligne[7] and ligne[8]

    lu = interfaces_depot.lire_graph(conn, "banque", "comptes")
    assert {(o.method, o.path) for o in lu.operations} == {
        ("GET", "/comptes"), ("POST", "/comptes"), ("GET", "/sante")}
    assert len(lu.contracts) == 1 and len(lu.assertions) == 4 and len(lu.bindings) == 2


@besoin_pg
def test_deuxieme_run_identique_ne_change_rien_et_ne_duplique_pas(conn, tmp_path):
    _ecrire_openapi(tmp_path, {
        "/comptes": {"get": {"operationId": "listerComptes"}},
        "/sante": {"get": {"operationId": "sante"}},
    })
    premier = decouverte_interfaces.executer(conn, "banque", "comptes", racine=tmp_path, environment="prod")
    second = decouverte_interfaces.executer(conn, "banque", "comptes", racine=tmp_path, environment="prod")

    assert premier["changements"] and second["changements"] == [] and second["impacts"] == []
    assert second["run"]["status"] == "ok" and second["run"]["stats"]["changements"] == 0
    assert interfaces_depot.compter(conn, "banque") == {
        "contracts": 1, "operations": 2, "bindings": 1, "assertions": 2}
    assert conn.execute("SELECT count(*) FROM discovery_run WHERE tenant_id = %s",
                        ("banque",)).fetchone()[0] == 2

    lu = interfaces_depot.lire_graph(conn, "banque", "comptes")
    assert len(lu.operations) == 2 == len({o.id for o in lu.operations})
    assert len(lu.assertions) == 2 and len(lu.bindings) == 1


@besoin_pg
def test_suppression_openapi_breaking_et_impact_du_consommateur_prouve(conn, tmp_path):
    _ecrire_openapi(tmp_path, {
        "/comptes": {"get": {"operationId": "listerComptes"}},
        "/comptes/{id}": {"delete": {"operationId": "supprimerCompte"}},
    })
    assert decouverte_interfaces.executer(
        conn, "banque", "comptes", racine=tmp_path, environment="prod")["run"]["status"] == "ok"

    interfaces_depot.enregistrer(conn, "banque", interfaces.InterfaceGraph(assertions=[interfaces.Assertion(
        subject="portail", predicate="CONSOMME", object="DELETE /comptes/{id}", mode="declared", source="config",
        locator="portail/application.properties", environment="prod", confidence=0.6,
        evidence="digest-portail")]))

    _ecrire_openapi(tmp_path, {"/comptes": {"get": {"operationId": "listerComptes"}}})
    res = decouverte_interfaces.executer(conn, "banque", "comptes", racine=tmp_path, environment="prod")

    ruptures = [c for c in res["changements"] if c["type"] == "operation_removed"]
    assert len(ruptures) == 1 and ruptures[0]["severity"] == "breaking"
    assert (ruptures[0]["before"]["method"], ruptures[0]["before"]["path"]) == ("DELETE", "/comptes/{id}")

    assert len(res["impacts"]) == 1
    impact = res["impacts"][0]
    assert (impact["application"], impact["change_type"], impact["severity"]) == (
        "portail", "operation_removed", "breaking")
    assert impact["evidence"][0]["subject"] == "portail"
    assert impact["evidence"][0]["locator"] == "portail/application.properties"
    assert impact["evidence"][0]["evidence"] == "digest-portail"

    ligne = conn.execute("SELECT status, changes, impacts FROM discovery_run WHERE id = %s",
                         (res["run"]["id"],)).fetchone()
    assert ligne[0] == "ok"
    assert any(change["type"] == "operation_removed" for change in ligne[1])
    assert ligne[2][0]["evidence"][0]["evidence"] == "digest-portail"

    conservee = conn.execute(
        "SELECT object, mode, source, locator, evidence FROM interface_assertion "
        "WHERE tenant_id = %s AND subject = %s", ("banque", "portail")).fetchone()
    assert conservee == ("DELETE /comptes/{id}", "declared", "config", "portail/application.properties",
                         "digest-portail")


@besoin_pg
def test_claims_only_gsf_mockup_declare_les_trois_operations(conn):
    res = decouverte_interfaces.executer(
        conn, "banque", "gsf-mockup", claims=_claims_gsf(), environment="test", source="code")

    assert res["run"]["status"] == "ok"
    assert {(o["method"], o["path"]) for o in res["graphe"]["operations"]} == {
        ("GET", "/"), ("GET", "/status"), ("POST", "/status")}
    assert len(res["graphe"]["assertions"]) == 3
    assert all(a["mode"] == "declared" and a["source"] == "code" for a in res["graphe"]["assertions"])
    assert res["graphe"]["contracts"][0]["format"] == "code"
    assert {a["locator"] for a in res["graphe"]["assertions"]} == {
        "server.py#L10", "server.py#L20", "server.py#L30"}

    lu = interfaces_depot.lire_graph(conn, "banque", "gsf-mockup")
    assert {(o.method, o.path) for o in lu.operations} == {
        ("GET", "/"), ("GET", "/status"), ("POST", "/status")}
    assert len(lu.assertions) == 3 and len(lu.contracts) == 1


@besoin_pg
def test_isolation_tenant_sur_les_graphes_les_runs_et_les_diffs(conn, tmp_path):
    banque = tmp_path / "banque"
    assurance = tmp_path / "assurance"
    banque.mkdir()
    assurance.mkdir()
    _ecrire_openapi(banque, {"/comptes": {"get": {"operationId": "listerComptes"}}})
    _ecrire_openapi(assurance, {"/assurances": {"get": {"operationId": "listerAssurances"}}})

    res_banque = decouverte_interfaces.executer(
        conn, "banque", "comptes", racine=banque, environment="prod")
    res_assurance = decouverte_interfaces.executer(
        conn, "assurance", "comptes", racine=assurance, environment="prod")
    assert {o["path"] for o in res_banque["graphe"]["operations"]} == {"/comptes"}
    assert {o["path"] for o in res_assurance["graphe"]["operations"]} == {"/assurances"}

    lu_banque = interfaces_depot.lire_graph(conn, "banque", "comptes")
    lu_assurance = interfaces_depot.lire_graph(conn, "assurance", "comptes")
    assert {o.path for o in lu_banque.operations} == {"/comptes"}
    assert {o.path for o in lu_assurance.operations} == {"/assurances"}
    assert {a.subject for a in lu_banque.assertions} == {"comptes"}
    assert {a.subject for a in lu_assurance.assertions} == {"comptes"}

    # Un second run côté banque ne doit voir ni l'opération ni le run de l'assurance.
    encore = decouverte_interfaces.executer(conn, "banque", "comptes", racine=banque, environment="prod")
    assert encore["changements"] == [] and encore["impacts"] == []

    comptes = dict(conn.execute(
        "SELECT tenant_id, count(*) FROM discovery_run GROUP BY tenant_id").fetchall())
    assert comptes == {"banque": 2, "assurance": 1}


@besoin_pg
def test_run_partiel_est_journalise_avec_ses_diagnostics(conn):
    res = decouverte_interfaces.executer(
        conn, "banque", "gsf-mockup", claims=[{"id": "c1", "predicat": "EXPOSE", "objet": "MongoDB"}],
        environment="test", source="code")

    assert res["run"]["status"] == "partial" and res["run"]["error"] is None
    assert res["run"]["stats"]["partial"] is True
    assert any("aucune exposition" in diagnostic for diagnostic in res["run"]["stats"]["diagnostics"])
    assert res["graphe"]["partial"] is True

    ligne = conn.execute("SELECT status, stats, error FROM discovery_run WHERE id = %s",
                         (res["run"]["id"],)).fetchone()
    assert ligne[0] == "partial" and ligne[1]["partial"] is True and ligne[2] is None


@besoin_pg
def test_run_erreur_est_journalise_puis_relance(conn, tmp_path):
    absent = tmp_path / "absent"
    with pytest.raises(ValueError, match="racine introuvable"):
        decouverte_interfaces.executer(conn, "banque", "comptes", racine=absent, environment="prod")

    ligne = conn.execute(
        "SELECT id, status, error, started_at, ended_at, stats, changes, impacts FROM discovery_run "
        "WHERE tenant_id = %s AND application_id = %s", ("banque", "comptes")).fetchone()
    assert ligne is not None
    assert ligne[0].startswith("run-") and ligne[1] == "error"
    assert "racine introuvable" in ligne[2] and len(ligne[2]) <= 200
    assert ligne[3] and ligne[4] and ligne[5] == {} and ligne[6] == [] and ligne[7] == []
    assert interfaces_depot.compter(conn, "banque") == {
        "contracts": 0, "operations": 0, "bindings": 0, "assertions": 0}
