#!/usr/bin/env python3
"""Enquête unifiée sur une application composée de plusieurs dépôts Git."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from meridian.application.exploration_agent import ExplorationHarness, RepoSnapshot  # noqa: E402


def _adaptateur():
    from meridian.adapters.outbound.llm.exploration_adapter import ExplorationAdapter
    return ExplorationAdapter()


def _semantique(manifeste):
    outils, schemas = {}, {}
    projets = {
        alias: valeur.get("cbm_project")
        for alias, valeur in manifeste.items()
        if isinstance(valeur, dict) and valeur.get("cbm_project")
    }
    if projets:
        from meridian.adapters.outbound.connectors.cbm_semantics import CbmSemanticTools
        cbm = CbmSemanticTools(projets)
        outils.update(cbm.outils())
        schemas.update(cbm.schemas())
    graphify = manifeste.get("_graphify")
    graph_path = graphify.get("path") if isinstance(graphify, dict) else graphify
    if graph_path:
        from meridian.adapters.outbound.connectors.graphify_semantics import GraphifySemanticTools
        graphe = GraphifySemanticTools(graph_path)
        outils.update(graphe.outils())
        schemas.update(graphe.schemas())
    return outils, schemas


def main(argv=None) -> int:
    from meridian.application.exploration_agent import main as executer
    return executer(argv, adaptateur_defaut=_adaptateur, fabrique_semantique=_semantique)


if __name__ == "__main__":
    raise SystemExit(main())
