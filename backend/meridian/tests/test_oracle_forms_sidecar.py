"""Tests du sidecar Oracle Forms : XML, lignes, binaires et entités externes."""
from meridian.adapters.outbound.connectors.oracle_forms import OracleFormsSidecar


MODULE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<FormModule Name="CLIENTS" >
  <Block Name="CLIENT" QueryDataSourceName="CLIENT" >
    <Item Name="CLIENT_ID" />
    <Item Name="CLIENT_NAME" />
    <Trigger Name="WHEN-BUTTON-PRESSED" >
      <TriggerText>BEGIN NULL; END;</TriggerText>
    </Trigger>
    <Relation Name="CLIENT_REL" JoinCondition="CLIENT.ID = OTHER.ID" />
  </Block>
  <LOV Name="CLIENT_LOV" RecordGroupName="CLIENT_RG" />
  <RecordGroup Name="CLIENT_RG" Query="SELECT ID, NAME FROM CLIENT" >
    <RecordGroupColumn Name="ID" />
  </RecordGroup>
  <Canvas Name="CANVAS1" />
  <Window Name="WINDOW1" />
</FormModule>
"""


def _par_kind(observations, kind, symbol=None):
    return [o for o in observations
            if o.kind == kind and (symbol is None or o.symbol == symbol)]


def _numero(contenu, fragment):
    return next(i for i, ligne in enumerate(contenu.splitlines(), 1)
                if fragment in ligne)


def test_export_xml_complet_et_lignes(tmp_path):
    (tmp_path / "clients.xml").write_text(MODULE_XML, encoding="utf-8")
    observations = OracleFormsSidecar().index(tmp_path)

    module = _par_kind(observations, "forms_module", "CLIENTS")[0]
    assert module.start == _numero(MODULE_XML, "<FormModule")
    assert module.end == _numero(MODULE_XML, "</FormModule>")
    assert module.provider == "oracle-forms"
    assert module.parser == "oracle-forms-xml"
    assert module.parser_version == "1.0"
    assert module.language == "oracle-forms"
    assert module.file == "clients.xml"
    assert module.status == "extracted"
    assert module.attributes == {"module": "CLIENTS"}

    bloc = _par_kind(observations, "forms_block", "CLIENT")[0]
    assert (bloc.start, bloc.end) == (
        _numero(MODULE_XML, "<Block"), _numero(MODULE_XML, "</Block>"))
    assert bloc.attributes == {
        "module": "CLIENTS", "block": "CLIENT", "table": "CLIENT"}

    identifiant = _par_kind(observations, "forms_item", "CLIENT_ID")[0]
    assert identifiant.start == identifiant.end == _numero(MODULE_XML, "CLIENT_ID")
    assert identifiant.attributes == {
        "module": "CLIENTS", "block": "CLIENT", "item": "CLIENT_ID"}
    assert _par_kind(observations, "forms_item", "CLIENT_NAME")[0].attributes == {
        "module": "CLIENTS", "block": "CLIENT", "item": "CLIENT_NAME"}

    declencheur = _par_kind(observations, "forms_trigger", "WHEN-BUTTON-PRESSED")[0]
    assert (declencheur.start, declencheur.end) == (
        _numero(MODULE_XML, "<Trigger"), _numero(MODULE_XML, "</Trigger>"))
    assert declencheur.attributes == {
        "module": "CLIENTS", "block": "CLIENT", "trigger": "WHEN-BUTTON-PRESSED"}

    relation = _par_kind(observations, "forms_relation", "CLIENT_REL")[0]
    assert relation.start == relation.end == _numero(MODULE_XML, "<Relation")
    assert relation.attributes == {
        "module": "CLIENTS", "block": "CLIENT", "relation": "CLIENT_REL"}

    lov = _par_kind(observations, "forms_lov", "CLIENT_LOV")[0]
    assert lov.start == lov.end == _numero(MODULE_XML, "<LOV")
    assert lov.attributes == {"module": "CLIENTS"}

    groupe = _par_kind(observations, "forms_record_group", "CLIENT_RG")[0]
    assert (groupe.start, groupe.end) == (
        _numero(MODULE_XML, "<RecordGroup"), _numero(MODULE_XML, "</RecordGroup>"))
    assert groupe.attributes == {
        "module": "CLIENTS", "sql": "SELECT ID, NAME FROM CLIENT"}

    assert len(observations) == 8
    assert not _par_kind(observations, "forms_canvas")
    assert not _par_kind(observations, "forms_window")


def test_trigger_sous_item_et_requete_enfant(tmp_path):
    contenu = """<FormModule Name="M">
  <Block Name="B">
    <Item Name="I">
      <Trigger Name="WHEN-NEW-ITEM-INSTANCE"/>
    </Item>
  </Block>
  <RecordGroup Name="RG">
    <Query>SELECT X FROM T</Query>
  </RecordGroup>
</FormModule>
"""
    (tmp_path / "nested.xml").write_text(contenu, encoding="utf-8")
    observations = OracleFormsSidecar().index(tmp_path)

    declencheur = _par_kind(observations, "forms_trigger", "WHEN-NEW-ITEM-INSTANCE")[0]
    assert declencheur.attributes == {
        "module": "M", "block": "B", "item": "I",
        "trigger": "WHEN-NEW-ITEM-INSTANCE"}
    groupe = _par_kind(observations, "forms_record_group", "RG")[0]
    assert groupe.attributes == {"module": "M", "sql": "SELECT X FROM T"}


def test_xml_invalide_non_fatal(tmp_path):
    (tmp_path / "invalide.xml").write_text(
        "<FormModule><Block></FormModule>", encoding="utf-8")
    sidecar = OracleFormsSidecar()

    assert sidecar.index(tmp_path) == []
    lignes = sidecar.couverture(tmp_path)
    assert len(lignes) == 1
    assert lignes[0].file == "invalide.xml"
    assert lignes[0].statut == "partiel"
    assert "XML invalide" in lignes[0].raison


def test_fmb_fmx_binaires_partiels_sans_observation(tmp_path):
    (tmp_path / "legacy.fmb").write_bytes(b"\x00\x01\xff\xfe\x00")
    (tmp_path / "legacy.fmx").write_bytes(b"\x00\x01\xff\xfe\x00")
    sidecar = OracleFormsSidecar()

    assert sidecar.index(tmp_path) == []
    assert sidecar.index(tmp_path, fichiers=["legacy.fmb"]) == []
    lignes = {ligne.file: ligne for ligne in sidecar.couverture(tmp_path)}
    assert set(lignes) == {"legacy.fmb", "legacy.fmx"}
    assert {ligne.statut for ligne in lignes.values()} == {"partiel"}
    assert all("binaire Oracle Forms" in ligne.raison for ligne in lignes.values())


def test_couverture_indexe_partiel_ignore_non_supporte(tmp_path):
    (tmp_path / "ok.xml").write_text(MODULE_XML, encoding="utf-8")
    (tmp_path / "notes.xml").write_text("<notes/>", encoding="utf-8")
    (tmp_path / "config.txt").write_text("rien", encoding="utf-8")
    sidecar = OracleFormsSidecar()

    assert {o.file for o in sidecar.index(tmp_path)} == {"ok.xml"}
    lignes = sidecar.couverture(
        tmp_path, fichiers=["ok.xml", "notes.xml", "absent.xml", "config.txt"])
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.xml": "indexe", "notes.xml": "partiel",
        "absent.xml": "ignore", "config.txt": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"oracle-forms-xml"}
    assert next(ligne for ligne in lignes if ligne.file == "config.txt").language == ""
    assert next(ligne for ligne in lignes if ligne.file == "notes.xml").raison == (
        "aucun module Oracle Forms reconnu")


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.xml").write_text(
        '<FormModule Name="A"><Block Name="BA"/></FormModule>', encoding="utf-8")
    (tmp_path / "b.xml").write_text(
        '<FormModule Name="B"><Block Name="BB"/></FormModule>', encoding="utf-8")

    observations = OracleFormsSidecar().index(tmp_path, fichiers=["b.xml"])
    assert {o.file for o in observations} == {"b.xml"}
    assert _par_kind(observations, "forms_module", "B")
    assert _par_kind(observations, "forms_block", "BB")


def test_doctype_externe_masque_sans_reseau(tmp_path):
    contenu = """<!DOCTYPE FormModule SYSTEM "http://127.0.0.1:9/forms.dtd">
<FormModule Name="SANS_RESEAU">
  <Block Name="B"/>
</FormModule>
"""
    (tmp_path / "dtd.xml").write_text(contenu, encoding="utf-8")
    observations = OracleFormsSidecar().index(tmp_path)

    assert _par_kind(observations, "forms_module", "SANS_RESEAU")
    assert _par_kind(observations, "forms_block", "B")


def test_entite_externe_non_resolue_et_raison_sans_secret(tmp_path):
    contenu = """<!DOCTYPE FormModule [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<FormModule Name="XXE"><Block Name="&xxe;"/></FormModule>
"""
    (tmp_path / "xxe.xml").write_text(contenu, encoding="utf-8")
    sidecar = OracleFormsSidecar()

    assert sidecar.index(tmp_path) == []
    ligne = sidecar.couverture(tmp_path, fichiers=["xxe.xml"])[0]
    assert ligne.statut == "partiel"
    assert "/etc/passwd" not in ligne.raison


def test_trigger_extrait_tables_et_appels_de_formulaire(tmp_path):
    contenu = """<FormModule Name="M">
  <Block Name="B">
    <Trigger Name="WHEN-BUTTON-PRESSED">
      <TriggerText>SELECT * FROM CLIENT WHERE ID = :B.ID; CALL_FORM('DETAIL');</TriggerText>
    </Trigger>
  </Block>
</FormModule>
"""
    (tmp_path / "trigger.xml").write_text(contenu, encoding="utf-8")
    observations = OracleFormsSidecar().index(tmp_path)

    sql = _par_kind(observations, "forms_sql", "CLIENT")
    appel = _par_kind(observations, "forms_call", "DETAIL")
    assert len(sql) == 1 and sql[0].attributes["table"] == "CLIENT"
    assert sql[0].attributes["trigger"] == "WHEN-BUTTON-PRESSED"
    assert len(appel) == 1 and appel[0].attributes["target"] == "DETAIL"
