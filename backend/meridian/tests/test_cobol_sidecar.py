"""Tests du sidecar COBOL : structure, relations, couverture et robustesse."""
from meridian.adapters.outbound.connectors.cobol import CobolSidecar


FIXE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLIENT-PROG.
      * COPY FANTOME.
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CLIENT-FILE ASSIGN TO "CLIENTS.DAT"
              ORGANIZATION IS INDEXED.
       DATA DIVISION.
       FILE SECTION.
       FD CLIENT-FILE.
       01 CLIENT-REC.
          05 CLIENT-ID PIC 9(5).
          05 CLIENT-NAME PIC X(20).
          05 CLIENT-STATUS PIC X.
             88 ACTIF VALUE "A".
       WORKING-STORAGE SECTION.
       01 WS-COMPTEUR PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           COPY COMMON.
           PERFORM INIT-PARA
           CALL "SUBPROG" USING WS-COMPTEUR
           EXEC CICS LINK PROGRAM("CICSPGM") END-EXEC
           EXEC SQL
              SELECT NAME INTO :WS-NAME
              FROM CUSTOMER WHERE ID = 1
           END-EXEC
           GOBACK.
       INIT-PARA.
           MOVE 1 TO WS-COMPTEUR.
"""

LIBRE = """\
*> commentaire libre CALL FANTOME
IDENTIFICATION DIVISION.
PROGRAM-ID. FREE-PROG.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 TOTAL PIC 9(4).
PROCEDURE DIVISION.
MAIN.
    PERFORM TRAITEMENT
    CALL "AUTRE"
    GOBACK.
TRAITEMENT.
    CONTINUE.
"""

COPYBOOK = """\
      * copybook client é
       01  CLIENT-REC.
           05  CLIENT-ID        PIC 9(5).
           05  CLIENT-NAME      PIC X(30).
           05  CLIENT-BALANCE   PIC S9(7)V99 COMP-3.
           05  FILLER           PIC X(2).
               88  CLIENT-ACTIF VALUE "A".
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1) if fragment in ligne)


def test_extraction_fixe_complete(tmp_path):
    (tmp_path / "prog.cbl").write_text(FIXE, encoding="utf-8")
    observations = CobolSidecar().index(tmp_path)

    programme = _par_kind(observations, "cobol_program", "CLIENT-PROG")
    assert len(programme) == 1
    assert programme[0].start == programme[0].end == _numero(FIXE, "PROGRAM-ID")
    assert programme[0].provider == "cobol"
    assert programme[0].parser == "cobol-structural"
    assert programme[0].parser_version == "1.0"
    assert programme[0].language == "cobol"
    assert programme[0].file == "prog.cbl"
    assert programme[0].status == "extracted"
    assert all(o.symbol != "FANTOME" for o in observations)

    divisions = {o.symbol for o in _par_kind(observations, "cobol_division")}
    assert divisions == {
        "IDENTIFICATION DIVISION", "ENVIRONMENT DIVISION", "DATA DIVISION", "PROCEDURE DIVISION"}
    sections = {o.symbol for o in _par_kind(observations, "cobol_section")}
    assert {"CONFIGURATION", "INPUT-OUTPUT", "FILE", "WORKING-STORAGE"} <= sections
    paragraphs = {o.symbol for o in _par_kind(observations, "cobol_paragraph")}
    assert {"MAIN-PARA", "INIT-PARA"} <= paragraphs
    assert "GOBACK" not in paragraphs

    copie = _par_kind(observations, "cobol_copy", "COMMON")[0]
    assert copie.attributes == {"copybook": "COMMON"}
    assert copie.start == _numero(FIXE, "COPY COMMON")

    appel = _par_kind(observations, "cobol_call", "SUBPROG")[0]
    assert appel.attributes == {"target": "SUBPROG", "program": "SUBPROG"}

    perform = _par_kind(observations, "cobol_perform", "INIT-PARA")[0]
    assert perform.attributes == {"target": "INIT-PARA"}

    cics = _par_kind(observations, "cobol_cics")[0]
    assert cics.symbol == "LINK"
    assert cics.attributes == {"command": "LINK", "target": "CICSPGM", "program": "CICSPGM"}

    sql = _par_kind(observations, "cobol_sql")[0]
    assert sql.symbol == "SELECT"
    assert sql.attributes == {"command": "SELECT", "table": "CUSTOMER"}
    assert sql.start == _numero(FIXE, "EXEC SQL")
    fin_sql = next(i for i, ligne in enumerate(FIXE.splitlines(), 1) if ligne.strip() == "END-EXEC")
    assert sql.end == fin_sql

    fichier = _par_kind(observations, "cobol_file", "CLIENT-FILE")
    assert {o.attributes.get("dataset") for o in fichier} == {"CLIENTS.DAT", None}
    assert {o.attributes.get("fd") for o in fichier} == {"CLIENT-FILE", None}

    identifiant = _par_kind(observations, "cobol_field", "CLIENT-ID")[0]
    assert identifiant.attributes == {"level": "05", "type": "9(5)", "length": 5}
    nom = _par_kind(observations, "cobol_field", "CLIENT-NAME")[0]
    assert nom.attributes == {"level": "05", "type": "X(20)", "length": 20}
    compteur = _par_kind(observations, "cobol_field", "WS-COMPTEUR")[0]
    assert compteur.attributes == {"level": "01", "type": "9(3)", "length": 3}

    condition = _par_kind(observations, "cobol_condition", "ACTIF")[0]
    assert condition.attributes == {"level": "88", "values": ["A"]}


def test_free_format_et_commentaires(tmp_path):
    (tmp_path / "free.cob").write_text(LIBRE, encoding="utf-8")
    observations = CobolSidecar().index(tmp_path)

    assert _par_kind(observations, "cobol_program", "FREE-PROG")[0].start == 3
    assert all(o.symbol != "FANTOME" for o in observations)
    assert {o.symbol for o in _par_kind(observations, "cobol_paragraph")} == {"MAIN", "TRAITEMENT"}
    assert _par_kind(observations, "cobol_perform", "TRAITEMENT")[0].attributes == {"target": "TRAITEMENT"}
    assert _par_kind(observations, "cobol_call", "AUTRE")[0].attributes == {"target": "AUTRE", "program": "AUTRE"}
    assert _par_kind(observations, "cobol_field", "TOTAL")[0].attributes == {"level": "01", "type": "9(4)", "length": 4}


def test_copybook_cp1252_champs_et_condition(tmp_path):
    (tmp_path / "client.cpy").write_bytes(COPYBOOK.encode("cp1252"))
    observations = CobolSidecar().index(tmp_path)

    assert _par_kind(observations, "cobol_field", "CLIENT-REC")[0].attributes == {"level": "01"}
    identifiant = _par_kind(observations, "cobol_field", "CLIENT-ID")[0]
    assert identifiant.attributes == {"level": "05", "type": "9(5)", "length": 5}
    solde = _par_kind(observations, "cobol_field", "CLIENT-BALANCE")[0]
    assert solde.attributes == {"level": "05", "type": "S9(7)V99", "usage": "COMP-3", "length": 5}
    assert all(o.symbol != "FILLER" for o in observations)
    condition = _par_kind(observations, "cobol_condition", "CLIENT-ACTIF")[0]
    assert condition.attributes == {"level": "88", "values": ["A"]}


def test_repli_latin1_sur_octet_cp1252_invalide(tmp_path):
    contenu = b"      * \x81\n       IDENTIFICATION DIVISION.\n       PROGRAM-ID. RAW-PROG.\n"
    (tmp_path / "raw.cob").write_bytes(contenu)
    observations = CobolSidecar().index(tmp_path)
    assert _par_kind(observations, "cobol_program", "RAW-PROG")


def test_xml_non_concerne_et_couverture(tmp_path):
    (tmp_path / "prog.cbl").write_text(LIBRE, encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = CobolSidecar()

    observations = sidecar.index(tmp_path)
    assert observations
    assert {o.file for o in observations} == {"prog.cbl"}

    lignes = sidecar.couverture(tmp_path, fichiers=["config.xml"])
    assert len(lignes) == 1
    assert lignes[0].statut == "non_supporte"
    assert lignes[0].parser == "cobol-structural"
    assert lignes[0].language == ""


def test_couverture_indexe_partiel_ignore(tmp_path):
    (tmp_path / "ok.cbl").write_text(FIXE, encoding="utf-8")
    (tmp_path / "vide.cob").write_text("*> rien ici\n", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<x/>", encoding="utf-8")
    sidecar = CobolSidecar()

    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.cbl", "vide.cob", "absent.cbl", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.cbl": "indexe", "vide.cob": "partiel",
        "absent.cbl": "ignore", "config.xml": "non_supporte",
    }


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.cbl").write_text(LIBRE, encoding="utf-8")
    (tmp_path / "b.cbl").write_text(LIBRE.replace("FREE-PROG", "B-PROG"), encoding="utf-8")

    observations = CobolSidecar().index(tmp_path, fichiers=["b.cbl"])
    assert {o.file for o in observations} == {"b.cbl"}
    assert _par_kind(observations, "cobol_program", "B-PROG")


def test_fichier_invalide_non_fatal(tmp_path):
    (tmp_path / "bin.cbl").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = CobolSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.cbl"]) == []
    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut in {"partiel", "indexe", "ignore"}
