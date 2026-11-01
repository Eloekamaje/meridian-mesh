"""Compatibilité : openapi_outils vit dans :mod:`meridian.application.openapi_outils`."""
import sys

from meridian.application import openapi_outils as _module

sys.modules[__name__] = _module
