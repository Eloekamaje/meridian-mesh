"""Compatibilité : la fabrique GraphStore vit dans :mod:`meridian.adapters.outbound.neo4j.graph_store`."""
import sys

from meridian.adapters.outbound.neo4j import graph_store as _module

sys.modules[__name__] = _module
