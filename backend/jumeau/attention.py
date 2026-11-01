"""Compatibilité : le score d'attention vit dans :mod:`meridian.domain.attention`."""
import sys

from meridian.domain import attention as _module

sys.modules[__name__] = _module
