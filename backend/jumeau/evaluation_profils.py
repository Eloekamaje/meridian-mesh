"""Compatibilité : l'évaluation des profils vit dans :mod:`meridian.application.evaluation_profils`."""
import sys

from meridian.application import evaluation_profils as _module

sys.modules[__name__] = _module
