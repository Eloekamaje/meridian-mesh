"""Compatibilité : le résolveur de contexte vit dans :mod:`meridian.application.resolveur_contexte`."""
import sys

from meridian.application import resolveur_contexte as _module

sys.modules[__name__] = _module
