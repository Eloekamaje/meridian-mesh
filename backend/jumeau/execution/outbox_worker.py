"""Compatibilité : le worker outbox vit dans :mod:`meridian.adapters.inbound.worker.outbox_worker`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.inbound.worker.outbox_worker import principal
    raise SystemExit(principal())
else:
    from meridian.adapters.inbound.worker import outbox_worker as _module
    sys.modules[__name__] = _module
