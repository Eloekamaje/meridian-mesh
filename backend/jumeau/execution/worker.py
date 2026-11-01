"""Compatibilité : le worker d'exécution vit dans :mod:`meridian.adapters.inbound.worker.execution_worker`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.inbound.worker.execution_worker import principal
    raise SystemExit(principal())
else:
    from meridian.adapters.inbound.worker import execution_worker as _module
    sys.modules[__name__] = _module
