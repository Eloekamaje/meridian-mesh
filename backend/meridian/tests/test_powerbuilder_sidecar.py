"""Tests du sidecar PowerBuilder : structure, lignes, SQL, DataWindow et couverture."""
from meridian.adapters.outbound.connectors.powerbuilder import PowerBuilderSidecar


SOURCE = """\
$PBExportHeader$w_main.srw
forward
global type w_main from window
end type
type dw_customer from datawindow within w_main
string dataobject = "d_customer"
end type
end forward

global type w_main from window
integer width = 800
string title = "Clients"
end type
global w_main w_main

global variables
string gs_app
integer gi_count, gi_total
end variables

type variables
string is_name
end variables

forward prototypes
public function integer of_total (integer ai_id)
end prototypes

public function integer of_total (integer ai_id);
integer li_count
SELECT count(*) INTO :li_count FROM customer WHERE id = :ai_id;
if li_count > 0 then
    dw_customer.Retrieve(ai_id)
end if
MessageBox("Total", string(li_count))
return li_count
end function

event open;
    dw_customer.SetTransObject(SQLCA)
    INSERT INTO audit_log (id) VALUES (:gi_count);
    UPDATE customer SET name = 'X' WHERE id = :gi_count;
    DELETE FROM audit_log WHERE id = :gi_count;
end event

on dw_customer::retrieveend
    of_total(1)
end on

on w_main.create
    open(w_main)
end on
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment, apres=0):
    lignes = contenu.splitlines()
    for index in range(apres, len(lignes)):
        if fragment in lignes[index]:
            return index + 1
    raise AssertionError(f"fragment introuvable : {fragment}")


def _derniere_ligne(contenu, fragment):
    lignes = contenu.splitlines()
    for index in range(len(lignes) - 1, -1, -1):
        if fragment in lignes[index]:
            return index + 1
    raise AssertionError(f"fragment introuvable : {fragment}")


def test_extraction_complete_lignes_et_attributs(tmp_path):
    (tmp_path / "w_main.srw").write_text(SOURCE, encoding="utf-8")
    observations = PowerBuilderSidecar().index(tmp_path)

    objet = _par_kind(observations, "pb_object", "w_main")[0]
    debut_objet = _derniere_ligne(SOURCE, "global type w_main from window")
    fin_objet = _numero(SOURCE, "end type", apres=debut_objet)
    assert (objet.start, objet.end) == (debut_objet, fin_objet)
    assert objet.provider == "powerbuilder"
    assert objet.parser == "powerbuilder-structural"
    assert objet.parser_version == "1.0"
    assert objet.language == "powerbuilder"
    assert objet.file == "w_main.srw"
    assert objet.status == "extracted"
    assert objet.attributes == {"object": "w_main"}

    fonction = _par_kind(observations, "pb_function", "of_total")[0]
    assert (fonction.start, fonction.end) == (
        _numero(SOURCE, "public function integer of_total (integer ai_id);"),
        _numero(SOURCE, "end function"))
    assert fonction.attributes == {"function": "of_total", "object": "w_main"}

    evenement = _par_kind(observations, "pb_event", "open")[0]
    assert (evenement.start, evenement.end) == (
        _numero(SOURCE, "event open;"), _numero(SOURCE, "end event"))
    assert evenement.attributes == {"event": "open", "object": "w_main"}

    retour = _par_kind(observations, "pb_event", "retrieveend")[0]
    assert retour.start == _numero(SOURCE, "on dw_customer::retrieveend")
    assert retour.attributes == {
        "event": "retrieveend", "target": "dw_customer", "object": "w_main"}

    creation = _par_kind(observations, "pb_event", "create")[0]
    assert creation.attributes == {
        "event": "create", "target": "w_main", "object": "w_main"}

    globales = {o.symbol: o for o in _par_kind(observations, "pb_var")}
    assert {"gs_app", "gi_count", "gi_total", "is_name"} <= set(globales)
    assert globales["gs_app"].start == _numero(SOURCE, "string gs_app")
    assert globales["gi_count"].start == globales["gi_total"].start == _numero(
        SOURCE, "integer gi_count, gi_total")
    assert globales["is_name"].start == _numero(SOURCE, "string is_name")
    assert globales["gs_app"].attributes == {"object": "w_main"}


def test_appels_source_et_absence_de_bruit_sql(tmp_path):
    (tmp_path / "w_main.srw").write_text(SOURCE, encoding="utf-8")
    observations = PowerBuilderSidecar().index(tmp_path)

    retrieve = _par_kind(observations, "pb_call", "Retrieve")[0]
    assert retrieve.start == _numero(SOURCE, "dw_customer.Retrieve(ai_id)")
    assert retrieve.attributes == {"target": "dw_customer.Retrieve"}

    trans = _par_kind(observations, "pb_call", "SetTransObject")[0]
    assert trans.start == _numero(SOURCE, "dw_customer.SetTransObject(SQLCA)")
    assert trans.attributes == {"target": "dw_customer.SetTransObject"}

    message = _par_kind(observations, "pb_call", "MessageBox")[0]
    assert message.start == _numero(SOURCE, "MessageBox(")
    assert message.attributes == {"target": "MessageBox"}

    total = _par_kind(observations, "pb_call", "of_total")[0]
    assert total.start == _numero(SOURCE, "of_total(1)")
    assert total.attributes == {"target": "of_total"}

    ouverture = _par_kind(observations, "pb_call", "open")[0]
    assert ouverture.start == _numero(SOURCE, "open(w_main)")
    assert ouverture.attributes == {"target": "open"}

    assert not _par_kind(observations, "pb_call", "count")
    assert not _par_kind(observations, "pb_call", "INTO")


def test_sql_select_insert_update_delete(tmp_path):
    (tmp_path / "w_main.srw").write_text(SOURCE, encoding="utf-8")
    observations = PowerBuilderSidecar().index(tmp_path)

    sql = {o.symbol: o for o in _par_kind(observations, "pb_sql")}
    assert set(sql) == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert sql["SELECT"].attributes == {"table": "customer"}
    assert sql["SELECT"].start == _numero(SOURCE, "SELECT count(*)")
    assert sql["INSERT"].attributes == {"table": "audit_log"}
    assert sql["INSERT"].start == _numero(SOURCE, "INSERT INTO audit_log")
    assert sql["UPDATE"].attributes == {"table": "customer"}
    assert sql["UPDATE"].start == _numero(SOURCE, "UPDATE customer")
    assert sql["DELETE"].attributes == {"table": "audit_log"}
    assert sql["DELETE"].start == _numero(SOURCE, "DELETE FROM audit_log")


def test_datawindow_nom_logique_et_objet_porteur(tmp_path):
    (tmp_path / "w_main.srw").write_text(SOURCE, encoding="utf-8")
    observations = PowerBuilderSidecar().index(tmp_path)

    datawindow = _par_kind(observations, "pb_datawindow", "dw_customer")[0]
    debut = _numero(SOURCE, "type dw_customer from datawindow")
    assert (datawindow.start, datawindow.end) == (
        debut, _numero(SOURCE, "end type", apres=debut))
    assert datawindow.attributes == {
        "datawindow": "d_customer", "object": "w_main"}


def test_datawindow_sans_dataobject_garde_le_nom_du_controle(tmp_path):
    contenu = """\
global type w_plain from window
end type
type dw_plain from datawindow within w_plain
end type
"""
    (tmp_path / "w_plain.srw").write_text(contenu, encoding="utf-8")
    observations = PowerBuilderSidecar().index(tmp_path)

    datawindow = _par_kind(observations, "pb_datawindow", "dw_plain")[0]
    assert datawindow.attributes == {
        "datawindow": "dw_plain", "object": "w_plain"}


def test_pbl_binaire_corrompu_non_fatal(tmp_path):
    (tmp_path / "legacy.pbl").write_bytes(b"\x00\x01PB\xff\xfe\x00legacy")
    (tmp_path / "ok.srw").write_text(
        "global type w_ok from window\nend type\n", encoding="utf-8")
    sidecar = PowerBuilderSidecar()

    observations = sidecar.index(tmp_path)
    assert {o.file for o in observations} == {"ok.srw"}
    assert sidecar.index(tmp_path, fichiers=["legacy.pbl"]) == []

    lignes = {ligne.file: ligne for ligne in sidecar.couverture(tmp_path)}
    assert set(lignes) == {"legacy.pbl", "ok.srw"}
    assert lignes["ok.srw"].statut == "indexe"
    assert lignes["legacy.pbl"].statut == "partiel"
    assert "PBL illisible" in lignes["legacy.pbl"].raison


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "ok.srw").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "vide.srw").write_text("", encoding="utf-8")
    (tmp_path / "config.txt").write_text("rien", encoding="utf-8")
    sidecar = PowerBuilderSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"ok.srw"}
    lignes = sidecar.couverture(
        tmp_path,
        fichiers=["ok.srw", "vide.srw", "absent.srw", "config.txt"],
    )
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.srw": "indexe", "vide.srw": "partiel",
        "absent.srw": "ignore", "config.txt": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"powerbuilder-structural"}
    assert next(ligne for ligne in lignes if ligne.file == "config.txt").language == ""
    assert "aucune structure PowerBuilder" in next(
        ligne for ligne in lignes if ligne.file == "vide.srw").raison


def test_fichier_vide_ou_illisible_non_fatal(tmp_path):
    (tmp_path / "vide.srw").write_text("", encoding="utf-8")
    (tmp_path / "bin.srw").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = PowerBuilderSidecar()

    observations = sidecar.index(tmp_path)
    assert isinstance(observations, list)
    assert sidecar.index(tmp_path, fichiers=["absent.srw"]) == []
    lignes = {ligne.file: ligne.statut for ligne in sidecar.couverture(tmp_path)}
    assert lignes == {"vide.srw": "partiel", "bin.srw": "partiel"}


def test_extensions_et_provider():
    sidecar = PowerBuilderSidecar()
    assert sidecar.provider == "powerbuilder"
    assert sidecar.parser == "powerbuilder-structural"
    assert set(sidecar.extensions) == {
        ".srw", ".sru", ".srf", ".srm", ".srs", ".sra", ".srq", ".srd",
        ".srx", ".srj", ".srp", ".pbl"}
