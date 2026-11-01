"""Compatibilité : reindexer vit dans :mod:`meridian.adapters.outbound.connectors.reindexer`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.reindexer import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import reindexer as _module
    sys.modules[__name__] = _module
