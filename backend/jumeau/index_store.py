"""Compatibilité : index_store vit dans :mod:`meridian.adapters.outbound.connectors.index_store`."""
import sys

from meridian.adapters.outbound.connectors import index_store as _module

sys.modules[__name__] = _module
