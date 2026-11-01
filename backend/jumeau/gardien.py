"""Compatibilité : gardien vit dans :mod:`meridian.adapters.outbound.llm.gardien`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.llm.gardien import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.llm import gardien as _module
    sys.modules[__name__] = _module
