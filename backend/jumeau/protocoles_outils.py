"""Compatibilité : protocoles_outils vit dans :mod:`meridian.application.protocoles_outils`."""
import sys

from meridian.application import protocoles_outils as _module

sys.modules[__name__] = _module
