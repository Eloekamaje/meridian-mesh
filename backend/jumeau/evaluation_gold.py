"""Compatibilité : evaluation_gold vit dans :mod:`meridian.application.evaluation_gold`."""
import runpy
import sys

if __name__ == "__main__":
    runpy.run_module("meridian.application.evaluation_gold", run_name="__main__")
else:
    from meridian.application import evaluation_gold as _module
    sys.modules[__name__] = _module
