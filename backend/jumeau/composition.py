"""Compatibilité : la composition vit dans :mod:`meridian.application.composition`."""
import sys

from meridian.application import composition as _module

sys.modules[__name__] = _module
