"""Compatibilité : le contexte tenant vit dans :mod:`meridian.domain.tenant`."""
import sys

from meridian.domain import tenant as _module

sys.modules[__name__] = _module
