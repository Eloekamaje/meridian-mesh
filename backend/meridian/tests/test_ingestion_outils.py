"""Ingestion OpenAPI/MCP : lecture seule, erreurs isolées, portée transmise."""
import json

from meridian.application import ingestion_outils
from meridian.domain.capacites import RegistreCapacites

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Comptes", "version": "1.0.0"},
    "paths": {
        "/comptes": {
            "get": {"operationId": "listerComptes", "summary": "Liste les comptes"},
            "post": {"operationId": "creerCompte", "summary": "Crée un compte"},
        }
    },
}


def test_ingestion_openapi_et_mcp_partagent_le_registre(tmp_path):
    openapi = tmp_path / "comptes.json"
    openapi.write_text(json.dumps(SPEC), encoding="utf-8")
    mcp = tmp_path / "outils.json"
    mcp.write_text(json.dumps({"tools": [
        {"name": "chercher", "description": "Cherche", "inputSchema": {"type": "object"},
         "annotations": {"readOnlyHint": True}},
    ]}), encoding="utf-8")

    registre = RegistreCapacites()
    rapport = ingestion_outils.ingerer_openapi(
        registre, [{"application": "comptes", "path": openapi, "tenant": "demo"}])
    mcp_rapport = ingestion_outils.ingerer_mcp(
        registre, [{"application": "atlas", "path": mcp, "tenant": "demo"}])

    assert len(rapport["outils"]) == 2 and rapport["erreurs"] == []
    assert mcp_rapport["outils"] == ["atlas.chercher"] and mcp_rapport["erreurs"] == []
    assert registre.decrire("comptes.listercomptes").tenant == "demo"
    assert registre.decrire("atlas.chercher").lecture_seule is True


def test_une_entree_invalide_n_empeche_pas_les_autres(tmp_path):
    valide = tmp_path / "valide.json"
    valide.write_text(json.dumps(SPEC), encoding="utf-8")
    registre = RegistreCapacites()

    rapport = ingestion_outils.ingerer_openapi(registre, [
        {"application": "absente", "path": tmp_path / "absente.json"},
        {"application": "comptes", "path": valide},
    ])

    assert len(rapport["outils"]) == 2 and len(rapport["erreurs"]) == 1
    assert "fichier" in rapport["erreurs"][0]["raison"]


def test_un_mcp_sans_tools_est_une_erreur_isolee(tmp_path):
    fichier = tmp_path / "mauvais.json"
    fichier.write_text(json.dumps({"objets": []}), encoding="utf-8")
    rapport = ingestion_outils.ingerer_mcp(RegistreCapacites(), [
        {"application": "atlas", "path": fichier},
    ])
    assert rapport["outils"] == [] and rapport["erreurs"]


WSDL = """<?xml version="1.0"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/" targetNamespace="urn:ventes">
  <portType name="Ventes">
    <operation name="GetQuote"/>
    <operation name="CreateOrder"/>
  </portType>
</definitions>
"""


def test_ingestion_wsdl_produit_soap_lecture_et_ecriture(tmp_path):
    fichier = tmp_path / "ventes.wsdl"
    fichier.write_text(WSDL, encoding="utf-8")
    registre = RegistreCapacites()

    rapport = ingestion_outils.ingerer_interface(
        registre, [{"application": "ventes", "path": fichier, "tenant": "demo"}])

    assert set(rapport["outils"]) == {"ventes.getquote", "ventes.createorder"}
    assert registre.decrire("ventes.getquote").lecture_seule is True
    assert registre.decrire("ventes.createorder").lecture_seule is False
    assert registre.decrire("ventes.createorder").effets_de_bord == ("soap:CreateOrder",)


def test_ingestion_graphql_grpc_asyncapi(tmp_path):
    graphql = tmp_path / "schema.graphql"
    graphql.write_text("type Query { lister: String } type Mutation { creer(nom: String!): String }",
                       encoding="utf-8")
    proto = tmp_path / "comptes.proto"
    proto.write_text("service Comptes { rpc GetCompte (Req) returns (Rep); rpc Creer (Req) returns (Rep); }",
                     encoding="utf-8")
    asyncapi = tmp_path / "events.json"
    asyncapi.write_text(json.dumps({"asyncapi": "2.6.0", "channels": {
        "comptes": {"publish": {"operationId": "publier"}, "subscribe": {"operationId": "recevoir"}}
    }}), encoding="utf-8")
    registre = RegistreCapacites()

    rapport = ingestion_outils.ingerer_protocoles(registre, [
        {"application": "comptes", "path": graphql, "type": "graphql"},
        {"application": "comptes", "path": proto, "type": "grpc"},
        {"application": "comptes", "path": asyncapi, "type": "asyncapi"},
    ])

    assert set(rapport["outils"]) == {
        "comptes.graphql.lister", "comptes.graphql.creer", "comptes.grpc.getcompte",
        "comptes.grpc.creer", "comptes.asyncapi.recevoir", "comptes.asyncapi.publier",
    }
    assert registre.decrire("comptes.asyncapi.publier").lecture_seule is False
    assert registre.decrire("comptes.asyncapi.recevoir").lecture_seule is True
