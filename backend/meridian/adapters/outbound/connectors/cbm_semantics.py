"""Outils sémantiques CBM pour le harness d'exploration : routes, symboles et requêtes de graphe."""
from __future__ import annotations

import json

from meridian.adapters.outbound.connectors import cbm


class CbmSemanticTools:
    """Un projet CBM par alias de dépôt ; aucune observation n'est inventée hors projet indexé."""

    def __init__(self, projets: dict[str, str]):
        self.projets = {str(alias): str(projet) for alias, projet in (projets or {}).items() if projet}

    def _projet(self, args: dict) -> str:
        alias = str(args.get("repo") or "").strip()
        projet = self.projets.get(alias)
        if not projet:
            raise ValueError(f"aucun index CBM pour le dépôt {alias or '?'}")
        return projet

    def _query(self, args: dict, requete: str) -> dict:
        projet = self._projet(args)
        resultat = cbm._cli(
            "query_graph", "--project", projet, "--query", requete, "--format", "json"
        )
        return {"project": projet, "columns": resultat.get("columns") or [],
                "rows": resultat.get("rows") or [], "has_more": bool(resultat.get("has_more"))}

    def routes(self, args: dict) -> dict:
        return self._query(args, "MATCH (f)-[:HANDLES]->(r:Route) "
                                "RETURN f.file_path AS chemin, f.start_line AS debut, "
                                "f.end_line AS fin, r.method AS methode, r.name AS route "
                                "ORDER BY chemin, debut")

    def symbols(self, args: dict) -> dict:
        motif = str(args.get("pattern") or args.get("query") or "").strip()
        if not motif:
            raise ValueError("motif de symbole requis")
        projet = self._projet(args)
        resultat = cbm._cli(
            "search_graph", "--project", projet, "--name_pattern", motif,
            "--limit", str(min(int(args.get("limit", 50)), 200)), "--format", "json",
        )
        return {"project": projet, "result": resultat}

    def query(self, args: dict) -> dict:
        requete = str(args.get("query") or "").strip()
        if not requete or len(requete) > 4000:
            raise ValueError("requête CBM vide ou trop longue")
        return self._query(args, requete)

    def outils(self) -> dict:
        return {"cbm_routes": self.routes, "cbm_symbols": self.symbols, "cbm_query": self.query}

    def schemas(self) -> dict:
        return {
            "cbm_routes": {"repo": "alias"},
            "cbm_symbols": {"repo": "alias", "pattern": "nom", "limit": 50},
            "cbm_query": {"repo": "alias", "query": "Cypher"},
        }


__all__ = ["CbmSemanticTools"]
