"""Compatibilité : ingerer vit dans :mod:`meridian.adapters.outbound.connectors.ingerer`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.ingerer import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import ingerer as _module
    sys.modules[__name__] = _module
