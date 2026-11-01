"""Compatibilité : la résolution d'identité vit dans :mod:`meridian.domain.identite`."""
import sys

from meridian.domain import identite as _module

sys.modules[__name__] = _module
