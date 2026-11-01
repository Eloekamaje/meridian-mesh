"""Compatibilité : appels vit dans :mod:`meridian.adapters.outbound.connectors.appels`."""
import sys

from meridian.adapters.outbound.connectors import appels as _module

sys.modules[__name__] = _module
