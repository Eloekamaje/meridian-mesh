"""Compatibilité : l'adaptateur Neo4j vit dans :mod:`meridian.adapters.outbound.neo4j.graphe_neo4j`."""
import sys

from meridian.adapters.outbound.neo4j import graphe_neo4j as _module

sys.modules[__name__] = _module
