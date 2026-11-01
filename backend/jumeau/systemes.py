"""Compatibilité : systemes vit dans :mod:`meridian.adapters.outbound.connectors.systemes`."""
import sys

from meridian.adapters.outbound.connectors import systemes as _module

sys.modules[__name__] = _module
