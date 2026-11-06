"""Sidecar des descripteurs Java : extraction XML, lignes, tolérance aux fichiers invalides."""
from meridian.adapters.outbound.connectors.java_descriptors import JavaDescriptorSidecar

WEB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="http://java.sun.com/xml/ns/javaee">
  <servlet>
    <servlet-name>accueil</servlet-name>
    <servlet-class>com.acme.AccueilServlet</servlet-class>
  </servlet>
  <servlet-mapping>
    <servlet-name>accueil</servlet-name>
    <url-pattern>/accueil</url-pattern>
  </servlet-mapping>
  <filter>
    <filter-name>auth</filter-name>
    <filter-class>com.acme.AuthFilter</filter-class>
  </filter>
  <filter-mapping>
    <filter-name>auth</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>
  <listener>
    <listener-class>com.acme.SessionListener</listener-class>
  </listener>
  <welcome-file>index.jsp</welcome-file>
</web-app>
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


def test_web_xml_extrait_servlets_filtres_et_welcome_file(tmp_path):
    _ecrire(tmp_path, "WEB-INF/web.xml", WEB_XML)
    observations = JavaDescriptorSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    servlet = kinds["servlet"][0]
    assert (servlet.symbol, servlet.start) == ("accueil", 3)
    assert servlet.attributes["class"] == "com.acme.AccueilServlet"

    mapping = kinds["servlet_mapping"][0]
    assert (mapping.symbol, mapping.start) == ("accueil", 7)
    assert mapping.attributes["url_pattern"] == "/accueil"

    filtre = kinds["filter"][0]
    assert (filtre.symbol, filtre.start) == ("auth", 11)
    assert filtre.attributes["class"] == "com.acme.AuthFilter"

    filtre_mapping = kinds["filter_mapping"][0]
    assert (filtre_mapping.symbol, filtre_mapping.start) == ("auth", 15)
    assert filtre_mapping.attributes["url_pattern"] == "/*"

    listener = kinds["listener"][0]
    assert (listener.symbol, listener.start) == ("com.acme.SessionListener", 19)

    welcome = kinds["welcome_file"][0]
    assert (welcome.symbol, welcome.start) == ("index.jsp", 22)


def test_ejb_jar_extrait_ejb_interfaces_mdb_et_resource_ref(tmp_path):
    _ecrire(tmp_path, "ejb-jar.xml", """<ejb-jar>
  <enterprise-beans>
    <session>
      <ejb-name>ClientEJB</ejb-name>
      <home>com.acme.ClientHome</home>
      <remote>com.acme.ClientRemote</remote>
      <local>com.acme.ClientLocal</local>
      <ejb-class>com.acme.ClientBean</ejb-class>
      <session-type>Stateless</session-type>
    </session>
    <message-driven>
      <ejb-name>MailMDB</ejb-name>
      <ejb-class>com.acme.MailBean</ejb-class>
      <destination-type>javax.jms.Queue</destination-type>
    </message-driven>
    <resource-ref>
      <res-ref-name>jdbc/mail</res-ref-name>
      <res-type>javax.sql.DataSource</res-type>
    </resource-ref>
  </enterprise-beans>
</ejb-jar>
""")
    observations = JavaDescriptorSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    ejb = kinds["ejb"][0]
    assert (ejb.symbol, ejb.start) == ("ClientEJB", 3)
    assert ejb.attributes["home"] == "com.acme.ClientHome"
    assert ejb.attributes["remote"] == "com.acme.ClientRemote"
    assert ejb.attributes["local"] == "com.acme.ClientLocal"
    assert ejb.attributes["ejb_class"] == "com.acme.ClientBean"

    refs = {o.symbol: o for o in kinds["ejb_ref"]}
    assert set(refs) == {
        "com.acme.ClientHome", "com.acme.ClientRemote", "com.acme.ClientLocal", "jdbc/mail"}
    assert refs["com.acme.ClientHome"].attributes["type"] == "home"
    assert refs["jdbc/mail"].attributes["res_type"] == "javax.sql.DataSource"
    assert refs["jdbc/mail"].start == 16

    mdb = kinds["mdb"][0]
    assert (mdb.symbol, mdb.start) == ("MailMDB", 11)
    assert mdb.attributes["destination_type"] == "javax.jms.Queue"


def test_struts_config_extrait_actions_et_forwards(tmp_path):
    _ecrire(tmp_path, "struts-config.xml", """<struts-config>
  <action-mappings>
    <action path="/client" type="com.acme.ClientAction" name="clientForm">
      <forward name="succes" path="/client/liste.jsp"/>
      <forward name="erreur" path="/client/form.jsp"/>
    </action>
  </action-mappings>
  <global-forwards>
    <forward name="accueil" path="/accueil.jsp"/>
  </global-forwards>
</struts-config>
""")
    observations = JavaDescriptorSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    action = kinds["struts_action"][0]
    assert (action.symbol, action.start) == ("/client", 3)
    assert action.attributes["type"] == "com.acme.ClientAction"
    assert action.attributes["name"] == "clientForm"

    forwards = {o.symbol: o for o in kinds["struts_forward"]}
    assert set(forwards) == {"succes", "erreur", "accueil"}
    assert (forwards["succes"].start, forwards["succes"].attributes["action"]) == (4, "/client")
    assert (forwards["erreur"].start, forwards["erreur"].attributes["path"]) == (5, "/client/form.jsp")
    assert forwards["accueil"].start == 9


def test_application_context_extrait_beans_et_property_ref(tmp_path):
    _ecrire(tmp_path, "applicationContext.xml", """<beans xmlns="http://www.springframework.org/schema/beans">
  <bean id="clientDao" class="com.acme.ClientDao">
    <property name="dataSource" ref="dataSource"/>
  </bean>
  <bean id="dataSource" class="org.apache.tomcat.jdbc.pool.DataSource"/>
</beans>
""")
    observations = JavaDescriptorSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    beans = {o.symbol: o for o in kinds["spring_bean"]}
    assert set(beans) == {"clientDao", "dataSource"}
    assert (beans["clientDao"].start, beans["clientDao"].attributes["class"]) == (2, "com.acme.ClientDao")
    assert beans["dataSource"].start == 5

    reference = kinds["spring_ref"][0]
    assert (reference.symbol, reference.start) == ("dataSource", 3)
    assert reference.attributes["bean"] == "clientDao"
    assert reference.attributes["property"] == "dataSource"


def test_persistence_xml_extrait_unite_classes_et_datasource(tmp_path):
    _ecrire(tmp_path, "persistence.xml", """<persistence>
  <persistence-unit name="unite" transaction-type="RESOURCE_LOCAL">
    <class>com.acme.Client</class>
    <jta-data-source>jdbc/unite</jta-data-source>
  </persistence-unit>
</persistence>
""")
    observations = JavaDescriptorSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    unite = kinds["persistence_unit"][0]
    assert (unite.symbol, unite.start) == ("unite", 2)
    assert unite.attributes["transaction_type"] == "RESOURCE_LOCAL"

    entite = kinds["entity_class"][0]
    assert (entite.symbol, entite.start) == ("com.acme.Client", 3)
    assert entite.attributes["unit"] == "unite"

    source = kinds["datasource"][0]
    assert (source.symbol, source.start) == ("jdbc/unite", 4)
    assert source.attributes["type"] == "jta-data-source"


def test_decouverte_limitee_aux_descripteurs_connus(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    _ecrire(tmp_path, "META-INF/ejb-jar.xml", "<ejb-jar/>")
    _ecrire(tmp_path, "WEB-INF/applicationContext.xml", "<beans/>")
    _ecrire(tmp_path, "META-INF/persistence.xml", "<persistence/>")
    _ecrire(tmp_path, "notes.xml", "<notes/>")

    couverture = {l.file: l.statut for l in JavaDescriptorSidecar().couverture(str(tmp_path))}

    assert couverture == {
        "META-INF/ejb-jar.xml": "indexe",
        "META-INF/persistence.xml": "indexe",
        "WEB-INF/applicationContext.xml": "indexe",
        "web.xml": "indexe",
    }


def test_xml_invalide_ne_leve_pas_et_reste_partiel(tmp_path):
    _ecrire(tmp_path, "web.xml", "<web-app><servlet></web-app>")

    sidecar = JavaDescriptorSidecar()
    assert sidecar.index(str(tmp_path)) == []

    couverture = sidecar.couverture(str(tmp_path))
    assert len(couverture) == 1
    assert couverture[0].statut == "partiel"
    assert "XML invalide" in couverture[0].raison


def test_doctype_externe_est_ignore_sans_requete(tmp_path):
    _ecrire(tmp_path, "web.xml", """<!DOCTYPE web-app SYSTEM "http://127.0.0.1:9/web-app.dtd">
<web-app>
  <servlet>
    <servlet-name>sans-reseau</servlet-name>
    <servlet-class>com.acme.SansReseau</servlet-class>
  </servlet>
</web-app>
""")
    observations = JavaDescriptorSidecar().index(str(tmp_path))

    assert [o.symbol for o in observations] == ["sans-reseau"]
    assert observations[0].start == 3


def test_entite_externe_non_resolue_et_fichier_illisible(tmp_path):
    _ecrire(tmp_path, "web.xml", """<!DOCTYPE web-app [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<web-app><servlet><servlet-name>&xxe;</servlet-name></servlet></web-app>
""")
    sidecar = JavaDescriptorSidecar()
    observations = sidecar.index(str(tmp_path))

    assert observations == []
    couverture = {l.file: l for l in sidecar.couverture(str(tmp_path), fichiers=["web.xml", "absent.xml"])}
    assert couverture["web.xml"].statut == "partiel"
    assert couverture["absent.xml"].statut == "partiel"
    assert "/etc/passwd" not in couverture["web.xml"].raison


def test_descripteur_inconnu_et_extension_non_xml(tmp_path):
    _ecrire(tmp_path, "notes.xml", "<notes/>")
    _ecrire(tmp_path, "page.jsp", "<form></form>")

    couverture = {l.file: l for l in JavaDescriptorSidecar().couverture(
        str(tmp_path), fichiers=["notes.xml", "page.jsp"])}

    assert couverture["notes.xml"].statut == "ignore"
    assert couverture["page.jsp"].statut == "non_supporte"
    assert JavaDescriptorSidecar().index(str(tmp_path), fichiers=["notes.xml"]) == []


def test_observations_portent_la_provenance_du_sidecar(tmp_path):
    _ecrire(tmp_path, "web.xml", WEB_XML)
    observation = JavaDescriptorSidecar().index(str(tmp_path))[0]

    assert observation.provider == "java-descriptor"
    assert observation.parser == "xml-descriptor"
    assert observation.parser_version == "1"
    assert observation.language == "xml"
    assert observation.status == "extracted"
    assert observation.confidence == 1.0
