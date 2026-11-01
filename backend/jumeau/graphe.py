"""Compatibilité : le modèle de graphe vit dans :mod:`meridian.domain.graphe`."""
import sys

from meridian.domain import graphe as _module

sys.modules[__name__] = _module
