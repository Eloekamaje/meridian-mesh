"""Compatibilité : parite_mongo vit dans :mod:`meridian.adapters.outbound.mongo.parite_mongo`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.mongo.parite_mongo import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.mongo import parite_mongo as _module
    sys.modules[__name__] = _module
