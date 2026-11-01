"""Compatibilité : le flux SSE vit dans :mod:`meridian.adapters.inbound.http.flux`."""
import sys

from meridian.adapters.inbound.http import flux as _module

sys.modules[__name__] = _module
