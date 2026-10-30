"""Manifestes d'outils depuis OpenAPI : lecture seule par défaut, noms stables et zéro exécution."""
import ast
from collections.abc import Mapping
import json
from pathlib import Path

import pytest

from jumeau.capacites import RegistreCapacites
from jumeau.openapi_outils import ErreurOpenAPI, charger_dans, manifests_depuis_openapi


def spec(**changements):
    document = {
        "openapi": "3.0.3",
        "info": {"title": "Comptes", "version": "1.4.2"},
        "servers": [{"url": "https://api.example.test/v1"}],
        "paths": {
            "/comptes": {
                "get": {
                    "operationId": "listerComptes",
                    "summary": "Liste les comptes",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                    ],
                },
                "post": {
                    "operationId": "creerCompte",
                    "summary": "Crée un compte",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Compte"},
                            },
                        },
                    },
                },
            },
            "/comptes/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                },
            },
        },
        "components": {
            "schemas": {
                "Compte": {
                    "type": "object",
                    "properties": {"nom": {"type": "string"}},
                    "required": ["nom"],
                },
            },
        },
    }
    document.update(changements)
    return document


SPEC_YAML = """
openapi: 3.1.0
info:
  title: Paiements
  version: "2.0.0"
paths:
  /paiements:
    get:
      operationId: listerPaiements
      parameters:
        - name: statut
          in: query
          schema:
            type: string
    post:
      operationId: creerPaiement
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                montant:
                  type: integer
"""


def test_openapi_json_lecture_et_ecriture():
    manifestes = manifests_depuis_openapi("comptes", json.dumps(spec()))
    par_nom = {manifeste.nom: manifeste for manifeste in manifestes}

    assert list(par_nom) == [
        "comptes.listercomptes",
        "comptes.creercompte",
        "comptes.get.comptes-id",
    ]
    lecture = par_nom["comptes.listercomptes"]
    ecriture = par_nom["comptes.creercompte"]

    assert lecture.capacite == "observer"
    assert lecture.lecture_seule is True
    assert lecture.effets_de_bord == ()
    assert ecriture.capacite == "agir"
    assert ecriture.lecture_seule is False
    assert ecriture.effets_de_bord == ("ecriture_post",)
    assert all(manifeste.source == "openapi" for manifeste in manifestes)
    assert all(manifeste.mode_preuve == "OBSERVED" for manifeste in manifestes)
    assert all(manifeste.cout == 0.0 and manifeste.timeout_ms == 5000 for manifeste in manifestes)
    assert all(manifeste.schema_sortie == {} for manifeste in manifestes)


def test_schemas_entree_path_query_body_depuis_openapi():
    manifestes = {manifeste.nom: manifeste for manifeste in manifests_depuis_openapi("comptes", json.dumps(spec()))}

    lecture = manifestes["comptes.listercomptes"].as_dict()["schema_entree"]
    assert lecture["type"] == "object"
    assert lecture["properties"] == {"limit": {"type": "integer"}}

    detail = manifestes["comptes.get.comptes-id"].as_dict()["schema_entree"]
    assert detail["properties"] == {"id": {"type": "string"}}
    assert detail["required"] == ["id"]

    ecriture = manifestes["comptes.creercompte"].as_dict()["schema_entree"]
    assert ecriture["required"] == ["body"]
    assert ecriture["properties"]["body"] == {
        "type": "object",
        "properties": {"nom": {"type": "string"}},
        "required": ["nom"],
    }


def test_openapi_yaml():
    manifestes = {manifeste.nom: manifeste for manifeste in manifests_depuis_openapi("paiements", SPEC_YAML)}
    assert set(manifestes) == {"paiements.listerpaiements", "paiements.creerpaiement"}
    assert manifestes["paiements.listerpaiements"].lecture_seule is True
    assert manifestes["paiements.creerpaiement"].lecture_seule is False
    assert manifestes["paiements.creerpaiement"].capacite == "agir"
    assert manifestes["paiements.listerpaiements"].as_dict()["schema_entree"]["properties"] == {
        "statut": {"type": "string"},
    }


def test_noms_stables_uniques_et_schemas_json_serialisables():
    document = json.dumps(spec())
    premier = manifests_depuis_openapi("comptes", document)
    second = manifests_depuis_openapi("comptes", document)

    assert [m.as_dict() for m in premier] == [m.as_dict() for m in second]
    assert len({m.nom for m in premier}) == len(premier)
    for manifeste in premier:
        json.dumps(manifeste.as_dict(), ensure_ascii=False)
        assert isinstance(manifeste.schema_entree, Mapping)
        assert isinstance(manifeste.schema_sortie, Mapping)


def test_collision_d_operation_id_rend_des_noms_uniques():
    document = spec(paths={
        "/a": {"get": {"operationId": "doublon"}},
        "/b": {"get": {"operationId": "doublon"}},
    })
    noms = [manifeste.nom for manifeste in manifests_depuis_openapi("app", json.dumps(document))]
    assert len(noms) == len(set(noms)) == 2
    assert all(nom.startswith("app.doublon") for nom in noms)


@pytest.mark.parametrize("document", [
    "{pas: [du json",
    "[]",
    json.dumps({"openapi": "3.0.3", "info": {"version": "1"}}),
])
def test_document_illisible_ou_sans_operation_leve_une_erreur_claire(document):
    with pytest.raises(ErreurOpenAPI, match="OpenAPI"):
        manifests_depuis_openapi("app", document)


def test_document_partiel_rend_les_operations_lisibles():
    document = json.dumps({
        "openapi": "3.0.3",
        "info": {"version": "1"},
        "paths": {
            "/ok": {"get": {"operationId": "lireOk"}},
            "/invalide": {"get": "pas un objet"},
        },
    })
    manifestes = manifests_depuis_openapi("app", document)
    assert [manifeste.nom for manifeste in manifestes] == ["app.lireok"]
    assert manifestes[0].schema_entree == {}


def test_openapi_valide_sans_chemin_rend_une_liste_vide():
    document = json.dumps({"openapi": "3.0.3", "info": {"version": "1"}, "paths": {}})
    assert manifests_depuis_openapi("app", document) == []


def test_aucun_secret_ni_url_dans_les_manifestes():
    document = spec(
        servers=[{"url": "https://api.example.test/v1?token=supersecret123"}],
        paths={
            "/comptes": {
                "get": {
                    "operationId": "listerComptes",
                    "summary": "Voir https://example.test/comptes avec token=supersecret123",
                    "parameters": [{
                        "name": "api_key",
                        "in": "query",
                        "schema": {"type": "string", "default": "supersecret123",
                                   "description": "clé https://example.test"},
                    }],
                },
            },
        },
        components={
            "schemas": {
                "Compte": {
                    "type": "object",
                    "properties": {
                        "nom": {"type": "string", "example": "https://example.test/nom"},
                    },
                },
            },
        },
    )
    manifestes = manifests_depuis_openapi("comptes", json.dumps(document))
    assert len(manifestes) == 1
    manifeste = manifestes[0]
    texte = json.dumps(manifeste.as_dict(), ensure_ascii=False)

    assert "https://" not in texte and "http://" not in texte
    assert "supersecret123" not in texte
    assert "api_key" in manifeste.as_dict()["schema_entree"]["properties"]
    assert manifeste.as_dict()["schema_entree"]["properties"]["api_key"] == {"type": "string"}
    assert "adaptateur" not in texte and "execution" not in texte


def test_charger_dans_enregistre_et_rend_les_noms():
    registre = RegistreCapacites()
    noms = charger_dans(registre, "comptes", json.dumps(spec()), "openapi.json", "2.0.0")

    assert noms == ["comptes.listercomptes", "comptes.creercompte", "comptes.get.comptes-id"]
    assert all(nom in registre for nom in noms)
    assert len(registre) == 3
    assert {manifeste.version for manifeste in registre} == {"2.0.0"}
    assert [manifeste.nom for manifeste in registre.lister(lecture_seule=True)] == [
        "comptes.get.comptes-id",
        "comptes.listercomptes",
    ]
    assert [manifeste.nom for manifeste in registre.lister(capacite="agir")] == ["comptes.creercompte"]
    assert charger_dans(registre, "comptes", json.dumps(spec()), "openapi.json", "2.0.0") == noms
    assert len(registre) == 3


def test_portee_et_version_personnalisees():
    manifestes = manifests_depuis_openapi(
        "comptes", json.dumps(spec()), version="3.1.0",
        tenant="banque", persona="analyste", perimetre="comptes")
    assert all(manifeste.version == "3.1.0" for manifeste in manifestes)
    assert all((manifeste.tenant, manifeste.persona, manifeste.perimetre) ==
               ("banque", "analyste", "comptes") for manifeste in manifestes)


def test_source_sans_reseau_sans_import_dynamique_ni_exec():
    source = (Path(__file__).resolve().parents[1] / "openapi_outils.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    interdits = {"requests", "httpx", "urllib", "socket", "http", "subprocess", "importlib"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            assert not ({alias.name.split(".")[0] for alias in noeud.names} & interdits)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            assert noeud.module.split(".")[0] not in interdits
        elif isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name):
            assert noeud.func.id not in {"eval", "exec", "__import__", "compile"}
    assert "urlopen" not in source and "requests." not in source
