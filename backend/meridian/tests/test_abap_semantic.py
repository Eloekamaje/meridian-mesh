"""Tests du sidecar ABAP sémantique : runner factice puis intégration abaplint."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from meridian.adapters.outbound.connectors.abap_semantic import (
    ANALYZE_JS,
    VERSION,
    AbapSemanticSidecar,
)

RACINE = Path(__file__).resolve().parents[3]
NODE_MODULES = RACINE / "tools" / "abaplint" / "node_modules" / "@abaplint" / "core"
NODE = shutil.which("node")
INTEGRATION = pytest.mark.skipif(
    NODE is None or not NODE_MODULES.is_dir(),
    reason="Node ou @abaplint/core absent (npm install --prefix tools/abaplint)",
)

SOURCE = """\
REPORT zdemo.
PARAMETERS p_input TYPE string.
CLASS zcl_demo DEFINITION PUBLIC.
  PUBLIC SECTION.
    TYPES: ty_name TYPE string,
           ty_count TYPE i.
    DATA mv_name TYPE string.
    METHODS run.
ENDCLASS.
CLASS zcl_demo IMPLEMENTATION.
  METHOD run.
    DATA lv_count TYPE i.
    CALL FUNCTION 'Z_REMOTE' EXPORTING iv_id = lv_count.
    CALL METHOD lo_obj->execute EXPORTING iv_id = lv_count.
    PERFORM calculate USING lv_count CHANGING lv_count.
    SELECT * FROM zcustomer INTO TABLE @DATA(lt_rows) WHERE id = 1.
    INSERT INTO zlog VALUES @ls_row.
    UPDATE zcustomer SET name = 'A' WHERE id = 1.
    DELETE FROM zlog WHERE id = 1.
    MODIFY zlog FROM @ls_row.
  ENDMETHOD.
  METHOD calculate.
  ENDMETHOD.
ENDCLASS.
INCLUDE zinclude.
FORM calculate USING p_value TYPE i CHANGING p_result TYPE i.
ENDFORM.
FUNCTION z_remote.
ENDFUNCTION.
"""

STATEMENTS = [
    {"type": "Report", "line": 1, "end_line": 1,
     "tokens": ["REPORT", "zdemo", "."], "symbol": "zdemo", "owner": ""},
    {"type": "Parameter", "line": 2, "end_line": 2,
     "tokens": ["PARAMETERS", "p_input", "TYPE", "string", "."],
     "symbol": "p_input", "owner": ""},
    {"type": "ClassDefinition", "line": 3, "end_line": 3,
     "tokens": ["CLASS", "zcl_demo", "DEFINITION", "PUBLIC", "."],
     "symbol": "zcl_demo", "owner": "zcl_demo"},
    {"type": "Type", "line": 5, "end_line": 5,
     "tokens": ["TYPES", "ty_name", "TYPE", "string", ","],
     "symbol": "ty_name", "owner": "zcl_demo"},
    {"type": "Type", "line": 5, "end_line": 6,
     "tokens": ["TYPES", "ty_count", "TYPE", "i", "."],
     "symbol": "ty_count", "owner": "zcl_demo"},
    {"type": "Data", "line": 7, "end_line": 7,
     "tokens": ["DATA", "mv_name", "TYPE", "string", "."],
     "symbol": "mv_name", "owner": "zcl_demo"},
    {"type": "MethodDef", "line": 8, "end_line": 8,
     "tokens": ["METHODS", "run", "."], "symbol": "run", "owner": "zcl_demo"},
    {"type": "ClassImplementation", "line": 10, "end_line": 10,
     "tokens": ["CLASS", "zcl_demo", "IMPLEMENTATION", "."],
     "symbol": "zcl_demo", "owner": "zcl_demo"},
    {"type": "MethodImplementation", "line": 11, "end_line": 11,
     "tokens": ["METHOD", "run", "."], "symbol": "run",
     "owner": "zcl_demo.run"},
    {"type": "Data", "line": 12, "end_line": 12,
     "tokens": ["DATA", "lv_count", "TYPE", "i", "."],
     "symbol": "lv_count", "owner": "zcl_demo.run"},
    {"type": "CallFunction", "line": 13, "end_line": 13,
     "tokens": ["CALL", "FUNCTION", "'Z_REMOTE'", "EXPORTING", "iv_id", "=",
                "lv_count", "."],
     "symbol": "Z_REMOTE", "owner": "zcl_demo.run", "target": "Z_REMOTE"},
    {"type": "Call", "line": 14, "end_line": 14,
     "tokens": ["CALL", "METHOD", "lo_obj", "->", "execute", "EXPORTING",
                "iv_id", "=", "lv_count", "."],
     "symbol": "execute", "owner": "zcl_demo.run",
     "target": "lo_obj->execute"},
    {"type": "Perform", "line": 15, "end_line": 15,
     "tokens": ["PERFORM", "calculate", "USING", "lv_count", "CHANGING",
                "lv_count", "."],
     "symbol": "calculate", "owner": "zcl_demo.run", "target": "calculate"},
    {"type": "Select", "line": 16, "end_line": 16,
     "tokens": ["SELECT", "*", "FROM", "zcustomer", "INTO", "TABLE", "@",
                "DATA", "(", "lt_rows", ")", "WHERE", "id", "=", "1", "."],
     "symbol": "SELECT", "owner": "zcl_demo.run", "table": "zcustomer"},
    {"type": "InsertDatabase", "line": 17, "end_line": 17,
     "tokens": ["INSERT", "INTO", "zlog", "VALUES", "@", "ls_row", "."],
     "symbol": "INSERT", "owner": "zcl_demo.run", "table": "zlog"},
    {"type": "UpdateDatabase", "line": 18, "end_line": 18,
     "tokens": ["UPDATE", "zcustomer", "SET", "name", "=", "'A'", "WHERE",
                "id", "=", "1", "."],
     "symbol": "UPDATE", "owner": "zcl_demo.run", "table": "zcustomer"},
    {"type": "DeleteDatabase", "line": 19, "end_line": 19,
     "tokens": ["DELETE", "FROM", "zlog", "WHERE", "id", "=", "1", "."],
     "symbol": "DELETE", "owner": "zcl_demo.run", "table": "zlog"},
    {"type": "ModifyDatabase", "line": 20, "end_line": 20,
     "tokens": ["MODIFY", "zlog", "FROM", "@", "ls_row", "."],
     "symbol": "MODIFY", "owner": "zcl_demo.run", "table": "zlog"},
    {"type": "Form", "line": 26, "end_line": 26,
     "tokens": ["FORM", "calculate", "USING", "p_value", "TYPE", "i",
                "CHANGING", "p_result", "TYPE", "i", "."],
     "symbol": "calculate", "owner": "calculate"},
    {"type": "FunctionModule", "line": 28, "end_line": 28,
     "tokens": ["FUNCTION", "z_remote", "."], "symbol": "z_remote",
     "owner": "z_remote"},
    {"type": "Include", "line": 25, "end_line": 25,
     "tokens": ["INCLUDE", "zinclude", "."], "symbol": "zinclude",
     "owner": ""},
    {"type": "Unknown", "line": 30, "end_line": 30,
     "tokens": ["PAS", "DU", "ABAP", "."], "symbol": "", "owner": ""},
]


def _resultat(statements=None, status="ok", errors=None, version=VERSION):
    return {
        "file": "demo.abap", "status": status, "parser": "abaplint",
        "parser_version": version, "language": "abap",
        "objects": [{"type": "PROG", "name": "ZDEMO"}],
        "statements": list(STATEMENTS if statements is None else statements),
        "structure": {"type": "Any", "line": 1, "children": []},
        "errors": list(errors or []),
    }


def _runner(resultat=None, appels=None):
    def lancer(chemin):
        if appels is not None:
            appels.append(chemin)
        return _resultat() if resultat is None else resultat
    return lancer


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if fragment in ligne)


def test_index_mappe_les_statements_ast(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    appels = []
    sidecar = AbapSemanticSidecar(runner=_runner(appels=appels))
    observations = sidecar.index(tmp_path)

    assert Path(appels[0]).name == "demo.abap"
    assert all(o.provider == "abap-semantic" for o in observations)
    assert all(o.parser == "abaplint" for o in observations)
    assert all(o.parser_version == VERSION for o in observations)
    assert all(o.language == "abap" for o in observations)
    assert all(o.file == "demo.abap" for o in observations)

    programme = _par_kind(observations, "abap_program", "zdemo")[0]
    assert programme.start == 1
    assert programme.attributes == {
        "type": "Report", "tokens": ["REPORT", "zdemo", "."]}

    parametre = _par_kind(observations, "abap_parameter", "p_input")[0]
    assert parametre.attributes == {
        "type": "Parameter",
        "tokens": ["PARAMETERS", "p_input", "TYPE", "string", "."]}

    classes = _par_kind(observations, "abap_class", "zcl_demo")
    assert len(classes) == 2
    assert {o.start for o in classes} == {3, 10}
    assert all(o.attributes["owner"] == "zcl_demo" for o in classes)

    types = _par_kind(observations, "abap_type")
    assert {o.symbol for o in types} == {"ty_name", "ty_count"}
    assert all(o.attributes["owner"] == "zcl_demo" for o in types)

    methode = _par_kind(observations, "abap_method", "run")
    assert {o.start for o in methode} == {8, 11}
    implementation = next(o for o in methode if o.start == 11)
    assert implementation.attributes["owner"] == "zcl_demo.run"

    assert _par_kind(observations, "abap_data", "lv_count")[0].start == 12

    appel = _par_kind(observations, "abap_call", "Z_REMOTE")[0]
    assert appel.attributes["target"] == "Z_REMOTE"
    assert appel.attributes["owner"] == "zcl_demo.run"

    methode_appelee = _par_kind(observations, "abap_call", "execute")[0]
    assert methode_appelee.attributes["target"] == "lo_obj->execute"

    perform = _par_kind(observations, "abap_call", "calculate")[0]
    assert perform.attributes["target"] == "calculate"

    sql = {o.symbol: o for o in _par_kind(observations, "abap_sql")}
    assert set(sql) == {"SELECT", "INSERT", "UPDATE", "DELETE", "MODIFY"}
    assert sql["SELECT"].attributes["table"] == "zcustomer"
    assert sql["INSERT"].attributes["table"] == "zlog"
    assert sql["UPDATE"].attributes["table"] == "zcustomer"
    assert sql["DELETE"].attributes["table"] == "zlog"
    assert sql["MODIFY"].attributes["table"] == "zlog"
    assert sql["SELECT"].start == 16

    assert _par_kind(observations, "abap_form", "calculate")[0].attributes[
        "owner"] == "calculate"
    assert _par_kind(observations, "abap_function_module", "z_remote")[0].start == 28
    assert _par_kind(observations, "abap_include", "zinclude")[0].start == 25

    assert all(o.symbol != "PAS" for o in observations)


def test_version_du_runner_est_reprise(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    sidecar = AbapSemanticSidecar(
        runner=_runner(_resultat(version="9.9.9")))
    observations = sidecar.index(tmp_path)
    assert {o.parser_version for o in observations} == {"9.9.9"}


def test_runner_malforme_non_fatal(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    sorties = [
        None,
        {"status": "ok", "statements": "pas une liste"},
        {"status": "ok", "statements": [None, 3, {"type": "Report"}]},
        {"status": "bizarre", "statements": []},
    ]
    for sortie in sorties:
        sidecar = AbapSemanticSidecar(runner=lambda chemin, s=sortie: s)
        assert isinstance(sidecar.index(tmp_path), list)
        assert isinstance(sidecar.couverture(tmp_path), list)


def test_couverture_sans_exception(tmp_path):
    (tmp_path / "ok.abap").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "partiel.abap").write_text("REPORT z.\nPAS DU ABAP.\n",
                                           encoding="utf-8")
    (tmp_path / "averti.abap").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "erreur.abap").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")

    def runner(chemin):
        nom = Path(chemin).name
        if nom == "ok.abap":
            return _resultat()
        if nom == "averti.abap":
            return _resultat(errors=[{"key": "parser_error", "line": 1,
                                      "message": "erreur signalée"}])
        if nom == "partiel.abap":
            return _resultat(
                statements=[STATEMENTS[0]], status="partial",
                errors=[{"key": "parser_error", "line": 2,
                         "message": "instruction inconnue"}])
        raise RuntimeError("node absent")

    sidecar = AbapSemanticSidecar(runner=runner)
    lignes = sidecar.couverture(
        tmp_path,
        fichiers=["ok.abap", "partiel.abap", "averti.abap", "erreur.abap",
                  "absent.abap", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.abap": "indexe", "partiel.abap": "partiel",
        "averti.abap": "partiel", "erreur.abap": "ignore",
        "absent.abap": "ignore", "config.xml": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"abaplint"}
    assert next(
        ligne for ligne in lignes if ligne.file == "config.xml").language == ""
    assert "instruction inconnue" in next(
        ligne for ligne in lignes if ligne.file == "partiel.abap").raison
    assert "node absent" in next(
        ligne for ligne in lignes if ligne.file == "erreur.abap").raison


def test_fichier_vide_parse_complet_reste_indexe(tmp_path):
    (tmp_path / "vide.abap").write_text("", encoding="utf-8")
    sidecar = AbapSemanticSidecar(
        runner=_runner(_resultat(statements=[], status="ok")))
    assert sidecar.index(tmp_path) == []
    lignes = sidecar.couverture(tmp_path)
    assert [(ligne.file, ligne.statut) for ligne in lignes] == [
        ("vide.abap", "indexe")]


def test_ordre_des_lignes_ne_depend_pas_du_runner(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    sidecar = AbapSemanticSidecar(runner=_runner())
    observations = sidecar.index(tmp_path)
    assert [o.start for o in observations] == [
        statement["line"] for statement in STATEMENTS
        if statement["type"] in {
            "Report", "Parameter", "ClassDefinition", "Type", "Data",
            "MethodDef", "ClassImplementation", "MethodImplementation",
            "CallFunction", "Call", "Perform", "Select", "InsertDatabase",
            "UpdateDatabase", "DeleteDatabase", "ModifyDatabase", "Form",
            "FunctionModule", "Include"}]


@INTEGRATION
def test_integration_analyze_js_json(tmp_path):
    fichier = tmp_path / "zdemo.abap"
    fichier.write_text(SOURCE, encoding="utf-8")
    termine = subprocess.run(
        [NODE, str(ANALYZE_JS), str(fichier)],
        capture_output=True, text=True, timeout=120)
    assert termine.returncode == 0, termine.stderr
    donnees = json.loads(termine.stdout)

    assert donnees["file"] == str(fichier.resolve())
    assert donnees["status"] == "ok"
    assert donnees["parser"] == "abaplint"
    assert donnees["parser_version"]
    assert donnees["objects"] == [{"type": "PROG", "name": "ZDEMO"}]
    assert donnees["errors"] == []
    assert donnees["structure"]["type"] == "Any"

    types = {s["type"] for s in donnees["statements"]}
    assert {
        "Report", "Parameter", "ClassDefinition", "ClassImplementation",
        "MethodDef", "MethodImplementation", "Type", "Data", "Form",
        "FunctionModule", "CallFunction", "Call", "Perform", "Select",
        "InsertDatabase", "UpdateDatabase", "DeleteDatabase",
        "ModifyDatabase", "Include",
    } <= types

    rapport = next(s for s in donnees["statements"] if s["type"] == "Report")
    assert rapport["line"] == _numero(SOURCE, "REPORT zdemo")
    assert rapport["tokens"] == ["REPORT", "zdemo", "."]
    assert rapport["symbol"] == "zdemo"
    assert rapport["kind"] == "abap_program"

    selection = next(s for s in donnees["statements"] if s["type"] == "Select")
    assert selection["table"] == "zcustomer"
    assert selection["owner"] == "zcl_demo.run"

    methode = next(s for s in donnees["statements"]
                   if s["type"] == "MethodImplementation")
    assert methode["line"] == _numero(SOURCE, "METHOD run")
    assert methode["owner"] == "zcl_demo.run"


@INTEGRATION
def test_integration_sidecar_observations_reelles(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    sidecar = AbapSemanticSidecar()
    observations = sidecar.index(tmp_path)

    assert _par_kind(observations, "abap_program", "zdemo")[0].start == 1
    assert _par_kind(observations, "abap_class", "zcl_demo")
    assert _par_kind(observations, "abap_method", "run")
    assert _par_kind(observations, "abap_sql", "SELECT")[0].attributes[
        "table"] == "zcustomer"
    assert _par_kind(observations, "abap_function_module", "z_remote")
    lignes = sidecar.couverture(tmp_path)
    assert [(ligne.file, ligne.statut) for ligne in lignes] == [
        ("demo.abap", "indexe")]


@INTEGRATION
def test_integration_parse_partiel_sur_source_invalide(tmp_path):
    (tmp_path / "invalide.abap").write_text(
        "REPORT z.\nPAS DU ABAP.\n", encoding="utf-8")
    sidecar = AbapSemanticSidecar()
    observations = sidecar.index(tmp_path)
    assert _par_kind(observations, "abap_program", "z")
    lignes = sidecar.couverture(tmp_path)
    assert [(ligne.file, ligne.statut) for ligne in lignes] == [
        ("invalide.abap", "partiel")]
    assert lignes[0].raison
