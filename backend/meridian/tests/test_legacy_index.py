"""Indexation fédérée legacy : sidecars, couverture et liens de bout en bout."""
import json

from meridian.adapters.outbound.connectors.legacy_index import indexer_legacy


def _ecrire(racine):
    (racine / "WEB-INF").mkdir()
    (racine / "WEB-INF" / "web.xml").write_text("""<?xml version="1.0"?>
<web-app xmlns="http://java.sun.com/xml/ns/javaee">
  <servlet><servlet-name>ClientServlet</servlet-name><servlet-class>com.acme.ClientServlet</servlet-class></servlet>
  <servlet-mapping><servlet-name>ClientServlet</servlet-name><url-pattern>/client/*</url-pattern></servlet-mapping>
</web-app>""")
    (racine / "client.jsp").write_text("""
<%@ page contentType="text/html" %>
<form action="/client/list" method="get"><input name="q"/></form>
<jsp:include page="/header.jsp"/>
""")
    (racine / "src").mkdir()
    (racine / "src" / "ClientServlet.java").write_text("""
package com.acme;
import javax.servlet.http.HttpServlet;
public class ClientServlet extends HttpServlet {
  public void doGet() {}
}
""")
    (racine / "sql").mkdir()
    (racine / "sql" / "schema.sql").write_text("""
CREATE TABLE CLIENT (ID INTEGER PRIMARY KEY, AGENCE_ID INTEGER NOT NULL,
  CONSTRAINT FK_AGENCE FOREIGN KEY (AGENCE_ID) REFERENCES AGENCE(ID));
CREATE TABLE AGENCE (ID INTEGER PRIMARY KEY);
""")
    (racine / "cobol").mkdir()
    (racine / "cobol" / "PROG.cbl").write_text("""
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROG.
       PROCEDURE DIVISION.
       MAIN.
           CALL 'SOUSPROG'.
           COPY CLIENT.
""")
    (racine / "cobol" / "SOUSPROG.cbl").write_text("""
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SOUSPROG.
       PROCEDURE DIVISION.
           GOBACK.
""")
    (racine / "cobol" / "CLIENT.cpy").write_text("""
       01 CLIENT-REC.
          05 CLIENT-ID PIC 9(8).
""")
    (racine / "job.jcl").write_text("""//JOB1 JOB (ACCT),'TEST'
//STEP1 EXEC PGM=PROG
//IN DD DSN=CLIENT.FILE,DISP=SHR
""")


def test_indexe_les_sidecars_et_produit_les_liens(tmp_path):
    _ecrire(tmp_path)
    rapport = indexer_legacy(str(tmp_path))
    fichiers = {ligne["file"]: ligne["statut"] for ligne in rapport["couvertures"]}
    kinds = {lien["kind"] for lien in rapport["liens"]["liens"]}

    assert rapport["providers"] == ["jsp", "java", "java-descriptor", "cobol", "jcl", "sql", "abap", "rpg", "pli", "oracle-forms", "powerbuilder"]
    assert fichiers["client.jsp"] in {"indexe", "conflit"}
    assert fichiers["src/ClientServlet.java"] == "indexe"
    assert "jsp_to_servlet_mapping" in kinds
    assert "servlet_mapping_to_servlet" in kinds
    assert "servlet_to_java_type" in kinds
    assert "cobol_call_to_program" in kinds
    assert "cobol_copy_to_copybook" in kinds
    assert "jcl_program_to_cobol_program" in kinds
    assert "sql_fk_to_table" in kinds


def test_rapport_serialisable_et_fichier_non_supporte_visible(tmp_path):
    _ecrire(tmp_path)
    (tmp_path / "notes.txt").write_text("hors index")
    rapport = indexer_legacy(str(tmp_path))

    relu = json.loads(json.dumps(rapport, ensure_ascii=False))
    statuts = {ligne["file"]: ligne["statut"] for ligne in relu["couvertures"]}
    assert statuts["notes.txt"] == "non_supporte"
    assert relu["compteurs"]["non_supporte"] >= 1
