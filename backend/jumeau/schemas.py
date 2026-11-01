"""Compatibilité : schemas vit dans :mod:`meridian.domain.schemas`."""
import sys

from meridian.domain import schemas as _module

sys.modules[__name__] = _module
