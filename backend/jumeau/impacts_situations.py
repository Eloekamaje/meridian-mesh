"""Compatibilité : impacts_situations vit dans :mod:`meridian.application.impacts_situations`."""
import sys

from meridian.application import impacts_situations as _module

sys.modules[__name__] = _module
