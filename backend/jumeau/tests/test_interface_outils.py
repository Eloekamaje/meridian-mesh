"""Compilation des opérations d'interface : REST/SOAP, preuves, noms stables et registre."""
import json

from jumeau import interface_outils, interfaces
from jumeau.capacites import RegistreCapacites


def contrat(identifiant="ctr-1", application="comptes", format_="openapi", environment="prod"):
    return interfaces.Contract(
        id=identifiant, format=format_, version="1.0.0", digest="digest", locator="spec",
        application_id=application, environment=environment)


def operation(identifiant, contract_id, protocol, method, path, name, environment="prod", version="1.0.0"):
    return interfaces.Operation(
        id=identifiant, contract_id=contract_id, protocol=protocol, method=method, path=path,
        name=name, version=version, environment=environment)


def graphe_rest():
    return interfaces.InterfaceGraph(
        contracts=[contrat()],
        operations=[
            operation("op-1", "ctr-1", "rest", "GET", "/comptes", "listerComptes"),
            operation("op-2", "ctr-1", "rest", "POST", "/comptes", "creerCompte"),
        ],
    )


def test_rest_get_est_observer_et_post_est_agir():
    manifestes = interface_outils.manifests_depuis_interface(
        graphe_rest(), tenant="banque", persona="analyste", perimetre="comptes")
    par_nom = {manifeste.nom: manifeste for manifeste in manifestes}

    assert set(par_nom) == {"comptes.listercomptes", "comptes.creercompte"}
    lecture = par_nom["comptes.listercomptes"]
    ecriture = par_nom["comptes.creercompte"]

    assert lecture.capacite == "observer"
    assert lecture.lecture_seule is True
    assert lecture.effets_de_bord == ()
    assert lecture.mode_preuve == "OBSERVED"
    assert ecriture.capacite == "agir"
    assert ecriture.lecture_seule is False
    assert ecriture.effets_de_bord == ("http:POST",)
    assert ecriture.mode_preuve == "AUCUNE"
    assert all(manifeste.source == "interface" for manifeste in manifestes)
    assert all(manifeste.timeout_ms == 5000 and manifeste.cout == 0.0 for manifeste in manifestes)
    assert all(manifeste.schema_entree == {} and manifeste.schema_sortie == {} for manifeste in manifestes)
    assert all((manifeste.tenant, manifeste.persona, manifeste.perimetre) ==
               ("banque", "analyste", "comptes") for manifeste in manifestes)
    assert "REST" in lecture.description and "listerComptes" in lecture.description
    assert "comptes" in lecture.description and "prod" in lecture.description


def test_soap_getquote_est_observer_et_createorder_est_agir():
    graph = interfaces.InterfaceGraph(
        contracts=[contrat("ctr-soap", "ventes", "wsdl")],
        operations=[
            operation("op-soap-1", "ctr-soap", "soap", "SOAP", "GetQuote", "GetQuote"),
            operation("op-soap-2", "ctr-soap", "soap", "SOAP", "CreateOrder", "CreateOrder"),
        ],
    )
    par_nom = {manifeste.nom: manifeste
               for manifeste in interface_outils.manifests_depuis_interface(graph)}

    lecture = par_nom["ventes.getquote"]
    ecriture = par_nom["ventes.createorder"]
    assert lecture.capacite == "observer" and lecture.lecture_seule is True
    assert lecture.effets_de_bord == () and lecture.mode_preuve == "OBSERVED"
    assert ecriture.capacite == "agir" and ecriture.lecture_seule is False
    assert ecriture.effets_de_bord == ("soap:CreateOrder",)
    assert ecriture.mode_preuve == "AUCUNE"
    assert all(manifeste.source == "interface" for manifeste in par_nom.values())
    assert "SOAP" in ecriture.description and "CreateOrder" in ecriture.description
    assert "ventes" in ecriture.description and "prod" in ecriture.description


def test_sans_contrat_ni_application_et_noms_dupliques_restent_deterministes_et_uniques():
    operations = [
        {"contract_id": "absent", "protocol": "rest", "method": "GET",
         "path": "/a", "name": "doublon", "version": None},
        {"contract_id": "absent", "protocol": "rest", "method": "GET",
         "path": "/b", "name": "doublon", "version": None},
    ]
    premier = interface_outils.manifests_depuis_interface(operations)
    second = interface_outils.manifests_depuis_interface(operations)

    assert [manifeste.as_dict() for manifeste in premier] == [
        manifeste.as_dict() for manifeste in second]
    noms = [manifeste.nom for manifeste in premier]
    assert len(noms) == len(set(noms)) == 2
    assert noms[0] == "application.doublon"
    assert noms[1].startswith("application.doublon-")
    assert all(len(nom) <= 80 for nom in noms)


def test_charger_dans_enregistre_et_preserve_la_portee():
    registre = RegistreCapacites()
    noms = interface_outils.charger_dans(
        registre, graphe_rest(), version="2.0.0",
        tenant="banque", persona="analyste", perimetre="comptes")

    assert noms == ["comptes.listercomptes", "comptes.creercompte"]
    assert all(nom in registre for nom in noms)
    assert len(registre) == 2
    for nom in noms:
        manifeste = registre.decrire(nom)
        assert manifeste.version == "2.0.0"
        assert (manifeste.tenant, manifeste.persona, manifeste.perimetre) == (
            "banque", "analyste", "comptes")
    assert interface_outils.charger_dans(
        registre, graphe_rest(), version="2.0.0",
        tenant="banque", persona="analyste", perimetre="comptes") == noms


def test_sans_operation_rend_une_liste_vide():
    assert interface_outils.manifests_depuis_interface(interfaces.InterfaceGraph()) == []
    assert interface_outils.manifests_depuis_interface([]) == []
    assert interface_outils.manifests_depuis_interface(None) == []


def test_cli_detecte_openapi_et_affiche_les_noms(tmp_path, capsys):
    fichier = tmp_path / "comptes.json"
    fichier.write_text(json.dumps({
        "openapi": "3.0.3",
        "info": {"version": "1"},
        "paths": {"/comptes": {"get": {"operationId": "listerComptes"}}},
    }), encoding="utf-8")

    assert interface_outils.main([
        "--application", "comptes", "--fichier", str(fichier), "--tenant", "banque"]) == 0
    assert json.loads(capsys.readouterr().out) == ["comptes.listercomptes"]


def test_graphql_et_asyncapi_sont_compiles_depuis_les_operations_connues():
    graph = interfaces.InterfaceGraph(
        contracts=[contrat("ctr-gql", "atlas", "graphql"), contrat("ctr-evt", "ventes", "asyncapi")],
        operations=[
            operation("op-gql-q", "ctr-gql", "graphql", "QUERY", "comptes", "comptes"),
            operation("op-gql-m", "ctr-gql", "graphql", "MUTATION", "creerCompte", "creerCompte"),
            operation("op-evt-p", "ctr-evt", "asyncapi", "PUBLISH", "comptes/crees", "publierCompte"),
            operation("op-evt-s", "ctr-evt", "asyncapi", "SUBSCRIBE", "comptes/crees", "recevoirCompte"),
        ],
    )
    par_nom = {m.nom: m for m in interface_outils.manifests_depuis_interface(graph)}

    assert par_nom["atlas.comptes"].lecture_seule is True
    assert par_nom["atlas.creercompte"].lecture_seule is False
    assert par_nom["atlas.creercompte"].effets_de_bord == ("graphql:creerCompte",)
    assert par_nom["ventes.publiercompte"].lecture_seule is False
    assert par_nom["ventes.publiercompte"].effets_de_bord == ("asyncapi:comptes/crees",)
    assert par_nom["ventes.recevoircompte"].lecture_seule is True
