"""Les graphes Graphify construits sur un sous-dossier rendent des chemins préfixés."""
import json

from meridian.adapters.outbound.connectors.graphify_semantics import GraphifySemanticTools


def _graphe(tmp_path):
    chemin = tmp_path / "graph.json"
    chemin.write_text(json.dumps({
        "nodes": [{"id": "n1", "label": "Route", "source_file": "app.py",
                   "source_location": "L1", "community_name": "api"}],
        "links": [],
    }), encoding="utf-8")
    return chemin


def test_graphify_prefixe_les_chemins(tmp_path):
    outils = GraphifySemanticTools(_graphe(tmp_path), prefix="api")
    assert outils.search({"query": "route"})["nodes"][0]["source_file"] == "api/app.py"
    assert outils.node({"id": "n1"})["node"]["source_file"] == "api/app.py"


def test_graphify_ne_double_pas_le_prefixe(tmp_path):
    outils = GraphifySemanticTools(_graphe(tmp_path), prefix="api")
    assert outils._vue({"source_file": "api/app.py"})["source_file"] == "api/app.py"
