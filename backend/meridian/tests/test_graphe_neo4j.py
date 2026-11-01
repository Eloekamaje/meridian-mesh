"""Adaptateur Neo4j du port GraphStore : Cypher paramétré, tenant, profondeur, refus."""

import ast
import inspect
import json

import pytest

from meridian.adapters.outbound.neo4j import graphe_neo4j
from meridian.domain.graphe import MAX_PROFONDEUR, Arete, GraphStore, NoeudTwin
from meridian.adapters.outbound.neo4j.graphe_neo4j import GrapheNeo4j

TENANT = "TENANT_SENTINEL"
TWIN = "TWIN_SENTINEL"


class Resultat:
    def __init__(self, lignes):
        self._lignes = list(lignes)

    def __iter__(self):
        return iter(self._lignes)

    def data(self):
        return [dict(ligne) for ligne in self._lignes]


class FausseSession:
    """Enregistre (requete, params) et rend les enregistrements fournis, dans l'ordre."""

    def __init__(self, reponses=None):
        self.reponses = list(reponses or [])
        self.appels = []

    def run(self, requete, params=None):
        self.appels.append((requete, params or {}))
        return Resultat(self.reponses.pop(0) if self.reponses else [])


def test_upsert_twin_est_parameterise_et_tenant_scoped():
    session = FausseSession([[{"type": "APPLICATION", "type_ok": True}]])
    noeud = NoeudTwin("app-a", "banque", "APPLICATION", "App A", {"owner": "DSI"})
    assert GrapheNeo4j(session).upsert_twin(noeud) is noeud
    requete, params = session.appels[0]
    assert "MERGE (n:Twin {tenant_id: $tenant_id, id: $id})" in requete
    assert "ON CREATE SET n.type = $type" in requete
    assert "FOREACH (_ IN CASE WHEN type_ok THEN [1] ELSE [] END" in requete
    assert params["tenant_id"] == "banque" and params["id"] == "app-a"
    assert params["type"] == "APPLICATION" and params["label"] == "App A"
    assert json.loads(params["proprietes"]) == {"owner": "DSI"}
    assert "banque" not in requete and "app-a" not in requete


def test_changement_de_type_refuse_sans_mise_a_jour():
    session = FausseSession([[{"type": "PROCESS", "type_ok": False}]])
    with pytest.raises(ValueError, match="type"):
        GrapheNeo4j(session).upsert_twin(
            NoeudTwin("app-a", "banque", "APPLICATION", "A")
        )
    assert len(session.appels) == 1

    session = FausseSession([[{"type": "PROCESS"}]])
    with pytest.raises(ValueError, match="type"):
        GrapheNeo4j(session).upsert_twin(
            NoeudTwin("app-a", "banque", "APPLICATION", "A")
        )


def test_relation_sans_noeuds_est_refusee_par_lecture():
    session = FausseSession([[{"source_present": True, "target_present": None}]])
    with pytest.raises(ValueError, match="absent"):
        GrapheNeo4j(session).upsert_relation(Arete("r1", "banque", "a", "b"))
    assert len(session.appels) == 1
    requete, params = session.appels[0]
    assert "OPTIONAL MATCH" in requete
    assert params["source"] == "a" and params["target"] == "b"
    assert "banque" not in requete


def test_relation_valide_est_mergee_avec_ses_proprietes():
    session = FausseSession(
        [
            [
                {
                    "source_present": True,
                    "target_present": True,
                    "relation_present": False,
                }
            ],
            [],
        ]
    )
    arete = Arete(
        "r1",
        "banque",
        "a",
        "b",
        type="DEPEND_DE",
        etat="confirmee",
        confiance=0.9,
        valid_from="2026-01-01T00:00:00Z",
        preuve_ids=("e1", "e2"),
    )
    assert GrapheNeo4j(session).upsert_relation(arete) is arete
    assert len(session.appels) == 2
    requete, params = session.appels[1]
    assert "MERGE (s)-[r:RELATION {tenant_id: $tenant_id, id: $id}]->(t)" in requete
    assert params["tenant_id"] == "banque" and params["id"] == "r1"
    assert params["source"] == "a" and params["target"] == "b"
    assert params["type"] == "DEPEND_DE" and params["etat"] == "confirmee"
    assert params["confiance"] == 0.9
    assert params["valid_from"] == "2026-01-01T00:00:00Z" and params["valid_to"] is None
    assert params["preuve_ids"] == ["e1", "e2"]
    assert "banque" not in requete and "DEPEND_DE" not in requete


def test_relation_ne_change_pas_d_extremites():
    session = FausseSession(
        [
            [
                {
                    "source_present": True,
                    "target_present": True,
                    "relation_present": True,
                    "existing_source": "autre",
                    "existing_target": "b",
                }
            ]
        ]
    )
    with pytest.raises(ValueError, match="extrémités"):
        GrapheNeo4j(session).upsert_relation(Arete("r1", "banque", "a", "b"))
    assert len(session.appels) == 1


def test_voisins_borne_la_profondeur_et_garde_le_plus_court_chemin():
    session = FausseSession(
        [
            [
                {
                    "id": "b",
                    "profondeur": 2,
                    "chemin": ["a", "x", "b"],
                    "relation": "r2",
                    "etat": "confirmee",
                },
                {
                    "id": "b",
                    "profondeur": 1,
                    "chemin": ["a", "b"],
                    "relation": "r1",
                    "etat": "supposee",
                },
                {
                    "id": "cycle",
                    "profondeur": 2,
                    "chemin": ["a", "cycle", "a"],
                    "relation": "r3",
                    "etat": "supposee",
                },
                {
                    "id": TWIN,
                    "profondeur": 1,
                    "chemin": [TWIN],
                    "relation": "boucle",
                    "etat": "supposee",
                },
            ]
        ]
    )
    sortie = GrapheNeo4j(session).voisins(TENANT, TWIN, profondeur=99, sens="sortant")
    assert sortie == [
        {
            "id": "b",
            "profondeur": 1,
            "chemin": ["a", "b"],
            "relation": "r1",
            "etat": "supposee",
        }
    ]
    requete, params = session.appels[0]
    assert "MATCH p = (depart:Twin {tenant_id: $tenant_id, id: $twin_id})" in requete
    assert f"-[:RELATION*1..{MAX_PROFONDEUR}]->" in requete
    assert "(voisin:Twin {tenant_id: $tenant_id})" in requete
    assert "length(p) <= $profondeur" in requete
    assert params == {
        "tenant_id": TENANT,
        "twin_id": TWIN,
        "profondeur": MAX_PROFONDEUR,
    }
    assert TENANT not in requete and TWIN not in requete


def test_voisins_sens_entrant_les_deux_et_sens_invalide():
    for sens, motif in (
        ("entrant", "<-[:RELATION*1.."),
        ("les_deux", "-[:RELATION*1.."),
    ):
        session = FausseSession()
        assert GrapheNeo4j(session).voisins(TENANT, TWIN, 1, sens) == []
        assert motif in session.appels[0][0]
        assert session.appels[0][1]["profondeur"] == 1
    session = FausseSession()
    with pytest.raises(ValueError, match="sens"):
        GrapheNeo4j(session).voisins(TENANT, TWIN, 1, "diagonal")
    assert session.appels == []


def test_chemins_orientes_sans_cycle_et_bornees():
    session = FausseSession(
        [
            [
                {"chemin": ["a", "b", "c"]},
                {"chemin": ["a", "b", "c"]},
                {"chemin": ["a", "x", "y", "c"]},
                {"chemin": ["a", "1", "2", "3", "4", "5", "6", "7", "8", "c"]},
                {"chemin": ["a", "b", "a", "c"]},
                {"chemin": ["x", "a", "c"]},
            ]
        ]
    )
    sortie = GrapheNeo4j(session).chemins(TENANT, "a", "c", profondeur=99)
    assert sortie == [["a", "b", "c"], ["a", "x", "y", "c"]]
    requete, params = session.appels[0]
    assert "MATCH p = (source:Twin {tenant_id: $tenant_id, id: $source})" in requete
    assert f"-[:RELATION*1..{MAX_PROFONDEUR}]->" in requete
    assert "(cible:Twin {tenant_id: $tenant_id, id: $cible})" in requete
    assert "length(p) <= $profondeur" in requete
    assert "single(m IN nodes(p) WHERE m = n)" in requete
    assert "LIMIT 100" in requete
    assert params == {
        "tenant_id": TENANT,
        "source": "a",
        "cible": "c",
        "profondeur": MAX_PROFONDEUR,
    }
    assert TENANT not in requete and " a " not in requete


def test_chemin_source_egale_cible_est_trivial_sans_requete():
    session = FausseSession()
    assert GrapheNeo4j(session).chemins(TENANT, TWIN, TWIN) == [[TWIN]]
    assert session.appels == []


def test_impact_interroge_aval_puis_amont():
    session = FausseSession(
        [
            [
                {
                    "id": "b",
                    "profondeur": 1,
                    "chemin": ["a", "b"],
                    "relation": "r1",
                    "etat": "confirmee",
                }
            ],
            [
                {
                    "id": "z",
                    "profondeur": 1,
                    "chemin": ["z", "a"],
                    "relation": "r0",
                    "etat": "supposee",
                }
            ],
        ]
    )
    sortie = GrapheNeo4j(session).impact(TENANT, "a", 2)
    assert [v["id"] for v in sortie["aval"]] == ["b"]
    assert [v["id"] for v in sortie["amont"]] == ["z"]
    assert len(session.appels) == 2
    assert "->" in session.appels[0][0] and "(voisin:Twin" in session.appels[0][0]
    assert "<-[:RELATION" in session.appels[1][0]
    assert (
        session.appels[0][1]["profondeur"] == 2
        and session.appels[1][1]["profondeur"] == 2
    )


def test_fermer_et_supprimer_relation_sont_parameterises_et_tenant_scoped():
    session = FausseSession(
        [[{"id": "r1", "valid_to": "2026-01-01T00:00:00Z"}], [{"supprimee": 1}]]
    )
    graphe = GrapheNeo4j(session)
    assert (
        graphe.fermer_relation(TENANT, "r1", "2026-01-01T00:00:00Z")
        == "2026-01-01T00:00:00Z"
    )
    assert graphe.supprimer_relation(TENANT, "r1") == 1
    fermeture, params_fermeture = session.appels[0]
    suppression, params_suppression = session.appels[1]
    assert "SET r.valid_to = $valid_to" in fermeture
    assert params_fermeture == {
        "tenant_id": TENANT,
        "relation_id": "r1",
        "valid_to": "2026-01-01T00:00:00Z",
    }
    assert "DELETE r" in suppression
    assert params_suppression == {"tenant_id": TENANT, "relation_id": "r1"}
    assert TENANT not in fermeture and TENANT not in suppression


def test_as_dict_audit_est_tenant_scoped_et_redecode_les_proprietes():
    session = FausseSession(
        [
            [
                {
                    "id": "a",
                    "tenant_id": TENANT,
                    "type": "APPLICATION",
                    "label": "A",
                    "proprietes": '{"owner": "DSI"}',
                }
            ],
            [
                {
                    "id": "r1",
                    "tenant_id": TENANT,
                    "source": "a",
                    "target": "b",
                    "type": "DEPEND_DE",
                    "etat": "confirmee",
                    "confiance": 0.9,
                    "valid_from": "2026-01-01T00:00:00Z",
                    "valid_to": None,
                    "preuve_ids": ["e1"],
                }
            ],
        ]
    )
    sortie = GrapheNeo4j(session).as_dict(TENANT)
    assert sortie == {
        "noeuds": [
            {
                "id": "a",
                "tenant_id": TENANT,
                "type": "APPLICATION",
                "label": "A",
                "proprietes": {"owner": "DSI"},
            }
        ],
        "aretes": [
            {
                "id": "r1",
                "tenant_id": TENANT,
                "source": "a",
                "target": "b",
                "type": "DEPEND_DE",
                "etat": "confirmee",
                "confiance": 0.9,
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": None,
                "preuve_ids": ["e1"],
            }
        ],
    }
    assert len(session.appels) == 2
    assert all(params["tenant_id"] == TENANT for _, params in session.appels)
    assert all(TENANT not in requete for requete, _ in session.appels)
    with pytest.raises(ValueError, match="tenant_id"):
        GrapheNeo4j(session).as_dict("")


def test_aucune_valeur_utilisateur_n_est_concatenez_dans_le_cypher_et_pas_de_driver():
    source = inspect.getsource(graphe_neo4j)
    assert "import neo4j" not in source and "from neo4j" not in source
    assert "{twin_id}" not in source and "{tenant_id}" not in source
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.JoinedStr):
            texte = ast.unparse(noeud)
            assert (
                "MATCH" not in texte and "MERGE" not in texte and "RETURN" not in texte
            )
    for nom in dir(graphe_neo4j):
        valeur = getattr(graphe_neo4j, nom)
        if nom.startswith("_REQ") and isinstance(valeur, str):
            assert "$tenant_id" in valeur
    assert isinstance(GrapheNeo4j(FausseSession()), GraphStore)
