"""Compatibilité : le projecteur graphe vit dans :mod:`meridian.adapters.outbound.neo4j.projecteur_graphe`."""
import sys

from meridian.adapters.outbound.neo4j import projecteur_graphe as _module

sys.modules[__name__] = _module
