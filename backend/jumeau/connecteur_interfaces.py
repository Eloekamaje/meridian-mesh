"""Compatibilité : connecteur_interfaces vit dans :mod:`meridian.adapters.outbound.connectors.connecteur_interfaces`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.connectors.connecteur_interfaces import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.connectors import connecteur_interfaces as _module
    sys.modules[__name__] = _module
