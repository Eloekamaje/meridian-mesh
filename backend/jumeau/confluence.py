"""Compatibilité : confluence vit dans :mod:`meridian.adapters.outbound.connectors.confluence`."""
import sys

from meridian.adapters.outbound.connectors import confluence as _module

sys.modules[__name__] = _module
