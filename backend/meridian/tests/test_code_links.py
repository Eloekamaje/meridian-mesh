"""Contrat des liens déterministes entre observations d'indexation legacy."""
import json

from meridian.adapters.outbound.connectors.cobol import CobolSidecar
from meridian.adapters.outbound.connectors.java_descriptors import JavaDescriptorSidecar
from meridian.adapters.outbound.connectors.jcl import JclSidecar
from meridian.adapters.outbound.connectors.jsp import JspSidecar
from meridian.adapters.outbound.connectors.sql_schema import SqlSchemaSidecar
from meridian.application.code_links import Link, lier, rapport_liens
from meridian.domain.code_index import Observation


def _ecrire(base, relatif, contenu):
    chemin = base / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _obs(kind, symbol, file, attributes=None, *, language="java", provider="java-source",
         start=1, end=1, status="extracted", confidence=1.0):
    return Observation(
        provider=provider, parser="test", parser_version="1", file=file,
        language=language, kind=kind, symbol=symbol, start=start, end=end,
        attributes=attributes or {}, confidence=confidence, status=status,
    )


def _de_kind(links, kind):
    return [lien for lien in links if lien.kind == kind]


WEB_XML = """<web-app>
  <servlet>
    <servlet-name>clientServlet</servlet-name>
    <servlet-class>com.acme.ClientServlet</servlet-class>
  </servlet>
  <servlet>
    <servlet-name>otherServlet</servlet-name>
    <servlet-class>com.acme.OtherServlet</servlet-class>
  </servlet>
  <servlet-mapping>
    <servlet-name>clientServlet</servlet-name>
    <url-pattern>*.do</url-pattern>
  </servlet-mapping>
  <servlet-mapping>
    <servlet-name>otherServlet</servlet-name>
    <url-pattern>/other/*</url-pattern>
  </servlet-mapping>
</web-app>
"""

PAGE_JSP = """<form action="/ctx/clients/save.do" method="post"></form>
<a href="/ctx/other/list">Autres</a>
<jsp:include page="/ctx/clients/list.do" />
"""


def _observations_web(base):
    return (JspSidecar().index(str(base)) + JavaDescriptorSidecar().index(str(base)) +
            [_obs("java_type", "com.acme.ClientServlet", "src/ClientServlet.java"),
             _obs("java_type", "com.acme.OtherServlet", "src/OtherServlet.java")])


def test_jsp_vers_servlet_mapping_puis_servlet_puis_classe_java(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    _ecrire(tmp_path, "page.jsp", PAGE_JSP)

    links = lier(_observations_web(tmp_path))

    formulaires = [lien for lien in _de_kind(links, "jsp_to_servlet_mapping")
                   if lien.source_symbol == "/ctx/clients/save.do"]
    assert len(formulaires) == 1
    lien = formulaires[0]
    assert (lien.source_file, lien.target_file) == ("page.jsp", "web.xml")
    assert lien.attributes["servlet_name"] == "clientServlet"
    assert lien.attributes["url_pattern"] == "*.do"
    assert lien.attributes["http_method"] == "POST"
    assert lien.status == "linked"
    assert lien.confidence == 1.0

    mapping = next(lien for lien in _de_kind(links, "servlet_mapping_to_servlet")
                   if lien.source_symbol == "clientServlet")
    assert mapping.target_symbol == "clientServlet"

    servlet = next(lien for lien in _de_kind(links, "servlet_to_java_type")
                   if lien.source_symbol == "clientServlet")
    assert servlet.target_file == "src/ClientServlet.java"
    assert servlet.target_symbol == "com.acme.ClientServlet"
    assert servlet.attributes["match"] == "fqn"


def test_jsp_normalise_contexte_et_mapping_par_chemin(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    _ecrire(tmp_path, "page.jsp", '<a href="/ctx/other/list">Autres</a>')

    lien = _de_kind(lier(_observations_web(tmp_path)), "jsp_to_servlet_mapping")[0]

    assert lien.attributes["servlet_name"] == "otherServlet"
    assert lien.attributes["url_pattern"] == "/other/*"
    assert lien.attributes["cible"] == "/ctx/other/list"
    assert lien.confidence < 1.0


def test_jsp_avec_deux_mappings_possibles_ne_produit_aucun_lien(tmp_path):
    _ecrire(tmp_path, "web.xml", """<web-app>
  <servlet><servlet-name>a</servlet-name><servlet-class>com.acme.A</servlet-class></servlet>
  <servlet><servlet-name>b</servlet-name><servlet-class>com.acme.B</servlet-class></servlet>
  <servlet-mapping><servlet-name>a</servlet-name><url-pattern>*.do</url-pattern></servlet-mapping>
  <servlet-mapping><servlet-name>b</servlet-name><url-pattern>*.do</url-pattern></servlet-mapping>
</web-app>
""")
    _ecrire(tmp_path, "page.jsp", '<form action="/save.do"></form>')

    links = lier(JspSidecar().index(str(tmp_path)) +
                 JavaDescriptorSidecar().index(str(tmp_path)))

    assert _de_kind(links, "jsp_to_servlet_mapping") == []


def test_mapping_sans_servlet_ou_servlet_sans_classe_ne_produit_aucun_lien(tmp_path):
    _ecrire(tmp_path, "web.xml", """<web-app>
  <servlet-mapping>
    <servlet-name>orphelin</servlet-name>
    <url-pattern>/orphelin</url-pattern>
  </servlet-mapping>
</web-app>
""")
    _ecrire(tmp_path, "page.jsp", '<form action="/orphelin"></form>')

    links = lier(JspSidecar().index(str(tmp_path)) +
                 JavaDescriptorSidecar().index(str(tmp_path)))

    assert _de_kind(links, "jsp_to_servlet_mapping")
    assert _de_kind(links, "servlet_mapping_to_servlet") == []
    assert _de_kind(links, "servlet_to_java_type") == []


def test_jsp_formulaire_vers_spring_route_sans_deviner_la_methode():
    route = _obs("spring_route", "/clients/{id}", "src/ClientController.java", {
        "path": "/clients/{id}", "methods": ["GET", "POST"],
        "controller": "com.acme.ClientController",
    })

    sans_methode = _obs("jsp_form", "form", "page.jsp", {"action": "/app/clients/42"})
    lien = _de_kind(lier([sans_methode, route]), "jsp_to_spring_route")[0]
    assert lien.attributes["http_method"] == ""
    assert lien.attributes["method_verified"] is False
    assert lien.status == "inferred"

    post = _obs("jsp_form", "form", "page.jsp",
                {"action": "/app/clients/42", "method": "post"})
    lien = _de_kind(lier([post, route]), "jsp_to_spring_route")[0]
    assert lien.attributes["http_method"] == "POST"
    assert lien.attributes["method_verified"] is True
    assert lien.status == "linked"

    delete = _obs("jsp_form", "form", "page.jsp",
                  {"action": "/app/clients/42", "method": "delete"})
    assert _de_kind(lier([delete, route]), "jsp_to_spring_route") == []


def test_jsp_vers_spring_route_ambigue_non_lie():
    formulaire = _obs("jsp_form", "form", "page.jsp", {"action": "/clients/42"})
    routes = [
        _obs("spring_route", "/clients/{id}", "src/A.java", {
            "path": "/clients/{id}", "controller": "com.acme.A"}),
        _obs("spring_route", "/clients/{id}", "src/B.java", {
            "path": "/clients/{id}", "controller": "com.acme.B"}),
    ]

    assert _de_kind(lier([formulaire, *routes]), "jsp_to_spring_route") == []


def test_servlet_vers_java_type_par_nom_simple_ou_fqn():
    servlet = _obs("servlet", "clientServlet", "web.xml", {
        "name": "clientServlet", "class": "com.acme.ClientServlet"})
    type_simple = _obs("java_type", "ClientServlet", "src/ClientServlet.java",
                       {"fqn": "com.acme.ClientServlet"})

    lien = _de_kind(lier([servlet, type_simple]), "servlet_to_java_type")[0]
    assert lien.target_symbol == "ClientServlet"
    assert lien.attributes["match"] == "fqn"

    servlet_simple = _obs("servlet", "clientServlet", "web.xml", {
        "name": "clientServlet", "class": "ClientServlet"})
    doublon = _obs("java_type", "ClientServlet", "src/autre/ClientServlet.java",
                   {"fqn": "org.autre.ClientServlet"})
    assert _de_kind(lier([servlet_simple, type_simple, doublon]),
                    "servlet_to_java_type") == []


DDL = """CREATE TABLE APP.CLIENTS (
  ID NUMBER NOT NULL,
  NAME VARCHAR2(40),
  PRIMARY KEY (ID)
);
CREATE TABLE APP.ORDERS (
  ID NUMBER NOT NULL,
  CLIENT_ID NUMBER,
  CONSTRAINT FK_ORDERS_CLIENT FOREIGN KEY (CLIENT_ID) REFERENCES APP.CLIENTS (ID)
);
"""


def test_spring_et_service_vers_jpa_par_import_et_champ():
    entite = _obs("java_entity", "com.acme.Client", "src/Client.java", {"table": "CLIENTS"})
    controleur = _obs("java_type", "com.acme.ClientController", "src/ClientController.java", {
        "stereotype": "RestController", "imports": ["com.acme.Client"]})
    route = _obs("spring_route", "/clients", "src/ClientController.java", {
        "path": "/clients", "methods": ["POST"],
        "controller": "com.acme.ClientController"})

    liens = lier([entite, controleur, route])
    par_import = [lien for lien in _de_kind(liens, "java_to_jpa_entity")
                  if lien.source_symbol == "com.acme.ClientController"]
    assert len(par_import) == 1
    assert par_import[0].target_symbol == "com.acme.Client"
    assert par_import[0].attributes["table"] == "CLIENTS"
    assert par_import[0].attributes["via"] == ["import"]

    par_route = [lien for lien in _de_kind(liens, "java_to_jpa_entity")
                 if lien.source_symbol == "/clients"]
    assert len(par_route) == 1
    assert par_route[0].target_symbol == "com.acme.Client"

    service = _obs("java_type", "com.acme.ClientService", "src/ClientService.java", {
        "stereotype": "Service",
        "fields": [{"name": "client", "type": "Client"}]})
    par_champ = [lien for lien in _de_kind(lier([entite, service]), "java_to_jpa_entity")]
    assert par_champ
    assert par_champ[0].attributes["via"] == ["field"]

    sans_reference = _obs("java_type", "com.acme.Libre", "src/Libre.java",
                          {"stereotype": "Service"})
    assert _de_kind(lier([entite, sans_reference]), "java_to_jpa_entity") == []


def test_sql_fk_vers_table_et_colonne_cibles(tmp_path):
    _ecrire(tmp_path, "schema.sql", DDL)

    liens = lier(SqlSchemaSidecar().index(str(tmp_path)))

    tables = _de_kind(liens, "sql_fk_to_table")
    colonnes = _de_kind(liens, "sql_fk_to_column")
    assert len(tables) == 1
    assert len(colonnes) == 1
    assert tables[0].source_symbol == "FK_ORDERS_CLIENT"
    assert tables[0].target_symbol == "APP.CLIENTS"
    assert tables[0].attributes["table_cible"] == "CLIENTS"
    assert colonnes[0].target_symbol == "APP.CLIENTS.ID"
    assert colonnes[0].attributes["colonne_cible"] == "ID"


def test_sql_fk_cible_absente_ou_ambigue_non_liee(tmp_path):
    _ecrire(tmp_path, "absent.sql", """CREATE TABLE APP.ORDERS (
  ID NUMBER,
  CLIENT_ID NUMBER,
  CONSTRAINT FK_ABSENT FOREIGN KEY (CLIENT_ID) REFERENCES APP.INCONNUE (ID)
);
""")
    assert _de_kind(lier(SqlSchemaSidecar().index(str(tmp_path))), "sql_fk_to_table") == []

    autre = tmp_path / "autre"
    _ecrire(autre, "a.sql", "CREATE TABLE APP.CLIENTS (ID NUMBER);")
    _ecrire(autre, "b.sql", "CREATE TABLE AUTRE.CLIENTS (ID NUMBER);")
    _ecrire(autre, "fk.sql", """CREATE TABLE APP.ORDERS (
  ID NUMBER, CLIENT_ID NUMBER,
  CONSTRAINT FK_AMBIGU FOREIGN KEY (CLIENT_ID) REFERENCES APP.CLIENTS (ID)
);
""")
    liens = lier(SqlSchemaSidecar().index(str(autre)))
    assert _de_kind(liens, "sql_fk_to_table") == []
    assert _de_kind(liens, "sql_fk_to_column") == []


COBOL_MAIN = """IDENTIFICATION DIVISION.
PROGRAM-ID. MAIN.
ENVIRONMENT DIVISION.
INPUT-OUTPUT SECTION.
FILE-CONTROL.
    SELECT CLIENT-FILE ASSIGN TO "APP.CLIENTS".
DATA DIVISION.
FILE SECTION.
FD CLIENT-FILE.
01 CLIENT-REC PIC X(10).
PROCEDURE DIVISION.
    CALL "SUBPROG".
    CALL "ABSENT".
    COPY COMMON.
"""


def test_cobol_call_et_copy_vers_programme_et_copybook(tmp_path):
    _ecrire(tmp_path, "MAIN.cbl", COBOL_MAIN)
    _ecrire(tmp_path, "SUBPROG.cbl", "IDENTIFICATION DIVISION.\nPROGRAM-ID. SUBPROG.\n")
    _ecrire(tmp_path, "COMMON.cpy", "01 COMMON-FIELD PIC X(5).\n")

    liens = lier(CobolSidecar().index(str(tmp_path)))

    appels = _de_kind(liens, "cobol_call_to_program")
    assert [(lien.source_symbol, lien.target_symbol) for lien in appels] == [
        ("SUBPROG", "SUBPROG")]
    copies = _de_kind(liens, "cobol_copy_to_copybook")
    assert len(copies) == 1
    assert copies[0].target_file == "COMMON.cpy"
    assert copies[0].target_symbol == "COMMON"

    _ecrire(tmp_path, "AUTRE/SUBPROG.cbl",
            "IDENTIFICATION DIVISION.\nPROGRAM-ID. SUBPROG.\n")
    assert _de_kind(lier(CobolSidecar().index(str(tmp_path))),
                    "cobol_call_to_program") == []


def test_jcl_programme_dataset_et_proc_vers_cobol(tmp_path):
    _ecrire(tmp_path, "MAIN.cbl", COBOL_MAIN)
    _ecrire(tmp_path, "SUBPROG.cbl", "IDENTIFICATION DIVISION.\nPROGRAM-ID. SUBPROG.\n")
    _ecrire(tmp_path, "COMMON.cpy", "01 COMMON-FIELD PIC X(5).\n")
    _ecrire(tmp_path, "LOAD.jcl", """//LOADJOB JOB (ACCT),'LOAD'
//STEP1 EXEC PGM=MAIN
//INFILE DD DSN=APP.CLIENTS,DISP=SHR
//STEP2 EXEC PROC=MYPROC
""")
    _ecrire(tmp_path, "MYPROC.proc", "//MYPROC PROC\n")

    observations = (CobolSidecar().index(str(tmp_path)) +
                    JclSidecar().index(str(tmp_path)))
    liens = lier(observations)

    programmes = _de_kind(liens, "jcl_program_to_cobol_program")
    assert [(lien.source_symbol, lien.target_symbol) for lien in programmes] == [
        ("MAIN", "MAIN")]
    vers_cobol = _de_kind(liens, "jcl_dataset_to_cobol_file")
    assert [(lien.source_symbol, lien.target_symbol) for lien in vers_cobol] == [
        ("APP.CLIENTS", "CLIENT-FILE")]
    vers_jcl = _de_kind(liens, "cobol_file_to_jcl_dataset")
    assert [(lien.source_symbol, lien.target_symbol) for lien in vers_jcl] == [
        ("CLIENT-FILE", "APP.CLIENTS")]
    procs = _de_kind(liens, "jcl_proc_to_jcl_proc")
    assert len(procs) == 1
    assert (procs[0].source_symbol, procs[0].target_file) == ("MYPROC", "MYPROC.proc")


def test_sql_table_et_jpa_table_par_nom_normalise(tmp_path):
    _ecrire(tmp_path, "schema.sql", DDL)
    entite = _obs("java_entity", "com.acme.Client", "src/Client.java", {"table": "clients"})

    liens = lier(SqlSchemaSidecar().index(str(tmp_path)) + [entite])
    tables = _de_kind(liens, "sql_table_to_jpa_table")
    assert len(tables) == 1
    assert (tables[0].source_symbol, tables[0].target_symbol) == (
        "APP.CLIENTS", "com.acme.Client")
    assert tables[0].attributes["table"] == "CLIENTS"
    assert tables[0].attributes["schema_retire"] is True

    sans_table = _obs("java_entity", "com.acme.Facture", "src/Facture.java")
    assert _de_kind(lier(SqlSchemaSidecar().index(str(tmp_path)) + [sans_table]),
                    "sql_table_to_jpa_table") == []


def test_jpa_table_sans_correspondance_sql_non_liee(tmp_path):
    _ecrire(tmp_path, "schema.sql", "CREATE TABLE APP.CLIENTS (ID NUMBER);")
    entite = _obs("java_entity", "com.acme.Facture", "src/Facture.java",
                  {"table": "FACTURES"})

    assert _de_kind(lier(SqlSchemaSidecar().index(str(tmp_path)) + [entite]),
                    "sql_table_to_jpa_table") == []


def test_ambiguite_de_la_source_est_signalee_sur_le_lien():
    formulaire = _obs("jsp_form", "form", "page.jsp", {"action": "/save.do"},
                      status="ambiguous")
    mapping = _obs("servlet_mapping", "clientServlet", "web.xml", {
        "servlet_name": "clientServlet", "url_patterns": ["*.do"]}, language="xml")
    servlet = _obs("servlet", "clientServlet", "web.xml", {
        "name": "clientServlet", "class": "com.acme.ClientServlet"}, language="xml")
    type_java = _obs("java_type", "com.acme.ClientServlet", "src/ClientServlet.java")

    liens = lier([formulaire, mapping, servlet, type_java])

    lien = _de_kind(liens, "jsp_to_servlet_mapping")[0]
    assert lien.status == "ambiguous"
    assert _de_kind(liens, "servlet_to_java_type")[0].status == "linked"


def test_provenance_des_deux_cotes_et_chaine_complete(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    _ecrire(tmp_path, "page.jsp", PAGE_JSP)

    liens = lier(_observations_web(tmp_path))
    lien = next(lien for lien in _de_kind(liens, "jsp_to_servlet_mapping")
                if lien.source_symbol == "/ctx/clients/save.do")

    source = lien.evidence["source"]
    cible = lien.evidence["target"]
    assert (source["file"], source["kind"], source["start"]) == (
        "page.jsp", "jsp_form", 1)
    assert (cible["file"], cible["kind"], cible["start"]) == ("web.xml", "servlet_mapping", 10)
    assert source["provider"] == "jsp"
    assert cible["provider"] == "java-descriptor"

    chaine = {
        (lien.source_file, lien.source_symbol, lien.target_file, lien.target_symbol)
        for lien in liens
    }
    assert ("page.jsp", "/ctx/clients/save.do", "web.xml", "clientServlet") in chaine
    assert ("web.xml", "clientServlet", "src/ClientServlet.java",
            "com.acme.ClientServlet") in chaine


def test_preuve_via_pour_un_champ_et_serialisation_du_rapport():
    entite = _obs("java_entity", "com.acme.Client", "src/Client.java",
                  {"table": "CLIENTS"}, start=4, end=20)
    service = _obs("java_type", "com.acme.ClientService", "src/ClientService.java",
                   {"stereotype": "Service"})
    champ = _obs("java_field", "client", "src/ClientService.java",
                 {"type": "Client", "owner": "com.acme.ClientService"}, start=8, end=8)

    lien = _de_kind(lier([entite, service, champ]), "java_to_jpa_entity")[0]
    assert lien.evidence["via"][0]["file"] == "src/ClientService.java"
    assert lien.evidence["via"][0]["symbol"] == "client"

    rapport = rapport_liens([lien])
    relu = json.loads(json.dumps(rapport, ensure_ascii=False))
    assert relu["total"] == 1
    assert relu["par_kind"] == {"java_to_jpa_entity": 1}
    assert relu["par_statut"]["linked"] == 1
    assert relu["fichiers"]["sources"] == ["src/ClientService.java"]
    assert relu["fichiers"]["cibles"] == ["src/Client.java"]
    assert relu["liens"][0]["evidence"]["source"]["file"] == "src/ClientService.java"


def test_rapport_liens_serialisable_et_coherent(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    _ecrire(tmp_path, "page.jsp", PAGE_JSP)
    liens = lier(_observations_web(tmp_path))

    rapport = rapport_liens(liens)
    relu = json.loads(json.dumps(rapport, ensure_ascii=False))

    assert relu["total"] == len(liens)
    assert sum(relu["par_kind"].values()) == len(liens)
    assert sum(relu["par_statut"].values()) == len(liens)
    assert set(relu["par_statut"]) == {"linked", "inferred", "ambiguous"}
    assert relu["confiance"]["min"] <= relu["confiance"]["moyenne"] <= relu["confiance"]["max"]
    assert relu["liens"]
    assert all(set(item) == {
        "kind", "source_file", "source_symbol", "target_file", "target_symbol",
        "attributes", "confidence", "status", "evidence",
    } for item in relu["liens"])


def test_jsp_ne_lie_pas_par_nom_de_fichier_seul(tmp_path):
    _ecrire(tmp_path, "page.jsp", '<form action="/inconnu"></form>')
    type_java = _obs("java_type", "page.Page", "page.java", {"fqn": "page.Page"})

    liens = lier(JspSidecar().index(str(tmp_path)) + [type_java])

    assert all(lien.source_file != "page.jsp" or lien.target_file != "page.java"
               for lien in liens)
    assert liens == []


def test_entree_vide_ou_non_observation():
    assert lier([]) == []
    assert lier([object(), "texte", None]) == []
    rapport = rapport_liens([])
    assert rapport["total"] == 0
    assert rapport["par_kind"] == {}
    assert rapport["liens"] == []
    assert json.dumps(rapport, ensure_ascii=False)


def test_lien_refuse_un_statut_inconnu():
    try:
        Link(kind="test", source_file="a", source_symbol="a", target_file="b",
             target_symbol="b", status="inconnu")
    except ValueError as erreur:
        assert "statut de lien inconnu" in str(erreur)
    else:
        raise AssertionError("un statut inconnu doit être refusé")
