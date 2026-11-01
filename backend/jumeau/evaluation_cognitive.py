"""Compatibilité : l'évaluation cognitive vit dans :mod:`meridian.application.evaluation_cognitive`."""
import sys

from meridian.application import evaluation_cognitive as _module

sys.modules[__name__] = _module
