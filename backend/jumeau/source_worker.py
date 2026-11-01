"""Compatibilité : le worker d'ingestion vit dans :mod:`meridian.adapters.inbound.worker.source_worker`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.inbound.worker.source_worker import main
    raise SystemExit(main())
else:
    from meridian.adapters.inbound.worker import source_worker as _module
    sys.modules[__name__] = _module
