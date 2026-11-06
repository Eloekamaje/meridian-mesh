"""Tests du sidecar PL/I : structure, lignes, SQL, couverture et robustesse."""
from meridian.adapters.outbound.connectors.pli import PliSidecar


SOURCE = """\
/* commentaire global : CALL FANTOME; */
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


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment, apres=0):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if i > apres and fragment in ligne)


def test_extraction_pli_complete(tmp_path):
    (tmp_path / "demo.pli").write_text(SOURCE, encoding="utf-8")
    observations = PliSidecar().index(tmp_path)

    principal = _par_kind(observations, "pli_proc", "MAIN")[0]
    assert principal.start == principal.end == _numero(SOURCE, "MAIN: PROC")
    assert principal.provider == "pli"
    assert principal.parser == "pli-structural"
    assert principal.parser_version == "1.0"
    assert principal.language == "pli"
    assert principal.file == "demo.pli"
    assert principal.status == "extracted"
    assert principal.attributes == {"proc": "MAIN"}

    secondaire = _par_kind(observations, "pli_proc", "SUB")[0]
    assert secondaire.start == _numero(SOURCE, "SUB: PROC")
    assert secondaire.attributes == {"proc": "SUB"}

    entree = _par_kind(observations, "pli_entry", "ENTRY_A")[0]
    assert entree.start == _numero(SOURCE, "ENTRY_A: ENTRY")
    assert entree.attributes == {"proc": "ENTRY_A"}

    nom = _par_kind(observations, "pli_var", "CUSTOMER_NAME")[0]
    assert nom.start == _numero(SOURCE, "DCL CUSTOMER_NAME")
    assert nom.attributes == {"type": "CHAR(30)", "proc": "MAIN"}
    assert _par_kind(observations, "pli_var", "COUNTER")[0].attributes == {
        "type": "FIXED BIN(31)", "proc": "MAIN"}
    assert _par_kind(observations, "pli_var", "TOTAL")[0].attributes == {
        "type": "FIXED BIN(31)", "proc": "MAIN"}
    assert _par_kind(observations, "pli_var", "EMP_FILE")[0].attributes == {
        "type": "FILE", "proc": "MAIN"}
    assert _par_kind(observations, "pli_var", "SECOND")[0].attributes == {
        "type": "ENTRY", "proc": "MAIN"}
    assert _par_kind(observations, "pli_var", "LOCAL_VAR")[0].attributes == {
        "type": "CHAR(10)", "proc": "SUB"}

    appel = _par_kind(observations, "pli_call", "LOAD_DATA")[0]
    assert appel.start == _numero(SOURCE, "CALL LOAD_DATA")
    assert appel.attributes == {"target": "LOAD_DATA", "proc": "MAIN"}
    assert _par_kind(observations, "pli_call", "SUB2")[0].attributes == {
        "target": "SUB2", "proc": "SUB"}

    inclusion = _par_kind(observations, "pli_include", "COMMON")[0]
    assert inclusion.start == _numero(SOURCE, "%INCLUDE COMMON")
    assert inclusion.attributes == {"include": "COMMON", "proc": "MAIN"}

    etiquettes = {o.symbol: o for o in _par_kind(observations, "pli_label")}
    assert etiquettes["CLEANUP"].attributes == {"proc": "MAIN"}
    assert etiquettes["CLEANUP"].start == _numero(SOURCE, "CLEANUP: RETURN")
    assert etiquettes["RETURN"].attributes == {"proc": "MAIN"}
    assert etiquettes["RETURN"].start == _numero(
        SOURCE, "RETURN;", apres=etiquettes["CLEANUP"].start)

    sql = {o.symbol: o for o in _par_kind(observations, "pli_sql")}
    assert set(sql) == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert sql["SELECT"].start == _numero(SOURCE, "EXEC SQL")
    assert sql["SELECT"].end == _numero(SOURCE, "WHERE ID = :COUNTER;")
    assert sql["SELECT"].attributes == {"table": "CUSTOMER", "proc": "MAIN"}
    assert sql["INSERT"].attributes == {"table": "AUDIT", "proc": "MAIN"}
    assert sql["UPDATE"].attributes == {"table": "CUSTOMER", "proc": "MAIN"}
    assert sql["DELETE"].attributes == {"table": "AUDIT", "proc": "MAIN"}

    assert all(o.symbol not in {"FANTOME", "FANTOME2", "FANTOME3"} for o in observations)


def test_commentaires_lignes_et_retour(tmp_path):
    contenu = """\
/* CALL FANTOME; */
* CALL FANTOME2;
// CALL FANTOME3;
MAIN: PROC;
  DCL X CHAR(1); /* DCL Y CHAR(2); */
  CALL REEL; // CALL FANTOME4
  RETURN;
END MAIN;
"""
    (tmp_path / "commentaires.pli").write_text(contenu, encoding="utf-8")
    observations = PliSidecar().index(tmp_path)

    assert _par_kind(observations, "pli_var", "X")[0].start == _numero(contenu, "DCL X")
    assert not _par_kind(observations, "pli_var", "Y")
    assert _par_kind(observations, "pli_call", "REEL")[0].start == _numero(contenu, "CALL REEL")
    assert not _par_kind(observations, "pli_call", "FANTOME")
    assert all(o.symbol not in {"FANTOME", "FANTOME2", "FANTOME3", "FANTOME4"}
               for o in observations)
    retour = _par_kind(observations, "pli_label", "RETURN")[0]
    assert retour.start == _numero(contenu, "RETURN;")
    assert retour.attributes == {"proc": "MAIN"}


def test_extension_pl1_latin1_et_include(tmp_path):
    contenu = """\
MAIN: PROC;
  DCL TEXTE CHAR(10) INIT('café');
  %INCLUDE FILE(OUTILS);
END MAIN;
"""
    (tmp_path / "legacy.pl1").write_bytes(contenu.encode("latin-1"))
    observations = PliSidecar().index(tmp_path)

    assert _par_kind(observations, "pli_var", "TEXTE")[0].file == "legacy.pl1"
    assert _par_kind(observations, "pli_include", "OUTILS")[0].attributes == {
        "include": "OUTILS", "proc": "MAIN"}


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "ok.pli").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "vide.pl1").write_text("/* rien ici */\n", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = PliSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"ok.pli"}
    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.pli", "vide.pl1", "absent.pli", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.pli": "indexe", "vide.pl1": "partiel",
        "absent.pli": "ignore", "config.xml": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"pli-structural"}
    assert next(ligne for ligne in lignes if ligne.file == "config.xml").language == ""


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.pli").write_text("MAIN: PROC;\nEND MAIN;\n", encoding="utf-8")
    (tmp_path / "b.pli").write_text("AUTRE: PROC;\nEND AUTRE;\n", encoding="utf-8")

    observations = PliSidecar().index(tmp_path, fichiers=["b.pli"])
    assert {o.file for o in observations} == {"b.pli"}
    assert _par_kind(observations, "pli_proc", "AUTRE")


def test_fichier_vide_ou_binaire_non_fatal(tmp_path):
    (tmp_path / "vide.pli").write_text("", encoding="utf-8")
    (tmp_path / "bin.pli").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = PliSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.pli"]) == []
    lignes = sidecar.couverture(tmp_path)
    assert {ligne.file: ligne.statut for ligne in lignes} == {
        "vide.pli": "partiel", "bin.pli": "partiel"}
