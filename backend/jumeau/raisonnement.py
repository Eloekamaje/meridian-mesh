"""Compatibilité : la trace de raisonnement vit dans :mod:`meridian.domain.raisonnement`."""
import sys

from meridian.domain import raisonnement as _module

sys.modules[__name__] = _module
