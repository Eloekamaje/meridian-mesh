"""Compatibilité : le contrefactuel vit dans :mod:`meridian.domain.contrefactuel`."""
import sys

from meridian.domain import contrefactuel as _module

sys.modules[__name__] = _module
