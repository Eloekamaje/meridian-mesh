"""Compatibilité : executeur vit dans :mod:`meridian.application.executeur`."""
import sys

from meridian.application import executeur as _module

sys.modules[__name__] = _module
