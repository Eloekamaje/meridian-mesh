"""Non-régression de bout en bout sur le corpus legacy de référence.

Le corpus est entièrement local : aucun appel CBM, aucune base, aucun réseau.
Les liens attendus sont ceux que les sidecars doivent produire seuls.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from meridian.adapters.outbound.connectors import legacy_index
from meridian.adapters.outbound.connectors.legacy_index import indexer_legacy

CORPUS = Path(__file__).resolve().parent / "fixtures" / "legacy_corpus"
PROVIDERS = ["jsp", "java", "java-descriptor", "cobol", "jcl", "sql",
             "abap", "rpg", "pli", "oracle-forms", "powerbuilder"]
PROVIDERS_CORPUS = {"jsp", "java", "java-descriptor", "cobol", "jcl", "sql"}
FICHIERS_ATTENDUS = {
    "README.md",
    "web/WEB-INF/web.xml",
    "web/client.jsp",
    "src/main/java/com/acme/ClientServlet.java",
    "src/main/java/com/acme/web/ClientController.java",
    "src/main/java/com/acme/service/ClientService.java",
    "src/main/java/com/acme/domain/Client.java",
    "src/main/resources/META-INF/ejb-jar.xml",
    "cobol/PROG.cbl",
    "cobol/SOUSPROG.cbl",
    "cobol/CLIENT.cpy",
    "jcl/LOAD.jcl",
    "sql/schema.sql",
}


@pytest.fixture(scope="module")
def rapport():
    return indexer_legacy(str(CORPUS))


def _liens(rapport, kind):
    return [lien for lien in rapport["liens"]["liens"] if lien["kind"] == kind]


def _a_un_lien(rapport, kind, **attendu):
    return any(
        all(lien.get(cle) == valeur for cle, valeur in attendu.items())
        for lien in _liens(rapport, kind)
    )


def _symboles(rapport):
    return {(observation["kind"], observation["symbol"])
            for observation in rapport["observations"]}


def test_tous_les_providers_et_tous_les_fichiers_sont_couverts(rapport):
    assert rapport["providers"] == PROVIDERS
    assert {observation["provider"] for observation in rapport["observations"]} == PROVIDERS_CORPUS

    reels = {chemin.relative_to(CORPUS).as_posix()
             for chemin in CORPUS.rglob("*") if chemin.is_file()}
    assert reels == FICHIERS_ATTENDUS
    assert set(rapport["fichiers_decouverts"]) == reels

    statuts = {ligne["file"]: ligne["statut"] for ligne in rapport["couvertures"]}
    assert set(statuts) == reels
    assert statuts.pop("README.md") == "non_supporte"
    assert all(statut == "indexe" for statut in statuts.values())
    assert rapport["compteurs"]["non_supporte"] == 1
    assert rapport["erreurs"] == []


def test_le_contenu_structurel_du_corpus_est_extrait(rapport):
    symboles = _symboles(rapport)

    assert ("servlet", "ClientServlet") in symboles
    assert ("servlet_mapping", "ClientServlet") in symboles
    assert ("jsp_form", "/clients/save") in symboles
    assert ("jsp_include", "/WEB-INF/header.jspf") in symboles
    assert ("jsp_forward", "/WEB-INF/detail.jsp") in symboles
    assert ("jpa_entity", "Client") in symboles
    assert ("spring_route", "GET /{id}") in symboles
    assert ("ejb", "ClientEJB") in symboles
    assert ("mdb", "ClientMDB") in symboles
    assert ("ejb_ref", "jdbc/client") in symboles
    assert ("cobol_program", "PROG") in symboles
    assert ("cobol_program", "SOUSPROG") in symboles
    assert ("cobol_call", "SOUSPROG") in symboles
    assert ("cobol_copy", "CLIENT") in symboles
    assert ("jcl_program", "PROG") in symboles
    assert ("jcl_dataset", "CLIENT.FILE") in symboles
    assert ("sql_table", "APP.CLIENT") in symboles
    assert ("sql_table", "APP.AGENCE") in symboles
    assert ("sql_column", "APP.CLIENT.AGENCE_ID") in symboles
    assert ("sql_fk", "FK_CLIENT_AGENCE") in symboles
    assert ("sql_view", "APP.VW_CLIENT_AGENCE") in symboles
    assert ("sql_index", "IDX_CLIENT_NOM") in symboles


def test_les_liens_attendus_existent(rapport):
    assert _a_un_lien(
        rapport, "jsp_to_servlet_mapping",
        source_file="web/client.jsp", source_symbol="/clients/save",
        target_file="web/WEB-INF/web.xml",
    )
    assert _a_un_lien(
        rapport, "servlet_mapping_to_servlet",
        source_file="web/WEB-INF/web.xml", target_file="web/WEB-INF/web.xml",
        target_symbol="ClientServlet",
    )
    assert _a_un_lien(
        rapport, "servlet_to_java_type",
        source_file="web/WEB-INF/web.xml",
        target_file="src/main/java/com/acme/ClientServlet.java",
        target_symbol="ClientServlet",
    )
    assert _a_un_lien(
        rapport, "java_to_jpa_entity",
        source_file="src/main/java/com/acme/web/ClientController.java",
        target_file="src/main/java/com/acme/domain/Client.java",
        target_symbol="com.acme.domain.Client",
    )
    assert _a_un_lien(
        rapport, "sql_fk_to_table",
        source_file="sql/schema.sql", source_symbol="FK_CLIENT_AGENCE",
        target_symbol="APP.AGENCE",
    )
    assert _a_un_lien(
        rapport, "cobol_call_to_program",
        source_file="cobol/PROG.cbl", target_file="cobol/SOUSPROG.cbl",
        target_symbol="SOUSPROG",
    )
    assert _a_un_lien(
        rapport, "cobol_copy_to_copybook",
        source_file="cobol/PROG.cbl", target_file="cobol/CLIENT.cpy",
        target_symbol="CLIENT",
    )
    assert _a_un_lien(
        rapport, "jcl_program_to_cobol_program",
        source_file="jcl/LOAD.jcl", target_file="cobol/PROG.cbl",
        target_symbol="PROG",
    )


def test_les_liens_transverses_sql_et_dataset_existent(rapport):
    assert _a_un_lien(
        rapport, "sql_table_to_jpa_table",
        source_symbol="APP.CLIENT",
        target_file="src/main/java/com/acme/domain/Client.java",
        target_symbol="com.acme.domain.Client",
    )
    assert _a_un_lien(
        rapport, "cobol_file_to_jcl_dataset",
        source_file="cobol/PROG.cbl", target_file="jcl/LOAD.jcl",
        target_symbol="CLIENT.FILE",
    )
    assert _a_un_lien(
        rapport, "jcl_dataset_to_cobol_file",
        source_file="jcl/LOAD.jcl", target_file="cobol/PROG.cbl",
        target_symbol="CLIENT-FILE",
    )


def test_le_rapport_est_json_serialisable(rapport):
    relu = json.loads(json.dumps(rapport, ensure_ascii=False))

    assert relu["providers"] == PROVIDERS
    assert relu["liens"]["total"] == len(relu["liens"]["liens"])
    assert relu["liens"]["total"] == sum(relu["liens"]["par_kind"].values())
    assert set(relu["liens"]["par_statut"]) == {"linked", "inferred", "ambiguous"}
    assert set(relu["compteurs"]) <= {"indexe", "partiel", "non_supporte",
                                      "ignore", "tronque", "conflit"}
    assert all(set(lien) == {
        "kind", "source_file", "source_symbol", "target_file", "target_symbol",
        "attributes", "confidence", "status", "evidence",
    } for lien in relu["liens"]["liens"])


def test_corpus_sans_cbm_sans_base_et_sans_reseau(monkeypatch):
    def refus(*args, **kwargs):
        raise AssertionError("le corpus ne doit ouvrir aucune connexion réseau")

    monkeypatch.setattr(socket, "socket", refus)
    monkeypatch.setattr(socket, "create_connection", refus)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    monkeypatch.setattr(legacy_index, "CbmObservations", refus)

    rapport = indexer_legacy(str(CORPUS))

    assert rapport["providers"] == PROVIDERS
    assert "cbm" not in rapport["providers"]
    assert rapport["erreurs"] == []
    assert rapport["liens"]["total"] > 0
