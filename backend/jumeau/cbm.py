"""Compatibilité : cbm vit dans :mod:`meridian.adapters.outbound.connectors.cbm`."""
import sys

from meridian.adapters.outbound.connectors import cbm as _module

sys.modules[__name__] = _module
