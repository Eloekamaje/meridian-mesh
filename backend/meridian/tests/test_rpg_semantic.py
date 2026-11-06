"""Tests du sidecar RPGLE sémantique : runner injectable, mapping, couverture, réel."""

import pytest

from meridian.adapters.outbound.connectors.rpg_semantic import RpgSemanticSidecar

SOURCE = """\
**FREE
DCL-F CUSTMAST DISK USAGE(*INPUT) KEYED;
DCL-PROC GET_CUSTOMER;
  DCL-S ID INT(10);
  DCL-DS CUSTDATA;
    FIELD1 CHAR(10);
  END-DS;
  CALLP LOAD_DATA(ID);
  EXSR CALC_TOTAL;
  CHAIN (ID) CUSTMAST;
  READ CUSTMAST;
  WRITE CUSTMAST;
  UPDATE CUSTMAST;
  DELETE CUSTMAST;
  EXEC SQL SELECT NAME INTO :NAME FROM CUSTOMER WHERE ID = :ID;
END-PROC;
"""


def _par_kind(observations, kind, symbol=None):
    return [
        o
        for o in observations
        if o.kind == kind and (symbol is None or o.symbol == symbol)
    ]


def _numero(contenu, fragment):
    return next(
        i for i, ligne in enumerate(contenu.splitlines(), 1) if fragment in ligne
    )


def _symbole(regle, cible, debut, fin=None, **extra):
    valeur = {
        "regle": regle,
        "cible": cible,
        "debut": debut,
        "fin": fin if fin is not None else debut,
        "texte": f"{regle} {cible}",
        "tokens": [regle, cible],
        "proc": extra.pop("proc", ""),
    }
    valeur.update(extra)
    return valeur


def _resultat_complet():
    return {
        "statut": "ok",
        "free": True,
        "tokens": [{"type": "ID", "texte": "CUSTMAST", "ligne": 2, "colonne": 6}],
        "noeuds": [{"regle": "r", "debut": 1, "fin": 18, "texte": "**FREE ..."}],
        "symboles": [
            _symbole("fspec", "CUSTMAST", 2),
            _symbole("freeBeginProcedure", "GET_CUSTOMER", 3),
            _symbole("dspec", "ID", 4, proc="GET_CUSTOMER"),
            _symbole("dcl_ds", "CUSTDATA", 5, 7, proc="GET_CUSTOMER"),
            _symbole("dcl_ds_field", "FIELD1", 6, proc="GET_CUSTOMER"),
            _symbole("op_callp", "LOAD_DATA", 8, proc="GET_CUSTOMER"),
            _symbole("op_exsr", "CALC_TOTAL", 9, proc="GET_CUSTOMER"),
            _symbole(
                "op_chain", "CUSTMAST", 10, proc="GET_CUSTOMER", operation="CHAIN"
            ),
            _symbole("op_read", "CUSTMAST", 11, proc="GET_CUSTOMER", operation="READ"),
            _symbole(
                "op_write", "CUSTMAST", 12, proc="GET_CUSTOMER", operation="WRITE"
            ),
            _symbole(
                "op_update", "CUSTMAST", 13, proc="GET_CUSTOMER", operation="UPDATE"
            ),
            _symbole(
                "op_delete", "CUSTMAST", 14, proc="GET_CUSTOMER", operation="DELETE"
            ),
            _symbole(
                "exec_sql",
                "CUSTOMER",
                15,
                proc="GET_CUSTOMER",
                operation="SELECT",
                table="CUSTOMER",
            ),
        ],
        "erreurs": [],
    }


def test_mapping_runner_factice(tmp_path):
    (tmp_path / "demo.rpgle").write_text(SOURCE, encoding="utf-8")
    vus = []

    def runner(chemin):
        vus.append(chemin.name)
        return _resultat_complet()

    sidecar = RpgSemanticSidecar(runner=runner)
    observations = sidecar.index(tmp_path)
    assert vus == ["demo.rpgle"]

    fichier = _par_kind(observations, "rpg_file", "CUSTMAST")[0]
    assert fichier.start == fichier.end == _numero(SOURCE, "DCL-F CUSTMAST")
    assert fichier.provider == "rpg-semantic"
    assert fichier.parser == "rpgleparser-antlr"
    assert fichier.parser_version == "1.0.0"
    assert fichier.language == "rpg"
    assert fichier.file == "demo.rpgle"
    assert fichier.status == "extracted"
    assert fichier.attributes["rule"] == "fspec"
    assert fichier.attributes["tokens"] == ["fspec", "CUSTMAST"]
    assert fichier.attributes["cible"] == "CUSTMAST"
    assert fichier.attributes["file"] == "CUSTMAST"

    procedure = _par_kind(observations, "rpg_proc", "GET_CUSTOMER")[0]
    assert procedure.start == _numero(SOURCE, "DCL-PROC GET_CUSTOMER")
    assert procedure.attributes["rule"] == "freeBeginProcedure"
    assert procedure.attributes["proc"] == "GET_CUSTOMER"

    identifiant = _par_kind(observations, "rpg_var", "ID")[0]
    assert identifiant.start == _numero(SOURCE, "DCL-S ID")
    assert identifiant.attributes["rule"] == "dspec"
    assert identifiant.attributes["proc"] == "GET_CUSTOMER"

    structure = _par_kind(observations, "rpg_data_structure", "CUSTDATA")[0]
    assert structure.attributes["proc"] == "GET_CUSTOMER"
    assert _par_kind(observations, "rpg_var", "FIELD1")[0].attributes["rule"] == (
        "dcl_ds_field"
    )

    appel = _par_kind(observations, "rpg_call", "LOAD_DATA")[0]
    assert appel.start == _numero(SOURCE, "CALLP LOAD_DATA")
    assert appel.attributes["target"] == "LOAD_DATA"
    assert appel.attributes["cible"] == "LOAD_DATA"
    assert appel.attributes["proc"] == "GET_CUSTOMER"
    assert (
        _par_kind(observations, "rpg_call", "CALC_TOTAL")[0].attributes["target"]
        == "CALC_TOTAL"
    )

    operations = {o.symbol: o for o in _par_kind(observations, "rpg_operation")}
    assert set(operations) == {"CHAIN", "READ", "WRITE", "UPDATE", "DELETE"}
    assert operations["CHAIN"].attributes["operation"] == "CHAIN"
    assert operations["CHAIN"].attributes["file"] == "CUSTMAST"
    assert operations["CHAIN"].attributes["cible"] == "CUSTMAST"
    assert operations["CHAIN"].attributes["proc"] == "GET_CUSTOMER"

    sql = _par_kind(observations, "rpg_sql", "SELECT")[0]
    assert sql.start == _numero(SOURCE, "EXEC SQL SELECT")
    assert sql.attributes["operation"] == "SELECT"
    assert sql.attributes["table"] == "CUSTOMER"
    assert sql.attributes["cible"] == "CUSTOMER"
    assert sql.attributes["rule"] == "exec_sql"
    assert sql.attributes["proc"] == "GET_CUSTOMER"


def test_couverture_complete_partielle_et_non_supporte(tmp_path):
    (tmp_path / "ok.rpgle").write_text("DCL-F A;", encoding="utf-8")
    (tmp_path / "partiel.rpg").write_text("DCL-PROC X;", encoding="utf-8")
    (tmp_path / "vide.rpg").write_text("", encoding="utf-8")
    (tmp_path / "config.xml").write_text("<root/>", encoding="utf-8")

    def runner(chemin):
        if chemin.name == "ok.rpgle":
            return {"statut": "ok", "symboles": [_symbole("fspec", "A", 1)]}
        if chemin.name == "partiel.rpg":
            return {
                "statut": "partiel",
                "symboles": [_symbole("dspec", "X", 1)],
                "erreurs": [{"ligne": 1, "colonne": 2, "message": "parse partiel"}],
            }
        return {"statut": "ok", "symboles": [], "erreurs": []}

    sidecar = RpgSemanticSidecar(runner=runner)
    observations = sidecar.index(tmp_path)
    assert {o.file for o in observations} == {"ok.rpgle", "partiel.rpg"}

    lignes = sidecar.couverture(
        tmp_path,
        fichiers=["ok.rpgle", "partiel.rpg", "vide.rpg", "absent.rpg", "config.xml"],
    )
    statuts = {ligne.file: ligne.statut for ligne in lignes}
    assert statuts == {
        "ok.rpgle": "indexe",
        "partiel.rpg": "partiel",
        "vide.rpg": "partiel",
        "absent.rpg": "ignore",
        "config.xml": "non_supporte",
    }
    assert {ligne.parser for ligne in lignes} == {"rpgleparser-antlr"}
    assert (
        next(ligne for ligne in lignes if ligne.file == "partiel.rpg").raison
        == "parse partiel"
    )
    assert (
        next(ligne for ligne in lignes if ligne.file == "vide.rpg").raison
        == "aucune structure RPG reconnue"
    )
    assert next(ligne for ligne in lignes if ligne.file == "config.xml").language == ""


def test_runner_defaillant_ou_invalide_ne_leve_jamais(tmp_path):
    (tmp_path / "demo.rpgle").write_text(SOURCE, encoding="utf-8")

    def runner(chemin):
        raise RuntimeError("JVM absente")

    sidecar = RpgSemanticSidecar(runner=runner)
    assert sidecar.index(tmp_path) == []
    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut == "partiel"
    assert "JVM absente" in lignes[0].raison

    for sortie in ("{pas du json", ["pas", "un", "dict"], 42, None):
        assert (
            RpgSemanticSidecar(runner=lambda chemin, valeur=sortie: valeur).index(
                tmp_path
            )
            == []
        )


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    (tmp_path / "a.rpg").write_text("DCL-F FILEA;", encoding="utf-8")
    (tmp_path / "b.rpg").write_text("DCL-F FILEB;", encoding="utf-8")

    def runner(chemin):
        nom = "FILEA" if chemin.name == "a.rpg" else "FILEB"
        return {"statut": "ok", "symboles": [_symbole("fspec", nom, 1)]}

    observations = RpgSemanticSidecar(runner=runner).index(tmp_path, fichiers=["b.rpg"])
    assert {o.file for o in observations} == {"b.rpg"}
    assert _par_kind(observations, "rpg_file", "FILEB")


def test_fichier_vide_ou_binaire_non_fatal(tmp_path):
    (tmp_path / "vide.rpg").write_text("", encoding="utf-8")
    (tmp_path / "bin.rpg").write_bytes(b"\x00\x01\xff\xfe\x00")

    def runner(chemin):
        return {"statut": "ok", "symboles": [], "erreurs": []}

    sidecar = RpgSemanticSidecar(runner=runner)
    assert sidecar.index(tmp_path) == []
    lignes = sidecar.couverture(tmp_path)
    assert {ligne.file: ligne.statut for ligne in lignes} == {
        "vide.rpg": "partiel",
        "bin.rpg": "partiel",
    }


@pytest.mark.skipif(
    not RpgSemanticSidecar.disponible(),
    reason="jars rpgleparser ou classes Analyze.java absents",
)
def test_parseur_reel_rpgle_free(tmp_path):
    (tmp_path / "demo.rpgle").write_text(SOURCE, encoding="utf-8")
    sidecar = RpgSemanticSidecar()

    observations = sidecar.index(tmp_path)
    assert observations
    assert _par_kind(observations, "rpg_file", "CUSTMAST")[0].start == _numero(
        SOURCE, "DCL-F CUSTMAST"
    )
    assert _par_kind(observations, "rpg_proc", "GET_CUSTOMER")[0].start == _numero(
        SOURCE, "DCL-PROC GET_CUSTOMER"
    )
    assert _par_kind(observations, "rpg_var", "ID")[0].attributes["proc"] == (
        "GET_CUSTOMER"
    )
    assert (
        _par_kind(observations, "rpg_call", "LOAD_DATA")[0].attributes["target"]
        == "LOAD_DATA"
    )
    chain = _par_kind(observations, "rpg_operation", "CHAIN")[0]
    assert chain.attributes["file"] == "CUSTMAST"
    assert chain.attributes["proc"] == "GET_CUSTOMER"
    sql = _par_kind(observations, "rpg_sql", "SELECT")[0]
    assert sql.attributes["table"] == "CUSTOMER"
    assert sql.attributes["rule"] == "exec_sql"

    lignes = sidecar.couverture(tmp_path)
    assert lignes[0].statut in {"indexe", "partiel"}
