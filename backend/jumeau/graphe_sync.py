"""Compatibilité : la synchronisation de graphe vit dans :mod:`meridian.application.graphe_sync`."""
import sys

from meridian.application import graphe_sync as _module

sys.modules[__name__] = _module
