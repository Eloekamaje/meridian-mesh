"""Manifestes depuis GraphQL, gRPC et AsyncAPI : déclaratif, sans réseau ni exécution."""
import ast
import json
from pathlib import Path

import pytest

from meridian.domain.capacites import RegistreCapacites
from meridian.application.protocoles_outils import ErreurProtocoles, charger_dans, manifests_asyncapi, manifests_graphql, manifests_grpc

SDL = '''
"""
Documentation qui imite un type Query { piege: String } sans être du SDL.
"""
type Query @cache(ttl: 30) {
  listerComptes(
    limite: Int = 10,
    filtre: Filtre = {actif: true, tags: ["a", "b"]}
  ): [Compte!]!
  __typename: String
  chercherCompte(id: ID!): Compte @deprecated(reason: "obsolète")
}

type Mutation {
  creerCompte(nom: String!): Compte!
}

type Subscription {
  nouveauxComptes: Compte!
}
'''

PROTO = '''
syntax = "proto3";

/* service Fantome { rpc GetFantome (Requete) returns (Reponse); } */
// rpc ListerCaches (Requete) returns (Reponse);
service Comptes {
  // rpc GetCache (Requete) returns (Reponse);
  rpc GetCompte (Requete) returns (Compte);
  rpc ListComptes (stream Requete) returns (stream Compte);
  rpc SearchComptes (Requete) returns (Compte);
  rpc CreerCompte (Requete) returns (Compte) {
    option (google.api.http) = { post: "/v1/comptes" body: "*" };
  }
  rpc WatchComptes (Requete) returns (stream Compte);
}

service Paiements {
  rpc FetchPaiement (Requete) returns (Paiement);
  rpc Encaisser (Requete) returns (Paiement);
}
'''

ASYNCAPI = {
    "asyncapi": "2.6.0",
    "channels": {
        "comptes/crees": {
            "publish": {
                "operationId": "publierCompte",
                "message": {"payload": {"type": "object", "properties": {"secretField": {"type": "string"}}}},
            },
            "subscribe": {
                "operationId": "recevoirCompte",
                "message": {"payload": {"type": "object"}},
            },
        },
        "paiements": {
            "subscribe": {"operationId": "receivePaiement"},
        },
    },
}


def _par_nom(manifestes):
    return {manifeste.nom: manifeste for manifeste in manifestes}


def test_graphql_query_mutation_subscription_et_introspection():
    manifestes = manifests_graphql("comptes", SDL)
    par_nom = _par_nom(manifestes)

    assert set(par_nom) == {
        "comptes.graphql.listercomptes",
        "comptes.graphql.cherchercompte",
        "comptes.graphql.creercompte",
        "comptes.graphql.nouveauxcomptes",
    }
    requete = par_nom["comptes.graphql.listercomptes"]
    mutation = par_nom["comptes.graphql.creercompte"]
    abonnement = par_nom["comptes.graphql.nouveauxcomptes"]

    assert requete.capacite == "observer"
    assert requete.lecture_seule is True
    assert requete.mode_preuve == "OBSERVED"
    assert requete.effets_de_bord == ()
    assert mutation.capacite == "agir"
    assert mutation.lecture_seule is False
    assert mutation.mode_preuve == "AUCUNE"
    assert mutation.effets_de_bord == ("graphql:mutation",)
    assert abonnement.capacite == "observer"
    assert abonnement.lecture_seule is True
    assert abonnement.effets_de_bord == ()
    assert "flux" in abonnement.description

    assert all(manifeste.source == "graphql" for manifeste in manifestes)
    assert all(manifeste.timeout_ms == 5000 and manifeste.cout == 0.0 for manifeste in manifestes)
    assert all(manifeste.schema_entree == {} and manifeste.schema_sortie == {} for manifeste in manifestes)
    assert "listerComptes" in requete.description and "comptes" in requete.description


def test_grpc_lectures_ecritures_et_commentaires():
    manifestes = manifests_grpc("comptes", PROTO)
    par_nom = _par_nom(manifestes)

    assert set(par_nom) == {
        "comptes.grpc.getcompte",
        "comptes.grpc.listcomptes",
        "comptes.grpc.searchcomptes",
        "comptes.grpc.creercompte",
        "comptes.grpc.watchcomptes",
        "comptes.grpc.fetchpaiement",
        "comptes.grpc.encaisser",
    }
    assert all(nom not in par_nom for nom in ("comptes.getcache", "comptes.getfantome", "comptes.listercaches"))

    for nom in ("comptes.grpc.getcompte", "comptes.grpc.listcomptes", "comptes.grpc.searchcomptes",
                "comptes.grpc.watchcomptes", "comptes.grpc.fetchpaiement"):
        assert par_nom[nom].capacite == "observer"
        assert par_nom[nom].lecture_seule is True
        assert par_nom[nom].mode_preuve == "OBSERVED"
        assert par_nom[nom].effets_de_bord == ()

    creation = par_nom["comptes.grpc.creercompte"]
    assert creation.capacite == "agir"
    assert creation.lecture_seule is False
    assert creation.mode_preuve == "AUCUNE"
    assert creation.effets_de_bord == ("grpc:Comptes.CreerCompte",)
    assert par_nom["comptes.grpc.encaisser"].effets_de_bord == ("grpc:Paiements.Encaisser",)
    assert all(manifeste.source == "grpc" for manifeste in manifestes)
    assert all(manifeste.schema_entree == {} and manifeste.schema_sortie == {} for manifeste in manifestes)


def test_asyncapi_publish_subscribe_depuis_dict_sans_payload():
    manifestes = manifests_asyncapi("comptes", ASYNCAPI)
    par_nom = _par_nom(manifestes)

    assert set(par_nom) == {
        "comptes.asyncapi.publiercompte",
        "comptes.asyncapi.recevoircompte",
        "comptes.asyncapi.receivepaiement",
    }
    publication = par_nom["comptes.asyncapi.publiercompte"]
    reception = par_nom["comptes.asyncapi.recevoircompte"]

    assert publication.capacite == "agir"
    assert publication.lecture_seule is False
    assert publication.mode_preuve == "AUCUNE"
    assert publication.effets_de_bord == ("asyncapi:publish",)
    assert reception.capacite == "observer"
    assert reception.lecture_seule is True
    assert reception.effets_de_bord == ()
    assert par_nom["comptes.asyncapi.receivepaiement"].lecture_seule is True
    assert all(manifeste.source == "asyncapi" for manifeste in manifestes)
    assert all("comptes/crees" in manifeste.description or "paiements" in manifeste.description
               for manifeste in manifestes)
    assert "secretField" not in json.dumps([manifeste.as_dict() for manifeste in manifestes], ensure_ascii=False)


def test_asyncapi_operations_send_receive_version_3():
    document = {
        "asyncapi": "3.0.0",
        "channels": {"commandes": {"address": "commandes"}},
        "operations": {
            "envoyerCommande": {"action": "send", "channel": {"$ref": "#/channels/commandes"}},
            "recevoirCommande": {"action": "receive", "channel": {"$ref": "#/channels/commandes"}},
        },
    }
    par_nom = _par_nom(manifests_asyncapi("ventes", document))

    assert set(par_nom) == {"ventes.asyncapi.envoyercommande", "ventes.asyncapi.recevoircommande"}
    assert par_nom["ventes.asyncapi.envoyercommande"].effets_de_bord == ("asyncapi:publish",)
    assert par_nom["ventes.asyncapi.envoyercommande"].lecture_seule is False
    assert par_nom["ventes.asyncapi.recevoircommande"].lecture_seule is True
    assert "commandes" in par_nom["ventes.asyncapi.envoyercommande"].description


def test_asyncapi_yaml_si_disponible():
    pytest.importorskip("yaml")
    texte = """
asyncapi: '2.6.0'
channels:
  factures:
    publish:
      operationId: emettreFacture
    subscribe:
      operationId: recevoirFacture
"""
    par_nom = _par_nom(manifests_asyncapi("compta", texte))
    assert set(par_nom) == {"compta.asyncapi.emettrefacture", "compta.asyncapi.recevoirfacture"}
    assert par_nom["compta.asyncapi.emettrefacture"].lecture_seule is False
    assert par_nom["compta.asyncapi.recevoirfacture"].lecture_seule is True


def test_noms_uniques_stables_et_borne_a_80_caracteres():
    proto = """
service Alpha { rpc Lister (Requete) returns (Reponse); }
service Beta { rpc Lister (Requete) returns (Reponse); }
"""
    premier = manifests_grpc("app", proto)
    second = manifests_grpc("app", proto)
    noms = [manifeste.nom for manifeste in premier]

    assert len(noms) == len(set(noms)) == 2
    assert all(nom.startswith("app.grpc.lister") for nom in noms)
    assert [manifeste.as_dict() for manifeste in premier] == [manifeste.as_dict() for manifeste in second]

    long_proto = f"service S {{ rpc {'a' * 120} (Requete) returns (Reponse); }}"
    manifeste = manifests_grpc("application", long_proto)[0]
    assert len(manifeste.nom) <= 80
    assert manifeste.nom.startswith("application.grpc.")


def test_aucune_entree_rend_une_liste_vide():
    assert manifests_graphql("app", "") == []
    assert manifests_graphql("app", "   \n") == []
    assert manifests_grpc("app", "") == []
    assert manifests_grpc("app", "// rien") == []
    assert manifests_asyncapi("app", {}) == []
    assert manifests_asyncapi("app", "") == []
    assert manifests_graphql("app", "type Autre { champ: String }") == []


def test_application_invalide_et_document_asyncapi_non_objet():
    with pytest.raises(ErreurProtocoles):
        manifests_graphql("", "type Query { lister: String }")
    with pytest.raises(ErreurProtocoles):
        manifests_asyncapi("app", ["pas", "un", "objet"])


def test_charger_dans_enregistre_les_manifestes_des_trois_protocoles():
    manifestes = (
        manifests_graphql("comptes", SDL)
        + manifests_grpc("paiements", PROTO)
        + manifests_asyncapi("ventes", ASYNCAPI)
    )
    registre = RegistreCapacites()

    noms = charger_dans(registre, manifestes)

    assert noms == [manifeste.nom for manifeste in manifestes]
    assert len(registre) == len(manifestes)
    assert all(nom in registre for nom in noms)
    assert charger_dans(registre, manifestes) == noms
    assert len(registre) == len(manifestes)


def test_module_sans_reseau_sans_import_dynamique_ni_execution():
    source = (Path(__file__).resolve().parents[1] / "application" / "protocoles_outils.py").read_text(encoding="utf-8")
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
