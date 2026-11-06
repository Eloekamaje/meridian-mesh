"""Graph RAG global : communautés factuelles, sans synthèse inventée."""
from meridian.application import graphe_global
from meridian.domain.graphe import Arete, GrapheMemoire, NoeudTwin


def _graphe():
    g = GrapheMemoire()
    for identifiant in ("a", "b", "c", "d"):
        g.upsert_twin(NoeudTwin(identifiant, "banque", "APPLICATION", identifiant.upper()))
    g.upsert_relation(Arete("r1", "banque", "a", "b"))
    g.upsert_relation(Arete("r2", "banque", "b", "c"))
    return g


def test_les_voisins_forment_une_communaute_bornee():
    resultat = graphe_global.resume_contextuel(_graphe(), "banque", ["a"])
    assert resultat["mode"] == "global-deterministe"
    assert resultat["communautes"][0]["taille"] == 3
    assert set(resultat["communautes"][0]["entites"]) == {"a", "b", "c"}


def test_un_noeud_isole_ne_cree_pas_de_bruit():
    resultat = graphe_global.resume_contextuel(_graphe(), "banque", ["d"])
    assert resultat["communautes"][0]["taille"] == 1
    assert "d" in resultat["communautes"][0]["entites"]
