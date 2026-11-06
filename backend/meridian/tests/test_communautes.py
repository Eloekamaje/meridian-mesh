"""Communautés de graphe et rapports précompilés."""
from meridian.application import communautes
from meridian.domain.graphe import Arete, GrapheMemoire, NoeudTwin


def test_label_propagation_regroupe_les_voisins():
    g = GrapheMemoire()
    for identifiant in ("a", "b", "c", "d", "e"):
        g.upsert_twin(NoeudTwin(identifiant, "banque"))
    g.upsert_relation(Arete("r1", "banque", "a", "b"))
    g.upsert_relation(Arete("r2", "banque", "b", "c"))
    g.upsert_relation(Arete("r3", "banque", "d", "e"))
    groupes = communautes.construire(g, "banque", ["a", "b", "c", "d", "e"], domaines={"a": "client"})
    assert len(groupes) == 2
    assert {len(g["membres"]) for g in groupes} == {3, 2}
    assert all(g["fingerprint"] for g in groupes)


def test_le_rapport_ne_depasse_pas_les_faits_du_groupe():
    texte = communautes.rapport({"membres": ["a", "b"], "relations": 1, "domain": ["client"]})
    assert "a" in texte and "client" in texte
    assert "preuve" not in texte.lower()


def test_la_hierarchie_produit_plusieurs_niveaux_stables():
    g = GrapheMemoire()
    for identifiant in ("a", "b", "c", "d", "e", "f"):
        g.upsert_twin(NoeudTwin(identifiant, "banque"))
    for i, (a, b) in enumerate((("a", "b"), ("b", "c"), ("d", "e"), ("e", "f"), ("c", "d"))):
        g.upsert_relation(Arete(f"r{i}", "banque", a, b))
    niveaux = communautes.construire_hierarchique(g, "banque", list("abcdef"))
    assert niveaux
    assert all(niveau["communautes"] for niveau in niveaux)
    assert all(c["fingerprint"] for n in niveaux for c in n["communautes"])
