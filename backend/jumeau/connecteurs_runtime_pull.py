"""Compatibilité : connecteurs_runtime_pull vit dans :mod:`meridian.adapters.outbound.connectors.connecteurs_runtime_pull`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.connecteurs_runtime_pull import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import connecteurs_runtime_pull as _module
    sys.modules[__name__] = _module
