"""Compatibilité : les contrats de spécialistes vivent dans :mod:`meridian.domain.specialistes`."""
import sys

from meridian.domain import specialistes as _module

sys.modules[__name__] = _module
