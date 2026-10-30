"""Port GraphStore : topologie propriétaire, tenant, parcours et impacts."""
import pytest

from jumeau.graphe import Arete, GrapheMemoire, NoeudTwin


def graphe():
    g = GrapheMemoire()
    for i, type_ in (("a", "APPLICATION"), ("b", "APPLICATION"), ("c", "PROCESS")):
        g.upsert_twin(NoeudTwin(i, "banque", type_, i.upper()))
    g.upsert_relation(Arete("r1", "banque", "a", "b"))
    g.upsert_relation(Arete("r2", "banque", "b", "c"))
    return g


def test_upsert_et_isolation_tenant():
    g = graphe()
    g.upsert_twin(NoeudTwin("x", "autre", "APPLICATION", "X"))
    assert len(g.noeuds) == 4
    assert [v["id"] for v in g.voisins("banque", "a")] == ["b"]
    assert g.voisins("autre", "a") == []


def test_voisins_chemins_impact_et_cycles():
    g = graphe()
    assert g.chemins("banque", "a", "c") == [["a", "b", "c"]]
    impact = g.impact("banque", "b", 2)
    assert [v["id"] for v in impact["aval"]] == ["c"]
    assert [v["id"] for v in impact["amont"]] == ["a"]
    g.upsert_relation(Arete("r3", "banque", "c", "a"))  # cycle
    assert [v["id"] for v in g.voisins("banque", "a", 3)] == ["b", "c"]  # le cycle ne revisite pas la source


def test_une_relation_exige_ses_deux_twins_et_un_type_stable():
    g = GrapheMemoire()
    g.upsert_twin(NoeudTwin("a", "banque"))
    with pytest.raises(ValueError):
        g.upsert_relation(Arete("r", "banque", "a", "absent"))
    with pytest.raises(ValueError):
        g.upsert_twin(NoeudTwin("a", "banque", "PROCESS"))


def test_relation_close_ou_invalide_est_ignoree():
    g = graphe()
    g.upsert_relation(Arete("fermee", "banque", "a", "c", valid_to="2020-01-01T00:00:00Z"))
    assert [v["id"] for v in g.voisins("banque", "a")] == ["b"]
    with pytest.raises(ValueError):
        Arete("loop", "banque", "a", "a")
    with pytest.raises(ValueError):
        Arete("etat", "banque", "a", "b", etat="inconnu")


def test_le_port_ne_depend_pas_de_postgres_ni_de_vendeur():
    import inspect
    from jumeau import graphe
    source = inspect.getsource(graphe)
    assert "import psycopg" not in source and "from neo4j" not in source and "from neptune" not in source
