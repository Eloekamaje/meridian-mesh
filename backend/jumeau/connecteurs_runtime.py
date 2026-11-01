"""Compatibilité : connecteurs_runtime vit dans :mod:`meridian.adapters.outbound.connectors.connecteurs_runtime`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.connecteurs_runtime import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import connecteurs_runtime as _module
    sys.modules[__name__] = _module
