"""Compatibilité : le backfill graphe vit dans :mod:`meridian.adapters.outbound.neo4j.backfill_graphe`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.neo4j.backfill_graphe import principal
    raise SystemExit(principal())
else:
    from meridian.adapters.outbound.neo4j import backfill_graphe as _module
    sys.modules[__name__] = _module
