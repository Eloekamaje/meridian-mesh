"""Compatibilité : ingestion_outils vit dans :mod:`meridian.application.ingestion_outils`."""
import sys

if __name__ == "__main__":
    from meridian.application.ingestion_outils import main
    raise SystemExit(main())
else:
    from meridian.application import ingestion_outils as _module
    sys.modules[__name__] = _module
