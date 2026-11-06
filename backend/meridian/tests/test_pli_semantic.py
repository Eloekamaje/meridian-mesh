"""Tests du sidecar PL/I sémantique ANTLR : AST, SQL, couverture et robustesse."""
import pytest

from meridian.adapters.outbound.connectors import pli_semantic
from meridian.adapters.outbound.connectors.pli_semantic import PliSemanticSidecar

pytestmark = pytest.mark.skipif(
    not pli_semantic.parser_disponible(),
    reason="parseur ANTLR généré absent (voir tools/pli/README.md)",
)


SOURCE = """\
/* CALL FANTOME; */
* CALL FANTOME2;
// CALL FANTOME3;
MAIN: PROC OPTIONS(MAIN);
  DCL CUSTOMER_NAME CHAR(30) INIT('X');
  DCL (COUNTER, TOTAL) FIXED BIN(31);
  DCL EMP_FILE FILE;
  DCL SECOND ENTRY;
  ENTRY_A: ENTRY;
  CALL LOAD_DATA(CUSTOMER_NAME);
  %INCLUDE COMMON;
  EXEC SQL
    SELECT NAME INTO :CUSTOMER_NAME
    FROM CUSTOMER
    WHERE ID = :COUNTER;
  EXEC SQL INSERT INTO AUDIT VALUES (:COUNTER);
  EXEC SQL UPDATE CUSTOMER SET NAME = :CUSTOMER_NAME;
  EXEC SQL DELETE FROM AUDIT WHERE ID = :COUNTER;
  IF COUNTER = 0 THEN DO;
    CLEANUP: RETURN;
  END;
  RETURN;
END MAIN;
SUB: PROC;
  DCL LOCAL_VAR CHAR(10);
  CALL SUB2;
END SUB;
"""

PROPRE = """\
CLEAN: PROCEDURE;
  DECLARE CNTR FIXED BINARY(31);
  DECLARE CNAME CHARACTER(30);
  DECLARE SECOND ENTRY;
  ENTRY_A: ENTRY;
  CALL LOAD_DATA(CNTR);
  %INCLUDE COMMON;
  IF CNTR = 0 THEN DO;
    CLEANUP: RETURN;
  END;
  RETURN;
END CLEAN;
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment, apres=0):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if i > apres and fragment in ligne)


def test_extraction_semantique_complete(tmp_path):
    (tmp_path / "demo.pli").write_text(SOURCE, encoding="utf-8")
    sidecar = PliSemanticSidecar()
    observations = sidecar.index(tmp_path)

    principal = _par_kind(observations, "pli_proc", "MAIN")[0]
    assert principal.start == principal.end == _numero(SOURCE, "MAIN: PROC")
    assert principal.provider == "pli-semantic"
    assert principal.parser == "pl1-antlr"
    assert principal.parser_version == "4.13.2"
    assert principal.language == "pli"
    assert principal.file == "demo.pli"
    assert principal.status == "extracted"
    assert principal.attributes["rule"] == "procedure2_statement"
    assert principal.attributes["proc"] == "MAIN"
    assert "MAIN" in principal.attributes["tokens"]

    secondaire = _par_kind(observations, "pli_proc", "SUB")[0]
    assert secondaire.start == _numero(SOURCE, "SUB: PROC")
    assert secondaire.attributes["proc"] == "SUB"

    entree = _par_kind(observations, "pli_entry", "ENTRY_A")[0]
    assert entree.start == _numero(SOURCE, "ENTRY_A: ENTRY")
    assert entree.attributes["rule"] == "entry_statement"
    assert entree.attributes["proc"] == "ENTRY_A"

    nom = _par_kind(observations, "pli_var", "CUSTOMER_NAME")[0]
    assert nom.start == _numero(SOURCE, "DCL CUSTOMER_NAME")
    assert nom.attributes["type"] == "CHAR(30)"
    assert nom.attributes["proc"] == "MAIN"
    assert nom.attributes["rule"] == "declare2_statement"
    assert _par_kind(observations, "pli_var", "COUNTER")[0].attributes["type"] == (
        "FIXED BIN(31)")
    assert _par_kind(observations, "pli_var", "TOTAL")[0].attributes["type"] == (
        "FIXED BIN(31)")
    assert _par_kind(observations, "pli_var", "EMP_FILE")[0].attributes["type"] == "FILE"
    assert _par_kind(observations, "pli_var", "SECOND")[0].attributes["type"] == "ENTRY"
    assert _par_kind(observations, "pli_var", "LOCAL_VAR")[0].attributes["type"] == (
        "CHAR(10)")

    appel = _par_kind(observations, "pli_call", "LOAD_DATA")[0]
    assert appel.start == _numero(SOURCE, "CALL LOAD_DATA")
    assert appel.attributes["target"] == "LOAD_DATA"
    assert appel.attributes["proc"] == "MAIN"
    assert appel.attributes["rule"] == "call_statement"
    assert _par_kind(observations, "pli_call", "SUB2")[0].attributes["target"] == "SUB2"

    inclusion = _par_kind(observations, "pli_include", "COMMON")[0]
    assert inclusion.start == _numero(SOURCE, "%INCLUDE COMMON")
    assert inclusion.attributes["target"] == "COMMON"
    assert inclusion.attributes["include"] == "COMMON"
    assert inclusion.attributes["proc"] == "MAIN"

    etiquettes = {o.symbol: o for o in _par_kind(observations, "pli_label")}
    assert etiquettes["CLEANUP"].attributes["proc"] == "MAIN"
    assert etiquettes["CLEANUP"].start == _numero(SOURCE, "CLEANUP: RETURN")
    assert etiquettes["RETURN"].attributes["proc"] == "MAIN"
    assert etiquettes["RETURN"].start == _numero(
        SOURCE, "RETURN;", apres=etiquettes["CLEANUP"].start)

    sql = {o.symbol: o for o in _par_kind(observations, "pli_sql")}
    assert set(sql) == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert sql["SELECT"].start == _numero(SOURCE, "EXEC SQL")
    assert sql["SELECT"].end == _numero(SOURCE, "WHERE ID = :COUNTER;")
    assert sql["SELECT"].attributes["table"] == "CUSTOMER"
    assert sql["SELECT"].attributes["proc"] == "MAIN"
    assert sql["SELECT"].attributes["rule"] == "exec_sql"
    assert sql["INSERT"].attributes["table"] == "AUDIT"
    assert sql["UPDATE"].attributes["table"] == "CUSTOMER"
    assert sql["DELETE"].attributes["table"] == "AUDIT"

    assert all(o.symbol not in {"FANTOME", "FANTOME2", "FANTOME3"} for o in observations)


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "propre.pli").write_text(PROPRE, encoding="utf-8")
    (tmp_path / "demo.pli").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "vide.pl1").write_text("/* rien ici */\n", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = PliSemanticSidecar()

    lignes = sidecar.couverture(
        tmp_path, fichiers=["propre.pli", "demo.pli", "vide.pl1", "absent.pli", "config.xml"])
    statuts = {ligne.file: ligne for ligne in lignes}
    assert statuts["propre.pli"].statut == "indexe"
    assert statuts["demo.pli"].statut == "partiel"
    assert "ANTLR" in statuts["demo.pli"].raison
    assert statuts["vide.pl1"].statut == "partiel"
    assert statuts["absent.pli"].statut == "ignore"
    assert statuts["config.xml"].statut == "non_supporte"
    assert statuts["config.xml"].language == ""
    assert {ligne.parser for ligne in lignes} == {"pl1-antlr"}


def test_erreur_de_parse_ne_leve_jamais(tmp_path):
    (tmp_path / "casse.pli").write_text(
        "CECI N'EST PAS DU PL/I ;;;\nIF THEN ???;\n", encoding="utf-8")
    sidecar = PliSemanticSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut == "partiel"
    assert "ANTLR" in lignes[0].raison


def test_provider_extensions_et_pl1(tmp_path):
    contenu = """\
MAIN: PROC;
  DCL X FIXED;
  CALL AUTRE;
END MAIN;
"""
    (tmp_path / "legacy.pl1").write_text(contenu, encoding="latin-1")
    sidecar = PliSemanticSidecar(provider="pli-semantic-test")

    observations = sidecar.index(tmp_path)
    assert {o.file for o in observations} == {"legacy.pl1"}
    assert {o.provider for o in observations} == {"pli-semantic-test"}
    assert _par_kind(observations, "pli_call", "AUTRE")


def test_parser_absent_ne_leve_pas(tmp_path, monkeypatch):
    (tmp_path / "demo.pli").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setattr(pli_semantic, "_PARSER", None)
    monkeypatch.setattr(pli_semantic, "_CHARGE", True)

    sidecar = PliSemanticSidecar()
    assert sidecar.index(tmp_path) == []
    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut == "non_supporte"
    assert "ANTLR" in lignes[0].raison
