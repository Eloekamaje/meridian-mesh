"""Compatibilité : evaluation vit dans :mod:`meridian.adapters.outbound.llm.evaluation`."""
import sys

if __name__ == "__main__":
    from meridian.adapters.outbound.llm.evaluation import main
    raise SystemExit(main())
else:
    from meridian.adapters.outbound.llm import evaluation as _module
    sys.modules[__name__] = _module
