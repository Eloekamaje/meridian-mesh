"""Compatibilité : origine vit dans :mod:`meridian.domain.origine`."""
import sys

from meridian.domain import origine as _module

sys.modules[__name__] = _module
