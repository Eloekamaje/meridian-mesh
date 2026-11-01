"""Compatibilité : le Context Pack vit dans :mod:`meridian.domain.contexte`."""
import sys

from meridian.domain import contexte as _module

sys.modules[__name__] = _module
