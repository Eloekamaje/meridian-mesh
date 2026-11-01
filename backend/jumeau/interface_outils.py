"""Compatibilité : interface_outils vit dans :mod:`meridian.application.interface_outils`."""
import sys

if __name__ == "__main__":
    from meridian.application.interface_outils import main
    raise SystemExit(main())
else:
    from meridian.application import interface_outils as _module
    sys.modules[__name__] = _module
