"""Compatibilité : la temporalité vit dans :mod:`meridian.domain.temporalite`."""
import sys

from meridian.domain import temporalite as _module

sys.modules[__name__] = _module
