"""Compatibilité : le modèle d'interfaces vit dans :mod:`meridian.domain.interfaces`."""
import sys

from meridian.domain import interfaces as _module

sys.modules[__name__] = _module
