"""Compatibilité : les types d'exécution vivent dans :mod:`meridian.application.execution.modele`."""
import sys

from meridian.application.execution import modele as _module

sys.modules[__name__] = _module
