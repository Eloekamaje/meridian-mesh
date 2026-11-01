"""Compatibilité : le service d'analyse vit dans :mod:`meridian.application.analyse_service`."""
import sys

from meridian.application import analyse_service as _module

sys.modules[__name__] = _module
