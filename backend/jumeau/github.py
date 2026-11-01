"""Compatibilité : github vit dans :mod:`meridian.adapters.outbound.connectors.github`."""
import sys

from meridian.adapters.outbound.connectors import github as _module

sys.modules[__name__] = _module
