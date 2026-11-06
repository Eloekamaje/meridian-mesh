"""Contrat des packs legacy : Finding localisés, candidats honnêtes, Claims existants seulement."""
import json

import pytest

from meridian.application.code_links import Link
from meridian.application.legacy_packs import (
    Finding, claims_promouvables, packs, rapport_packs,
)
from meridian.domain.code_index import Observation


def _obs(kind, symbol, file, attributes=None, *, start=1, end=None, commit="",
         confidence=1.0, language="java", provider="test"):
    return Observation(
        provider=provider, parser="test", parser_version="1", file=file,
        language=language, kind=kind, symbol=symbol, start=start,
        end=end if end is not None else start, commit=commit,
        attributes=attributes or {}, confidence=confidence, status="extracted",
    )


def _par_kind(findings, kind):
    return [finding for finding in findings if finding.kind == kind]


def _route_get():
    return _obs(
        "spring_route", "GET /clients/{id}", "src/main/java/com/acme/ClientController.java",
        {"annotation": "GetMapping", "path": "/clients/{id}", "methods": ["GET"],
         "method": "GET", "http_method": "GET", "controller": "com.acme.ClientController"},
        start=42, commit="abc123def456",
    )


def _constats_legacy_prouvables():
    return packs([
        _obs("cobol_call", "SUBPROG", "cobol/main.cbl", {"target": "SUBPROG"},
             start=20, commit="abc123def456", language="cobol", provider="cobol"),
        _obs("cobol_copy", "COMMON", "cobol/main.cbl", {"copybook": "COMMON"},
             start=22, commit="abc123def456", language="cobol", provider="cobol"),
        _obs("jcl_program", "MAINPROG", "jcl/night.jcl",
             {"pgm": "MAINPROG", "step": "STEP1", "job": "NIGHT"},
             start=5, commit="abc123def456", language="jcl", provider="jcl"),
        _obs("jcl_dataset", "ACME.CLIENTS", "jcl/night.jcl",
             {"dsn": "ACME.CLIENTS", "dd": "IN", "step": "STEP1", "job": "NIGHT"},
             start=6, commit="abc123def456", language="jcl", provider="jcl"),
        _obs("sql_fk", "FK_ORDERS_CLIENTS", "db/schema.sql",
             {"table": "ORDERS", "references": "CLIENTS"},
             start=12, commit="abc123def456", language="sql", provider="sql"),
    ])


def _fichier(contenu, taille=30):
    lignes = ["* ligne neutre"] * taille
    for numero, texte in contenu.items():
        lignes[numero - 1] = texte
    return lignes


def _fichiers_legacy():
    return {
        "cobol/main.cbl": _fichier({
            20: "           CALL 'SUBPROG'.",
            22: "           COPY COMMON.",
        }),
        "jcl/night.jcl": _fichier({
            5: "//STEP1 EXEC PGM=MAINPROG",
            6: "//IN DD DSN=ACME.CLIENTS,DISP=SHR",
        }),
        "db/schema.sql": _fichier({
            12: "FOREIGN KEY (CLIENT_ID) REFERENCES CLIENTS (ID)",
        }),
    }


def test_route_spring_avec_methode_et_preuve_est_promue():
    findings = packs([_route_get()])

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.kind, finding.predicate) == ("EXPOSE", "EXPOSE")
    assert finding.object == "GET /clients/{id}"
    assert finding.claim_type == "API_USAGE"
    assert finding.status == "claim"
    assert finding.source_file == "src/main/java/com/acme/ClientController.java"
    assert finding.evidence["start"] == 42
    assert finding.evidence["end"] == 42

    claims = claims_promouvables(findings, lire=lambda chemin: ["class ClientController {"] * 41 + ["@GetMapping(\"/clients/{id}\")"])
    assert len(claims) == 1
    claim = claims[0]
    assert claim["sujet"] == "com.acme.ClientController"
    assert claim["predicat"] == "EXPOSE"
    assert claim["objet"] == "GET /clients/{id}"
    assert claim["type"] == "API_USAGE"
    assert len(claim["preuves"]) == 1
    preuve = claim["preuves"][0]
    assert preuve["chemin"] == "src/main/java/com/acme/ClientController.java"
    assert preuve["ligne_debut"] == 42
    assert preuve["ligne_fin"] == 42
    assert "GetMapping" in preuve["citation"]
    assert len(preuve["hash"]) == 64
    assert "abc123def456" in preuve["locator"]
    assert "#L42-L42" in preuve["locator"]


def test_prefixe_de_controleur_est_compose_dans_la_route():
    route = _obs(
        "spring_route", "GET /{id}", "src/ClientController.java",
        {"annotation": "GetMapping", "path": "/{id}", "prefix": "/clients",
         "methods": ["GET"], "method": "GET", "controller": "com.acme.ClientController"},
        start=20, commit="abc123def456",
    )

    [finding] = packs([route])

    assert finding.object == "GET /clients/{id}"
    assert finding.attributes["path"] == "/clients/{id}"


def test_route_spring_sans_methode_reste_candidate():
    route = _obs(
        "spring_route", "ANY /things", "src/ThingController.java",
        {"annotation": "RequestMapping", "path": "/things", "method": "ANY",
         "methods": ["ANY"], "controller": "com.acme.ThingController"},
        start=8,
    )

    findings = packs([route])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.object == "ANY /things"
    assert finding.status == "candidate"
    assert finding.attributes["promouvable"] is False
    assert claims_promouvables(findings) == []


def test_prefixe_de_controleur_n_est_pas_une_route_exposee():
    prefixe = _obs(
        "spring_route", "ANY /api", "src/ClientController.java",
        {"annotation": "RequestMapping", "path": "/api", "method": "ANY",
         "scope": "type", "controller": "com.acme.ClientController"},
        start=5,
    )

    assert packs([prefixe]) == []


def test_jsp_reste_candidate_meme_avec_un_lien_unique():
    page = _obs(
        "jsp_form", "form", "web/page.jsp",
        {"action": "/clients/save", "target": "/clients/save", "method": "post"},
        start=3, language="jsp", provider="jsp",
    )
    lien = Link(
        kind="jsp_to_spring_route",
        source_file="web/page.jsp", source_symbol="form",
        target_file="src/ClientController.java", target_symbol="POST /clients/save",
        attributes={"http_method": "POST", "method_verified": True},
        confidence=0.95, status="linked",
    )

    findings = packs([page], liens=[lien])

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.kind, finding.predicate, finding.claim_type) == (
        "INTERFACE_UTILISATEUR", "INTERFACE_UTILISATEUR", "FUNCTIONALITY")
    assert finding.status == "candidate"
    assert finding.object == "/clients/save"
    assert finding.target_file == "src/ClientController.java"
    assert finding.target_symbol == "POST /clients/save"
    assert finding.attributes["lien"] == "jsp_to_spring_route"
    assert claims_promouvables(findings) == []


def test_jee_jpa_produit_des_constats_candidates():
    service = _obs(
        "jee_component", "OrderService", "src/OrderService.java",
        {"name": "OrderService", "stereotype": "Stateless",
         "class": "com.acme.OrderService", "owner": "com.acme.OrderService"}, start=5,
    )
    entite = _obs(
        "jpa_entity", "Order", "src/Order.java",
        {"fqn": "com.acme.Order", "name": "Order", "class": "Order", "table": "ORDERS"},
        start=7,
    )
    colonne = _obs(
        "jpa_column", "ID", "src/Order.java",
        {"name": "ID", "column": "ID", "table": "ORDERS", "class": "Order"}, start=9,
    )
    injection = _obs(
        "jee_injection", "orderRepository", "src/OrderService.java",
        {"name": "orderRepository", "owner": "com.acme.OrderService", "annotation": "EJB"},
        start=12,
    )
    champ = _obs(
        "java_field", "orderRepository", "src/OrderService.java",
        {"name": "orderRepository", "owner": "com.acme.OrderService",
         "type": "OrderRepository"}, start=13,
    )

    findings = packs([service, entite, colonne, injection, champ])

    composants = _par_kind(findings, "COMPOSANT_JEE")
    stocks = _par_kind(findings, "STOCKE_DANS")
    injections = _par_kind(findings, "INJECTE")
    assert len(composants) == 1
    assert composants[0].object == "Stateless"
    assert composants[0].subject == "com.acme.OrderService"
    assert {finding.object for finding in stocks} == {"ORDERS", "ORDERS.ID"}
    assert len(stocks) == 2
    assert len(injections) == 1
    assert injections[0].subject == "com.acme.OrderService"
    assert injections[0].object == "OrderRepository"
    assert all(finding.status == "candidate" for finding in findings)
    assert claims_promouvables(findings) == []


def test_entite_sans_table_explicite_reste_candidate_avec_table_inferee():
    entite = _obs(
        "jpa_entity", "Client", "src/Client.java",
        {"fqn": "com.acme.Client", "name": "Client"}, start=7,
    )

    findings = packs([entite])

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.kind, finding.predicate) == ("STOCKE_DANS", "STOCKE_DANS")
    assert finding.object == "Client"
    assert finding.attributes["table_source"] == "class_name"
    assert finding.status == "candidate"
    assert claims_promouvables(findings) == []


def test_cobol_jcl_produit_appelle_copie_execute_et_lit_dataset():
    programme = _obs("cobol_program", "MAINPROG", "cobol/main.cbl", start=1,
                     language="cobol", provider="cobol")
    appel = _obs("cobol_call", "SUBPROG", "cobol/main.cbl", {"target": "SUBPROG"},
                 start=20, language="cobol", provider="cobol")
    copie = _obs("cobol_copy", "COMMON", "cobol/main.cbl", {"copybook": "COMMON"},
                 start=22, language="cobol", provider="cobol")
    fichier = _obs("cobol_file", "CLIENTS", "cobol/main.cbl",
                   {"select": "CLIENTS", "dataset": "ACME.CLIENTS"},
                   start=8, language="cobol", provider="cobol")
    cible = _obs("cobol_program", "SUBPROG", "cobol/sub.cbl", start=1,
                 language="cobol", provider="cobol")
    etape = _obs("jcl_program", "MAINPROG", "jcl/night.jcl",
                 {"pgm": "MAINPROG", "step": "STEP1", "job": "NIGHT"},
                 start=5, language="jcl", provider="jcl")
    proc = _obs("jcl_proc", "CLEANUP", "jcl/night.jcl",
                {"proc": "CLEANUP", "step": "STEP2", "job": "NIGHT"},
                start=9, language="jcl", provider="jcl")
    dataset = _obs("jcl_dataset", "ACME.CLIENTS", "jcl/night.jcl",
                   {"dsn": "ACME.CLIENTS", "dd": "IN", "step": "STEP1", "job": "NIGHT"},
                   start=6, language="jcl", provider="jcl")
    lien = Link(
        kind="cobol_call_to_program",
        source_file="cobol/main.cbl", source_symbol="SUBPROG",
        target_file="cobol/sub.cbl", target_symbol="SUBPROG",
        confidence=1.0, status="linked",
    )

    findings = packs([programme, appel, copie, fichier, cible, etape, proc, dataset],
                     liens=[lien])

    assert {finding.kind for finding in findings} == {"APPELLE", "COPIE", "EXECUTE",
                                                      "LIT_DATASET"}
    appels = _par_kind(findings, "APPELLE")
    assert appels[0].subject == "MAINPROG"
    assert appels[0].object == "SUBPROG"
    assert appels[0].target_file == "cobol/sub.cbl"
    assert _par_kind(findings, "COPIE")[0].object == "COMMON"
    executes = {(finding.subject, finding.object) for finding in _par_kind(findings, "EXECUTE")}
    assert ("NIGHT/STEP1", "MAINPROG") in executes
    assert ("NIGHT/STEP2", "CLEANUP") in executes
    datasets = {finding.object for finding in _par_kind(findings, "LIT_DATASET")}
    assert datasets == {"ACME.CLIENTS"}
    assert all(finding.status == "candidate" for finding in findings)
    assert claims_promouvables(findings) == []


def test_les_constats_structurels_prouvables_sont_promus_par_la_recette():
    findings = _constats_legacy_prouvables()

    assert {finding.predicate for finding in findings} == {
        "APPELLE", "COPIE", "EXECUTE", "LIT_DATASET", "REFERENCE"}
    assert all(finding.status == "claim" for finding in findings)

    fichiers = _fichiers_legacy()
    claims = claims_promouvables(findings, lire=lambda chemin: fichiers.get(chemin))

    assert {(claim["predicat"], claim["objet"]) for claim in claims} == {
        ("APPELLE", "SUBPROG"),
        ("COPIE", "COMMON"),
        ("EXECUTE", "MAINPROG"),
        ("LIT_DATASET", "ACME.CLIENTS"),
        ("REFERENCE", "CLIENTS"),
    }
    for claim in claims:
        [preuve] = claim["preuves"]
        assert preuve["citation"]
        assert len(preuve["hash"]) == 64
        assert preuve["locator"].startswith("git://abc123def456:")
        assert preuve["sha"] == "abc123def456"
        assert preuve["ligne_debut"] >= 1


def test_un_constat_dont_la_recette_echoue_reste_sans_claim():
    findings = _constats_legacy_prouvables()
    assert all(finding.status == "claim" for finding in findings)

    fichiers = {chemin: ["DISPLAY 'RIEN'"] * 30 for chemin in _fichiers_legacy()}

    assert claims_promouvables(findings, lire=lambda chemin: fichiers.get(chemin)) == []


def test_les_lignes_commentees_ne_promeuvent_pas():
    findings = _constats_legacy_prouvables()
    commentaires = {
        "cobol/main.cbl": _fichier({
            20: "* CALL 'SUBPROG'.",
            22: "-- COPY COMMON.",
        }),
        "jcl/night.jcl": _fichier({
            5: "//* EXEC PGM=MAINPROG",
            6: "# DSN=ACME.CLIENTS",
        }),
        "db/schema.sql": _fichier({
            12: "-- REFERENCES CLIENTS",
        }),
    }

    assert claims_promouvables(findings, lire=lambda chemin: commentaires.get(chemin)) == []


def test_sans_lignes_lues_aucun_claim_meme_avec_commit():
    findings = _constats_legacy_prouvables()

    assert claims_promouvables(findings, lire=lambda chemin: None) == []


def test_un_constat_localise_sans_commit_reste_candidate():
    appel = _obs("cobol_call", "SUBPROG", "cobol/main.cbl", {"target": "SUBPROG"},
                 start=20, language="cobol", provider="cobol")

    [finding] = packs([appel])

    assert finding.status == "candidate"
    assert claims_promouvables(
        [finding], lire=lambda chemin: ["CALL 'SUBPROG'"] * 20) == []


def test_les_constats_composes_sans_preuve_restent_candidats_meme_avec_un_commit():
    page = _obs("jsp_form", "form", "web/page.jsp", {"method": "post"},
                start=3, commit="abc123def456", language="jsp", provider="jsp")
    composant = _obs("jee_component", "Service", "src/Service.java",
                     {"name": "Service", "class": "com.acme.Service"},
                     start=2, commit="abc123def456")
    entite = _obs("jpa_entity", "Client", "src/Client.java",
                  {"fqn": "com.acme.Client", "name": "Client", "table": "CLIENTS"},
                  start=7, commit="abc123def456")
    injection = _obs("jee_injection", "service", "src/Service.java",
                     {"name": "service", "owner": "com.acme.Service",
                      "annotation": "EJB"},
                     start=12, commit="abc123def456")

    findings = packs([page, composant, entite, injection])

    assert len(findings) == len([page, composant, entite, injection])
    assert all(finding.status == "candidate" for finding in findings)
    assert all(finding.attributes["preuve_suffisante"] is False for finding in findings)
    assert claims_promouvables(
        findings, lire=lambda chemin: ["REFERENCES CLIENTS"] * 30) == []


def test_jsp_formulaire_est_promu_sur_la_ligne_du_formulaire():
    page = _obs("jsp_form", "form", "web/page.jsp",
                {"action": "/clients/save", "method": "post"},
                start=3, commit="abc123def456", language="jsp", provider="jsp")

    [finding] = packs([page])

    assert finding.predicate == "INTERFACE_UTILISATEUR"
    assert finding.object == "/clients/save"
    assert finding.status == "claim"
    assert finding.attributes["preuve_suffisante"] is True

    fichiers = {"web/page.jsp": _fichier({
        3: '<form action="/clients/save" method="post">',
    })}
    claims = claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin))

    assert [(claim["predicat"], claim["objet"]) for claim in claims] == [
        ("INTERFACE_UTILISATEUR", "/clients/save")]
    [preuve] = claims[0]["preuves"]
    assert preuve["citation"] == '<form action="/clients/save" method="post">'
    assert preuve["ligne_debut"] == 3
    assert preuve["sha"] == "abc123def456"
    assert len(preuve["hash"]) == 64


def test_jsp_formulaire_dont_la_ligne_ne_porte_pas_l_action_ne_produit_pas_de_claim():
    page = _obs("jsp_form", "form", "web/page.jsp",
                {"action": "/clients/save", "method": "post"},
                start=3, commit="abc123def456", language="jsp", provider="jsp")
    [finding] = packs([page])

    fichiers = {"web/page.jsp": _fichier({3: '<form action="/autre" method="post">'})}

    assert claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin)) == []


def test_composant_jee_est_promu_sur_son_stereotype():
    composant = _obs("jee_component", "OrderService", "src/OrderService.java",
                     {"name": "OrderService", "stereotype": "Stateless",
                      "annotation": "Stateless", "class": "com.acme.OrderService"},
                     start=5, commit="abc123def456")

    [finding] = packs([composant])

    assert finding.predicate == "COMPOSANT_JEE"
    assert finding.subject == "com.acme.OrderService"
    assert finding.object == "Stateless"
    assert finding.status == "claim"

    fichiers = {"src/OrderService.java": _fichier({5: "@Stateless"})}
    claims = claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin))

    assert [(claim["predicat"], claim["objet"]) for claim in claims] == [
        ("COMPOSANT_JEE", "Stateless")]
    assert claims[0]["preuves"][0]["ligne_debut"] == 5


def test_composant_jee_dont_la_ligne_ne_porte_pas_l_annotation_reste_sans_claim():
    composant = _obs("jee_component", "OrderService", "src/OrderService.java",
                     {"name": "OrderService", "stereotype": "Stateless",
                      "annotation": "Stateless", "class": "com.acme.OrderService"},
                     start=5, commit="abc123def456")
    [finding] = packs([composant])

    fichiers = {"src/OrderService.java": _fichier({5: "@Service"})}

    assert claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin)) == []


def test_stocke_dans_est_prouve_par_la_ligne_de_la_table_pas_par_l_entite():
    entite = _obs("jpa_entity", "Order", "src/Order.java",
                  {"fqn": "com.acme.Order", "name": "Order", "class": "Order",
                   "table": "ORDERS"}, start=7, commit="abc123def456")
    table = _obs("jpa_table", "ORDERS", "src/Order.java",
                 {"name": "ORDERS", "table": "ORDERS", "class": "Order"},
                 start=8, commit="abc123def456")

    findings = packs([entite, table])

    [stockage] = _par_kind(findings, "STOCKE_DANS")
    [declaration] = _par_kind(findings, "TABLE")
    assert stockage.object == "ORDERS"
    assert stockage.evidence["start"] == 8
    assert stockage.status == "claim"
    assert declaration.object == "ORDERS"
    assert declaration.evidence["start"] == 8

    fichiers = {"src/Order.java": _fichier({
        7: "@Entity",
        8: '@Table(name = "ORDERS")',
    })}
    claims = claims_promouvables(findings, lire=lambda chemin: fichiers.get(chemin))

    assert {(claim["predicat"], claim["objet"]) for claim in claims} == {
        ("STOCKE_DANS", "ORDERS"), ("TABLE", "ORDERS")}
    assert all(claim["preuves"][0]["ligne_debut"] == 8 for claim in claims)


def test_entite_sans_ligne_de_table_reste_candidate_meme_avec_un_commit():
    entite = _obs("jpa_entity", "Order", "src/Order.java",
                  {"fqn": "com.acme.Order", "name": "Order", "class": "Order",
                   "table": "ORDERS"}, start=7, commit="abc123def456")

    [finding] = packs([entite])

    assert finding.predicate == "STOCKE_DANS"
    assert finding.attributes["preuve_suffisante"] is False
    assert finding.status == "candidate"

    fichiers = {"src/Order.java": _fichier({7: "@Entity"})}
    assert claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin)) == []


def test_stocke_dans_utilise_la_preuve_sql_reliee_a_l_entite():
    entite = _obs("jpa_entity", "Client", "src/Client.java",
                  {"fqn": "com.acme.Client", "name": "Client", "class": "Client",
                   "table": "CLIENTS"}, start=4, commit="abc123def456")
    table = _obs("sql_table", "APP.CLIENTS", "db/schema.sql",
                 {"table": "APP.CLIENTS"}, start=2, commit="abc123def456",
                 language="sql", provider="sql")
    lien = Link(
        kind="sql_table_to_jpa_table",
        source_file="db/schema.sql", source_symbol="APP.CLIENTS",
        target_file="src/Client.java", target_symbol="com.acme.Client",
        confidence=1.0, status="linked",
    )

    findings = packs([entite, table], liens=[lien])

    [stockage] = _par_kind(findings, "STOCKE_DANS")
    assert stockage.object == "CLIENTS"
    assert stockage.evidence["file"] == "db/schema.sql"
    assert stockage.evidence["start"] == 2
    assert stockage.status == "claim"

    fichiers = {"db/schema.sql": _fichier({2: "CREATE TABLE APP.CLIENTS ("})}
    claims = claims_promouvables(findings, lire=lambda chemin: fichiers.get(chemin))

    stockages = [claim for claim in claims if claim["predicat"] == "STOCKE_DANS"]
    assert [(claim["objet"], claim["preuves"][0]["chemin"],
             claim["preuves"][0]["ligne_debut"]) for claim in stockages] == [
        ("CLIENTS", "db/schema.sql", 2)]


def test_injection_est_prouvee_par_le_champ_qui_porte_le_type_et_l_annotation():
    injection = _obs("jee_injection", "orderRepository", "src/OrderService.java",
                     {"name": "orderRepository", "owner": "com.acme.OrderService",
                      "annotation": "EJB"}, start=12, commit="abc123def456")
    champ = _obs("java_field", "orderRepository", "src/OrderService.java",
                 {"name": "orderRepository", "owner": "com.acme.OrderService",
                  "type": "OrderRepository", "annotations": ["EJB"]},
                 start=12, end=13, commit="abc123def456")

    findings = packs([injection, champ])

    [trouve] = _par_kind(findings, "INJECTE")
    assert trouve.object == "OrderRepository"
    assert trouve.evidence["start"] == 12
    assert trouve.evidence["end"] == 13
    assert trouve.status == "claim"

    fichiers = {"src/OrderService.java": _fichier({
        12: "@EJB",
        13: "private OrderRepository orderRepository;",
    })}
    claims = claims_promouvables(findings, lire=lambda chemin: fichiers.get(chemin))

    assert [(claim["predicat"], claim["objet"]) for claim in claims] == [
        ("INJECTE", "OrderRepository")]
    [preuve] = claims[0]["preuves"]
    assert preuve["ligne_debut"] == 12
    assert preuve["ligne_fin"] == 13
    assert "@EJB" in preuve["citation"]


def test_injection_sans_champ_localise_reste_candidate():
    injection = _obs("jee_injection", "orderRepository", "src/OrderService.java",
                     {"name": "orderRepository", "owner": "com.acme.OrderService",
                      "annotation": "EJB"}, start=12, commit="abc123def456")

    [finding] = packs([injection])

    assert finding.object == "orderRepository"
    assert finding.attributes["preuve_suffisante"] is False
    assert finding.status == "candidate"
    assert claims_promouvables(
        [finding], lire=lambda chemin: _fichier({12: "@EJB"})) == []


def test_resource_ref_xml_est_promu_sur_le_type_de_la_ressource():
    reference = _obs("ejb_ref", "jdbc/client", "web/WEB-INF/ejb-jar.xml",
                     {"type": "resource-ref", "res_type": "javax.sql.DataSource"},
                     start=3, end=6, commit="abc123def456",
                     language="xml", provider="java-descriptor")

    [finding] = packs([reference])

    assert finding.predicate == "INJECTE"
    assert finding.object == "javax.sql.DataSource"
    assert finding.status == "claim"

    fichiers = {"web/WEB-INF/ejb-jar.xml": _fichier({
        3: "<resource-ref>",
        4: "<res-ref-name>jdbc/client</res-ref-name>",
        5: "<res-type>javax.sql.DataSource</res-type>",
        6: "</resource-ref>",
    })}
    claims = claims_promouvables([finding], lire=lambda chemin: fichiers.get(chemin))

    assert [(claim["predicat"], claim["objet"]) for claim in claims] == [
        ("INJECTE", "javax.sql.DataSource")]


def test_table_sql_est_prouvee_par_create_table_et_rejetee_sur_commentaire():
    table = _obs("sql_table", "CLIENTS", "db/schema.sql", {"table": "CLIENTS"},
                 start=5, commit="abc123def456", language="sql", provider="sql")

    [finding] = packs([table])
    assert finding.predicate == "TABLE"
    assert finding.status == "claim"

    create = {"db/schema.sql": _fichier({5: "CREATE TABLE CLIENTS ("})}
    commentaire = {"db/schema.sql": _fichier({5: "-- CREATE TABLE CLIENTS ("})}

    assert [(claim["predicat"], claim["objet"]) for claim in
            claims_promouvables([finding], lire=lambda chemin: create.get(chemin))] == [
        ("TABLE", "CLIENTS")]
    assert claims_promouvables(
        [finding], lire=lambda chemin: commentaire.get(chemin)) == []


def test_sql_table_et_fk_sont_candidates_et_enrichis_par_les_liens():
    table = _obs("sql_table", "CLIENTS", "db/schema.sql",
                 {"table": "CLIENTS", "schema": "ACME", "colonnes": ["ID", "NAME"]},
                 start=2, language="sql", provider="sql")
    fk = _obs("sql_fk", "FK_ORDERS_CLIENTS", "db/schema.sql",
              {"table": "ORDERS", "references": "CLIENTS", "colonnes": ["CLIENT_ID"],
               "colonnes_referencees": ["ID"]}, start=12, language="sql", provider="sql")
    entite = _obs("jpa_entity", "Client", "src/Client.java",
                  {"fqn": "com.acme.Client", "name": "Client", "table": "CLIENTS"},
                  start=4)
    lien_table = Link(
        kind="sql_table_to_jpa_table",
        source_file="db/schema.sql", source_symbol="CLIENTS",
        target_file="src/Client.java", target_symbol="com.acme.Client",
        confidence=1.0, status="linked",
    )
    lien_fk = Link(
        kind="sql_fk_to_table",
        source_file="db/schema.sql", source_symbol="FK_ORDERS_CLIENTS",
        target_file="db/schema.sql", target_symbol="CLIENTS",
        confidence=1.0, status="linked",
    )

    findings = packs([table, fk, entite], liens=[lien_table, lien_fk])

    tables = _par_kind(findings, "TABLE")
    references = _par_kind(findings, "REFERENCE")
    assert len(tables) == 1
    assert tables[0].object == "CLIENTS"
    assert tables[0].target_file == "src/Client.java"
    assert len(references) == 1
    assert (references[0].subject, references[0].object) == ("ORDERS", "CLIENTS")
    assert references[0].target_symbol == "CLIENTS"
    assert all(finding.status == "candidate" for finding in findings)
    assert claims_promouvables(findings) == []


def test_preuve_non_localisee_interdit_la_promotion():
    route = _obs(
        "spring_route", "GET /sans-ligne", "src/Controller.java",
        {"annotation": "GetMapping", "path": "/sans-ligne", "method": "GET",
         "controller": "com.acme.Controller"}, start=0,
    )

    findings = packs([route])

    assert findings[0].status == "candidate"
    assert findings[0].evidence["localisee"] is False
    assert findings[0].evidence["locator"] == ""
    assert claims_promouvables(findings) == []


def test_preuve_localisee_porte_fichier_lignes_et_commit():
    findings = packs([_route_get()])
    evidence = findings[0].evidence

    assert evidence["file"] == "src/main/java/com/acme/ClientController.java"
    assert (evidence["start"], evidence["end"]) == (42, 42)
    assert evidence["commit"] == "abc123def456"
    assert evidence["locator"].endswith(
        "src/main/java/com/acme/ClientController.java#L42-L42")
    assert "abc123def456" in evidence["locator"]


def test_aucun_candidat_n_est_transforme_en_claim():
    candidats = [
        _obs("jsp_include", "include", "web/page.jsp", {"page": "/header.jsp"},
             start=1, language="jsp", provider="jsp"),
        _obs("jee_component", "Service", "src/Service.java",
             {"name": "Service", "stereotype": "Stateless", "class": "com.acme.Service"},
             start=2),
        _obs("cobol_call", "SUBPROG", "cobol/main.cbl", {"target": "SUBPROG"},
             start=3, language="cobol", provider="cobol"),
        _obs("jcl_dataset", "ACME.DATA", "jcl/job.jcl", {"dsn": "ACME.DATA"},
             start=4, language="jcl", provider="jcl"),
        _obs("sql_table", "CLIENTS", "db/schema.sql", {"table": "CLIENTS"},
             start=5, language="sql", provider="sql"),
    ]

    findings = packs(candidats)

    assert len(findings) == len(candidats)
    assert all(finding.status == "candidate" for finding in findings)
    assert claims_promouvables(findings) == []


def test_rapport_packs_est_serialisable_et_compte_les_promouvables():
    page = _obs("jsp_form", "form", "web/page.jsp",
                {"action": "/clients/save", "method": "post"},
                start=3, language="jsp", provider="jsp")
    findings = packs([_route_get(), page])

    rapport = rapport_packs(findings)

    assert rapport["total"] == 2
    assert rapport["par_statut"] == {"candidate": 1, "claim": 1}
    assert rapport["par_kind"] == {"EXPOSE": 1, "INTERFACE_UTILISATEUR": 1}
    assert rapport["par_predicat"] == {"EXPOSE": 1, "INTERFACE_UTILISATEUR": 1}
    assert rapport["promouvables"] == 1
    assert rapport["confiance"]["min"] <= rapport["confiance"]["moyenne"] <= rapport["confiance"]["max"]
    assert rapport["fichiers"]["sources"] == [
        "src/main/java/com/acme/ClientController.java", "web/page.jsp"]
    assert len(rapport["findings"]) == 2
    assert json.loads(json.dumps(rapport)) == rapport


def test_statut_de_finding_inconnu_est_refuse():
    with pytest.raises(ValueError):
        Finding(kind="EXPOSE", subject="s", predicate="EXPOSE", object="GET /",
                claim_type="API_USAGE", status="prouve")
