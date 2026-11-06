"""Sidecar JSP : extraction structurelle, lignes sources et couverture."""
from meridian.adapters.outbound.connectors.jsp import JspSidecar

PAGE = """<%@ page contentType="text/html" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<%@ include file="/WEB-INF/entete.jspf" %>
<jsp:useBean id="client" class="bo.Client" scope="request" />
<form action="/clients/save" method="post" id="form-client">
  <a href="/clients/list">Liste</a>
</form>
<jsp:include page="/WEB-INF/pied.jsp" />
<c:import url="/WEB-INF/legal.jsp" />
<jsp:forward page="/done.jsp" />
"""


def _ecrire(base, relatif, contenu):
    chemin = base / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _par_kind(observations):
    resultat = {}
    for observation in observations:
        resultat.setdefault(observation.kind, []).append(observation)
    return resultat


def test_decouverte_recursive_des_pages_jsp(tmp_path):
    _ecrire(tmp_path, "accueil.jsp", "<form action=\"/accueil\"></form>")
    _ecrire(tmp_path, "WEB-INF/fragments/pied.jspf", "<jsp:include page=\"/x.jsp\" />")
    _ecrire(tmp_path, "WEB-INF/tags/carte.tag", "<form action=\"/carte\"></form>")
    _ecrire(tmp_path, "notes.txt", "<form action=\"/faux\">")

    observations = JspSidecar().index(str(tmp_path))

    assert {o.file for o in observations} == {
        "accueil.jsp", "WEB-INF/fragments/pied.jspf", "WEB-INF/tags/carte.tag"}
    assert all(o.file.endswith((".jsp", ".jspf", ".tag")) for o in observations)


def test_extraction_des_constructions_et_des_lignes(tmp_path):
    _ecrire(tmp_path, "page.jsp", PAGE)
    observations = JspSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    taglib = kinds["jsp_taglib"][0]
    assert (taglib.symbol, taglib.start) == ("c", 2)
    assert taglib.attributes["uri"] == "http://java.sun.com/jsp/jstl/core"

    include_directive = next(o for o in kinds["jsp_include"] if o.start == 3)
    assert include_directive.attributes["file"] == "/WEB-INF/entete.jspf"
    assert include_directive.attributes["target"] == "/WEB-INF/entete.jspf"

    bean = kinds["jsp_bean"][0]
    assert (bean.symbol, bean.start) == ("client", 4)
    assert bean.attributes["class"] == "bo.Client"
    assert bean.attributes["scope"] == "request"

    form = kinds["jsp_form"][0]
    assert (form.start, form.end) == (5, 5)
    assert form.symbol == "form-client"
    assert form.attributes["action"] == "/clients/save"
    assert form.attributes["method"] == "post"
    assert form.attributes["target"] == "/clients/save"

    lien = next(o for o in kinds["jsp_link"] if o.symbol == "/clients/list")
    assert lien.start == 6
    assert lien.attributes["href"] == "/clients/list"

    include_jsp = next(o for o in kinds["jsp_include"] if o.start == 8)
    assert include_jsp.attributes["page"] == "/WEB-INF/pied.jsp"

    import_jsp = next(o for o in kinds["jsp_include"] if o.start == 9)
    assert import_jsp.attributes["url"] == "/WEB-INF/legal.jsp"

    forward = kinds["jsp_forward"][0]
    assert (forward.start, forward.symbol) == (10, "/done.jsp")
    assert forward.attributes["page"] == "/done.jsp"


def test_commentaires_et_scriptlets_ne_produisent_pas_de_faux_positifs(tmp_path):
    _ecrire(tmp_path, "page.jsp", """<!-- <form action="/faux-html"> -->
<%-- <form action="/faux"> --%>
<% String faux = "<a href=\\"/faux\\">"; %>
<form action="/vrai"></form>
""")
    observations = JspSidecar().index(str(tmp_path))

    assert [o.symbol for o in observations if o.kind == "jsp_form"] == ["/vrai"]
    assert all(o.symbol != "/faux" for o in observations)
    assert next(o for o in observations if o.kind == "jsp_form").start == 4


def test_tags_struts_legacy_sont_reconnus(tmp_path):
    _ecrire(tmp_path, "page.jsp", """<html:form action="/client/save">
  <html:link page="/client/liste">Liste</html:link>
</html:form>
<s:url action="client" />
""")
    observations = JspSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    assert kinds["jsp_form"][0].symbol == "/client/save"
    liens = {o.symbol: o for o in kinds["jsp_link"]}
    assert set(liens) == {"/client/liste", "client"}
    assert (liens["/client/liste"].start, liens["client"].start) == (2, 4)


def test_balise_multiligne_garde_debut_et_fin(tmp_path):
    _ecrire(tmp_path, "page.jsp", """<form
  action="/x"
  method="post">
</form>
""")
    form = JspSidecar().index(str(tmp_path))[0]

    assert form.kind == "jsp_form"
    assert (form.start, form.end) == (1, 3)


def test_fichiers_explicites_limitent_l_indexation(tmp_path):
    _ecrire(tmp_path, "a.jsp", "<form action=\"/a\"></form>")
    _ecrire(tmp_path, "b.jsp", "<form action=\"/b\"></form>")

    observations = JspSidecar().index(str(tmp_path), fichiers=["b.jsp"])
    assert [o.file for o in observations] == ["b.jsp"]

    absolu = JspSidecar().index(str(tmp_path), fichiers=[str(tmp_path / "a.jsp")])
    assert [o.file for o in absolu] == ["a.jsp"]


def test_couverture_signale_indexe_non_supporte_et_illisible(tmp_path):
    _ecrire(tmp_path, "page.jsp", "<p>ok</p>")
    _ecrire(tmp_path, "notes.txt", "texte")

    discovered = {l.file: l for l in JspSidecar().couverture(str(tmp_path))}
    assert set(discovered) == {"page.jsp"}
    assert discovered["page.jsp"].statut == "indexe"
    assert discovered["page.jsp"].language == "jsp"

    explicit = {l.file: l for l in JspSidecar().couverture(
        str(tmp_path), fichiers=["notes.txt", "absent.jsp"])}
    assert explicit["notes.txt"].statut == "non_supporte"
    assert explicit["absent.jsp"].statut == "partiel"
    assert explicit["absent.jsp"].raison


def test_observations_portent_la_provenance_du_sidecar(tmp_path):
    _ecrire(tmp_path, "page.jsp", "<form action=\"/x\"></form>")
    observation = JspSidecar().index(str(tmp_path))[0]

    assert observation.provider == "jsp"
    assert observation.parser == "jsp-structural"
    assert observation.parser_version == "1"
    assert observation.language == "jsp"
    assert observation.status == "extracted"
    assert observation.confidence == 1.0
