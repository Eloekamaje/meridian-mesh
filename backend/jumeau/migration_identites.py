"""Compatibilité : migration_identites vit dans :mod:`meridian.adapters.outbound.mongo.migration_identites`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.mongo.migration_identites import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.mongo import migration_identites as _module
    sys.modules[__name__] = _module
