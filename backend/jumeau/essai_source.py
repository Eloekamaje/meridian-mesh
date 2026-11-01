"""Compatibilité : essai_source vit dans :mod:`meridian.adapters.outbound.connectors.essai_source`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.essai_source import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import essai_source as _module
    sys.modules[__name__] = _module
