"""Compatibilité : les profils vivent dans :mod:`meridian.domain.profils`."""
import sys

from meridian.domain import profils as _module

sys.modules[__name__] = _module
