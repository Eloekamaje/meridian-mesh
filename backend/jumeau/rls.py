"""Compatibilité : l'adapter RLS vit dans :mod:`meridian.adapters.outbound.postgres.rls`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.postgres.rls import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.postgres import rls as _module
    sys.modules[__name__] = _module
