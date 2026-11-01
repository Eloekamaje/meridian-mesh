"""Compatibilité : l'évaluation des outils vit dans :mod:`meridian.application.evaluation_outils`."""
import sys

if __name__ == "__main__":
    from meridian.application.evaluation_outils import main

    raise SystemExit(main())
else:
    from meridian.application import evaluation_outils as _module

    sys.modules[__name__] = _module
