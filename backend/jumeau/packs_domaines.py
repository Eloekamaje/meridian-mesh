"""Compatibilité : les packs de domaine vivent dans :mod:`meridian.domain.packs_domaines`."""
import sys

if __name__ == "__main__":
    import runpy

    runpy.run_module("meridian.domain.packs_domaines", run_name="__main__")
else:
    from meridian.domain import packs_domaines as _module

    sys.modules[__name__] = _module
