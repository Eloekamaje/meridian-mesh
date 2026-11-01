"""Compatibilité : decouverte vit dans :mod:`meridian.application.decouverte`."""
import sys

from meridian.application import decouverte as _module

sys.modules[__name__] = _module
