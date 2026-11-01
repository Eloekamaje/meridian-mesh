"""Compatibilité : le spécialiste de preuve vit dans :mod:`meridian.application.specialiste_preuve`."""
import sys

from meridian.application import specialiste_preuve as _module

sys.modules[__name__] = _module
