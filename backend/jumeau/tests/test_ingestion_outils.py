"""Ingestion OpenAPI/MCP : lecture seule, erreurs isolées, portée transmise."""
import json

from jumeau import ingestion_outils
from jumeau.capacites import RegistreCapacites

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
