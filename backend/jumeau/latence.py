"""Compatibilité : latence vit dans :mod:`meridian.adapters.outbound.llm.latence`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.llm.latence import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.llm import latence as _module
    sys.modules[__name__] = _module
