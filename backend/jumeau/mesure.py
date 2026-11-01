"""Compatibilité : mesure vit dans :mod:`meridian.application.mesure`."""
import sys

from meridian.application import mesure as _module

sys.modules[__name__] = _module
