"""Compatibilité : methodes vit dans :mod:`meridian.application.methodes`."""
import sys

from meridian.application import methodes as _module

sys.modules[__name__] = _module
