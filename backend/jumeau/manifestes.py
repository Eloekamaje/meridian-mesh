"""Compatibilité : manifestes vit dans :mod:`meridian.adapters.outbound.connectors.manifestes`."""
import sys

from meridian.adapters.outbound.connectors import manifestes as _module

sys.modules[__name__] = _module
