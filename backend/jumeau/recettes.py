"""Compatibilité : recettes vit dans :mod:`meridian.domain.recettes`."""
import sys

from meridian.domain import recettes as _module

sys.modules[__name__] = _module
