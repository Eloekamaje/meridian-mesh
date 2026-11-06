"""Tests du sidecar RPG : free, fixed, SQL, couverture et robustesse."""
from meridian.adapters.outbound.connectors.rpg import RpgSidecar


LIBRE = """\
**FREE
// commentaire DCL-F FANTOME;
DCL-F CUSTMAST DISK USAGE(*INPUT) KEYED;
DCL-F CUSTLOG DISK USAGE(*OUTPUT);

DCL-PROC GET_CUSTOMER EXPORT;
  DCL-S ID INT(10);
  DCL-S NAME CHAR(50);
  DCL-DS CUSTDATA;
    DCL-S FIELD1 CHAR(10);
  END-DS;
  CALLP LOAD_DATA(ID);
  EXSR CALC_TOTAL;
  CHAIN CUSTMAST;
  READ CUSTMAST;
  WRITE CUSTLOG;
  UPDATE CUSTLOG;
  DELETE CUSTLOG;
  SETLL CUSTMAST;
  EXEC SQL SELECT NAME INTO :NAME FROM CUSTOMER WHERE ID = :ID;
END-PROC;

BEGSR CALC_TOTAL;
ENDSR;
"""

FIXE = """\
     FCUSTMAST  IF   E           K DISK
     * DCL-F FANTOME
     FCUSTLOG   O    E             DISK
     D ID              S             10I 0
     D CUSTDATA        DS
     C                   BEGSR     CALC_TOTAL
     C                   CALLP     LOAD_DATA(ID)
     C                   EXSR      CALC_TOTAL
     C                   CALL      'PROG1'
     C                   CHAIN     CUSTMAST
     C                   SETLL     CUSTMAST
     C                   READ      CUSTMAST
     C                   WRITE     CUSTLOG
     C                   UPDATE    CUSTLOG
     C                   DELETE    CUSTLOG
     C/EXEC SQL
     C+ SELECT NAME INTO :NAME
     C+ FROM CUSTOMER WHERE ID = :ID
     C+ END-EXEC
     C                   ENDSR
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment, apres=0):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if i > apres and fragment in ligne)


def test_free_extraction_complete(tmp_path):
    (tmp_path / "libre.rpgle").write_text(LIBRE, encoding="utf-8")
    observations = RpgSidecar().index(tmp_path)

    fichier = _par_kind(observations, "rpg_file", "CUSTMAST")[0]
    assert fichier.start == fichier.end == _numero(LIBRE, "DCL-F CUSTMAST")
    assert fichier.provider == "rpg"
    assert fichier.parser == "rpg-structural"
    assert fichier.parser_version == "1.0"
    assert fichier.language == "rpg"
    assert fichier.file == "libre.rpgle"
    assert fichier.attributes == {"file": "CUSTMAST"}
    assert _par_kind(observations, "rpg_file", "FANTOME") == []

    proc = _par_kind(observations, "rpg_proc", "GET_CUSTOMER")[0]
    assert proc.start == _numero(LIBRE, "DCL-PROC GET_CUSTOMER")
    assert proc.attributes == {"proc": "GET_CUSTOMER"}

    identifiant = _par_kind(observations, "rpg_var", "ID")[0]
    assert identifiant.attributes == {"proc": "GET_CUSTOMER"}
    assert _par_kind(observations, "rpg_var", "FIELD1")[0].attributes == {
        "proc": "GET_CUSTOMER"}
    assert _par_kind(observations, "rpg_data_structure", "CUSTDATA")[0].attributes == {
        "proc": "GET_CUSTOMER"}

    sous_programme = _par_kind(observations, "rpg_subroutine", "CALC_TOTAL")[0]
    assert sous_programme.attributes == {"target": "CALC_TOTAL"}

    appel = _par_kind(observations, "rpg_call", "LOAD_DATA")[0]
    assert appel.start == _numero(LIBRE, "CALLP LOAD_DATA")
    assert appel.attributes == {"target": "LOAD_DATA", "proc": "GET_CUSTOMER"}
    assert _par_kind(observations, "rpg_call", "CALC_TOTAL")[0].attributes == {
        "target": "CALC_TOTAL", "proc": "GET_CUSTOMER"}

    operations = {o.symbol: o for o in _par_kind(observations, "rpg_operation")}
    assert set(operations) == {"CHAIN", "READ", "WRITE", "UPDATE", "DELETE", "SETLL"}
    assert operations["CHAIN"].attributes == {
        "operation": "CHAIN", "file": "CUSTMAST", "proc": "GET_CUSTOMER"}
    assert operations["DELETE"].attributes == {
        "operation": "DELETE", "file": "CUSTLOG", "proc": "GET_CUSTOMER"}

    sql = _par_kind(observations, "rpg_sql", "SELECT")[0]
    assert sql.start == _numero(LIBRE, "EXEC SQL SELECT")
    assert sql.attributes == {
        "operation": "SELECT", "table": "CUSTOMER", "proc": "GET_CUSTOMER"}


def test_fixed_extraction_et_sql_multiligne(tmp_path):
    (tmp_path / "fixe.rpg").write_text(FIXE, encoding="utf-8")
    observations = RpgSidecar().index(tmp_path)

    assert _par_kind(observations, "rpg_file", "CUSTMAST")[0].start == _numero(
        FIXE, "FCUSTMAST")
    assert _par_kind(observations, "rpg_file", "FANTOME") == []
    assert _par_kind(observations, "rpg_var", "ID")[0].attributes == {}
    assert _par_kind(observations, "rpg_data_structure", "CUSTDATA")[0].attributes == {}
    assert _par_kind(observations, "rpg_subroutine", "CALC_TOTAL")[0].start == _numero(
        FIXE, "BEGSR")

    assert _par_kind(observations, "rpg_call", "LOAD_DATA")[0].attributes == {
        "target": "LOAD_DATA"}
    assert _par_kind(observations, "rpg_call", "PROG1")[0].attributes == {
        "target": "PROG1"}

    operations = {o.symbol: o for o in _par_kind(observations, "rpg_operation")}
    assert set(operations) == {"CHAIN", "READ", "WRITE", "UPDATE", "DELETE", "SETLL"}
    assert operations["SETLL"].attributes == {
        "operation": "SETLL", "file": "CUSTMAST"}

    sql = _par_kind(observations, "rpg_sql", "SELECT")[0]
    assert sql.start == _numero(FIXE, "C/EXEC SQL")
    assert sql.end == _numero(FIXE, "END-EXEC")
    assert sql.attributes == {"operation": "SELECT", "table": "CUSTOMER"}


def test_free_delete_sql_et_commentaires(tmp_path):
    contenu = """\
**FREE
// DELETE FROM FANTOME;
DCL-PROC MAJ;
  EXEC SQL DELETE FROM CUSTLOG WHERE ID = :ID;
  EXEC SQL UPDATE CUSTOMER SET NAME = :NAME WHERE ID = :ID;
  EXEC SQL INSERT INTO AUDIT VALUES (:ID);
  DELETE CUSTLOG;
END-PROC;
"""
    (tmp_path / "maj.sqlrpgle").write_text(contenu, encoding="utf-8")
    observations = RpgSidecar().index(tmp_path)

    sql = {o.symbol: o for o in _par_kind(observations, "rpg_sql")}
    assert set(sql) == {"DELETE", "UPDATE", "INSERT"}
    assert sql["DELETE"].attributes == {
        "operation": "DELETE", "table": "CUSTLOG", "proc": "MAJ"}
    assert sql["UPDATE"].attributes == {
        "operation": "UPDATE", "table": "CUSTOMER", "proc": "MAJ"}
    assert sql["INSERT"].attributes == {
        "operation": "INSERT", "table": "AUDIT", "proc": "MAJ"}

    operation = _par_kind(observations, "rpg_operation", "DELETE")[0]
    assert operation.attributes == {
        "operation": "DELETE", "file": "CUSTLOG", "proc": "MAJ"}
    assert all("FANTOME" not in o.symbol for o in observations)


def test_latin1_et_extension_sqlrpgle(tmp_path):
    contenu = """\
**FREE
// commentaire café
DCL-F CUSTMAST DISK;
"""
    (tmp_path / "legacy.sqlrpgle").write_bytes(contenu.encode("latin-1"))
    observations = RpgSidecar().index(tmp_path)

    fichier = _par_kind(observations, "rpg_file", "CUSTMAST")[0]
    assert fichier.file == "legacy.sqlrpgle"
    assert fichier.start == _numero(contenu, "DCL-F CUSTMAST")


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "ok.rpgle").write_text(LIBRE, encoding="utf-8")
    (tmp_path / "vide.rpg").write_text("**FREE\n// rien\n", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = RpgSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"ok.rpgle"}
    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.rpgle", "vide.rpg", "absent.rpg", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.rpgle": "indexe", "vide.rpg": "partiel",
        "absent.rpg": "ignore", "config.xml": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"rpg-structural"}
    assert next(l for l in lignes if l.file == "config.xml").language == ""


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.rpg").write_text("**FREE\nDCL-F FILEA DISK;\n", encoding="utf-8")
    (tmp_path / "b.rpg").write_text("**FREE\nDCL-F FILEB DISK;\n", encoding="utf-8")

    observations = RpgSidecar().index(tmp_path, fichiers=["b.rpg"])
    assert {o.file for o in observations} == {"b.rpg"}
    assert _par_kind(observations, "rpg_file", "FILEB")


def test_fichier_vide_ou_illisible_non_fatal(tmp_path):
    (tmp_path / "vide.rpg").write_text("", encoding="utf-8")
    (tmp_path / "bin.rpg").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = RpgSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.rpg"]) == []
    lignes = sidecar.couverture(tmp_path)
    assert {ligne.file: ligne.statut for ligne in lignes} == {
        "vide.rpg": "partiel", "bin.rpg": "partiel"}
