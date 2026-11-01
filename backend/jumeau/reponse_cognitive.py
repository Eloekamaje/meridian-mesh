"""Compatibilité : la réponse cognitive vit dans :mod:`meridian.application.reponse_cognitive`."""
import sys

from meridian.application import reponse_cognitive as _module

sys.modules[__name__] = _module
