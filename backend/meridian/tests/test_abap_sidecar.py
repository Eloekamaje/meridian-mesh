"""Tests du sidecar ABAP : structure, lignes, commentaires et couverture."""
from meridian.adapters.outbound.connectors.abap import AbapSidecar


SOURCE = """\
* commentaire global REPORT ZFANTOME.
REPORT zdemo.
" commentaire PROGRAM zaudit
CLASS zcl_demo DEFINITION PUBLIC.
  PUBLIC SECTION.
    TYPES: ty_name TYPE string,
           ty_count TYPE i.
    DATA mv_name TYPE string.
    PARAMETERS p_input TYPE string.
ENDCLASS.
CLASS zcl_demo IMPLEMENTATION.
  METHOD run.
    DATA lv_count TYPE i.
    " CALL FUNCTION 'ZFANTOME'
    CALL FUNCTION 'Z_REMOTE' EXPORTING iv_id = lv_count.
    CALL METHOD lo_obj->execute EXPORTING iv_id = lv_count.
    PERFORM calculate USING lv_count CHANGING lv_count.
    SELECT * FROM zcustomer INTO TABLE @DATA(lt_rows) WHERE id = 1.
    INSERT INTO zlog VALUES @ls_row.
    UPDATE zcustomer SET name = 'A' WHERE id = 1.
    DELETE FROM zlog WHERE id = 1.
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


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if fragment in ligne)


def test_extraction_abap_complete(tmp_path):
    (tmp_path / "demo.abap").write_text(SOURCE, encoding="utf-8")
    observations = AbapSidecar().index(tmp_path)

    programme = _par_kind(observations, "abap_program", "zdemo")
    assert len(programme) == 1
    assert programme[0].start == programme[0].end == _numero(SOURCE, "REPORT zdemo")
    assert programme[0].provider == "abap"
    assert programme[0].parser == "abap-structural"
    assert programme[0].parser_version == "1.0"
    assert programme[0].language == "abap"
    assert programme[0].file == "demo.abap"
    assert programme[0].status == "extracted"
    assert all(o.symbol not in {"ZFANTOME", "zaudit"} for o in observations)

    classes = _par_kind(observations, "abap_class", "zcl_demo")
    assert len(classes) == 2
    assert {o.start for o in classes} == {
        _numero(SOURCE, "CLASS zcl_demo DEFINITION"),
        _numero(SOURCE, "CLASS zcl_demo IMPLEMENTATION"),
    }
    assert all(o.attributes == {"class": "zcl_demo"} for o in classes)

    methode = _par_kind(observations, "abap_method", "run")[0]
    assert methode.start == _numero(SOURCE, "METHOD run")
    assert methode.attributes == {"method": "run", "class": "zcl_demo"}

    nom = _par_kind(observations, "abap_type", "ty_name")[0]
    assert nom.start == _numero(SOURCE, "TYPES:")
    assert nom.attributes == {"class": "zcl_demo"}
    assert _par_kind(observations, "abap_type", "ty_count")[0].attributes == {
        "class": "zcl_demo"}
    assert _par_kind(observations, "abap_data", "mv_name")[0].attributes == {
        "class": "zcl_demo"}
    assert _par_kind(observations, "abap_data", "lv_count")[0].attributes == {
        "class": "zcl_demo"}
    assert _par_kind(observations, "abap_parameter", "p_input")[0].attributes == {}

    appel = _par_kind(observations, "abap_call", "Z_REMOTE")[0]
    assert appel.start == _numero(SOURCE, "CALL FUNCTION 'Z_REMOTE'")
    assert appel.attributes == {
        "function": "Z_REMOTE", "target": "Z_REMOTE", "parameters": ["iv_id"]}

    methode_appelee = _par_kind(observations, "abap_call", "execute")[0]
    assert methode_appelee.attributes == {
        "method": "execute", "target": "lo_obj->execute", "parameters": ["iv_id"]}

    perform = _par_kind(observations, "abap_call", "calculate")[0]
    assert perform.start == _numero(SOURCE, "PERFORM calculate")
    assert perform.attributes == {"target": "calculate", "parameters": ["lv_count"]}

    forme = _par_kind(observations, "abap_form", "calculate")[0]
    assert forme.attributes == {"parameters": ["p_value", "p_result"]}
    assert _par_kind(observations, "abap_function_module", "z_remote")[0].attributes == {
        "function": "z_remote"}
    assert _par_kind(observations, "abap_include", "zinclude")[0].attributes == {
        "include": "zinclude"}

    sql = {o.symbol: o for o in _par_kind(observations, "abap_sql")}
    assert set(sql) == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert sql["SELECT"].attributes == {"table": "zcustomer"}
    assert sql["SELECT"].start == _numero(SOURCE, "SELECT * FROM")
    assert sql["INSERT"].attributes == {"table": "zlog"}
    assert sql["UPDATE"].attributes == {"table": "zcustomer"}
    assert sql["DELETE"].attributes == {"table": "zlog"}


def test_commentaires_etoile_et_guillemet(tmp_path):
    contenu = """\
* REPORT zcommente.
   * CALL FUNCTION 'ZMASQUE'
" PROGRAM zcommente2
REPORT zreel. " DATA mv_faux TYPE i.
DATA mv_reel TYPE i.
"""
    (tmp_path / "commentaires.abap").write_text(contenu, encoding="utf-8")
    observations = AbapSidecar().index(tmp_path)

    assert _par_kind(observations, "abap_program", "zreel")
    assert all(o.symbol not in {"zcommente", "zcommente2"} for o in observations)
    assert _par_kind(observations, "abap_data", "mv_reel")[0].start == _numero(
        contenu, "DATA mv_reel")
    assert not _par_kind(observations, "abap_data", "mv_faux")
    assert not _par_kind(observations, "abap_call", "ZMASQUE")


def test_latin1_et_extension_abapinclude(tmp_path):
    contenu = """\
* commentaire café REPORT zfaux.
REPORT zlatin.
DATA mv_texte TYPE string VALUE 'café'.
"""
    (tmp_path / "latin.abapinclude").write_bytes(contenu.encode("latin-1"))
    observations = AbapSidecar().index(tmp_path)

    assert _par_kind(observations, "abap_program", "zlatin")[0].file == "latin.abapinclude"
    assert _par_kind(observations, "abap_data", "mv_texte")[0].start == _numero(
        contenu, "DATA mv_texte")


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "ok.abap").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "vide.abap").write_text("", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")
    sidecar = AbapSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"ok.abap"}
    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.abap", "vide.abap", "absent.abap", "config.xml"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.abap": "indexe", "vide.abap": "partiel",
        "absent.abap": "ignore", "config.xml": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"abap-structural"}
    assert next(l for l in lignes if l.file == "config.xml").language == ""


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.abap").write_text("REPORT za.\n", encoding="utf-8")
    (tmp_path / "b.abap").write_text("REPORT zb.\n", encoding="utf-8")

    observations = AbapSidecar().index(tmp_path, fichiers=["b.abap"])
    assert {o.file for o in observations} == {"b.abap"}
    assert _par_kind(observations, "abap_program", "zb")


def test_fichier_vide_ou_illisible_non_fatal(tmp_path):
    (tmp_path / "vide.abap").write_text("", encoding="utf-8")
    (tmp_path / "bin.abap").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = AbapSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.abap"]) == []
    lignes = sidecar.couverture(tmp_path)
    assert {ligne.file: ligne.statut for ligne in lignes} == {
        "vide.abap": "partiel", "bin.abap": "partiel"}
