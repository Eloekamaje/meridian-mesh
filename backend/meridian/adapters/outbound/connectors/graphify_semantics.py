"""Outils sémantiques Graphify : recherche en lecture seule dans un graphe exporté."""
from __future__ import annotations

import json
from pathlib import Path


class GraphifySemanticTools:
    def __init__(self, graph_path, prefix=""):
        self.graph_path = Path(graph_path).expanduser().resolve()
        self.prefix = str(prefix or "").strip("/")
        self._graph = None

    def _vue(self, noeud: dict) -> dict:
        """Ajoute le préfixe du dépôt aux chemins d'un graphe construit sur un sous-dossier."""
        vue = dict(noeud)
        source = str(vue.get("source_file") or "")
        if self.prefix and source and not source.startswith(self.prefix + "/"):
            vue["source_file"] = f"{self.prefix}/{source}"
        return vue

    def _charger(self):
        if self._graph is None:
            self._graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        return self._graph

    def search(self, args: dict) -> dict:
        requete = str(args.get("query") or args.get("pattern") or "").strip().lower()
        if not requete:
            raise ValueError("requête Graphify requise")
        limite = min(int(args.get("limit", 50)), 200)
        noeuds = self._charger().get("nodes") or []
        correspondances = [
            {cle: self._vue(n).get(cle)
             for cle in ("id", "label", "source_file", "source_location", "community_name")}
            for n in noeuds
            if requete in str(n.get("label") or "").lower()
            or requete in str(n.get("id") or "").lower()
            or requete in str(n.get("source_file") or "").lower()
        ][:limite]
        return {"graph": str(self.graph_path), "nodes": correspondances,
                "count": len(correspondances), "limit": limite}

    def node(self, args: dict) -> dict:
        identifiant = str(args.get("id") or args.get("label") or "").strip()
        if not identifiant:
            raise ValueError("identifiant Graphify requis")
        noeuds = self._charger().get("nodes") or []
        trouve = next((n for n in noeuds if n.get("id") == identifiant or n.get("label") == identifiant), None)
        if trouve is None:
            raise ValueError("nœud Graphify introuvable")
        liens = [l for l in self._charger().get("links") or []
                 if l.get("source") == identifiant or l.get("target") == identifiant]
        return {"node": self._vue(trouve), "links": liens[:200]}

    def outils(self) -> dict:
        return {"graphify_search": self.search, "graphify_node": self.node}

    def schemas(self) -> dict:
        return {"graphify_search": {"query": "texte", "limit": 50},
                "graphify_node": {"id": "identifiant"}}


__all__ = ["GraphifySemanticTools"]
