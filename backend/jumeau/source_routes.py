"""Compatibilité : le routeur des sources vit dans :mod:`meridian.adapters.inbound.http.sources`."""
import sys

from meridian.adapters.inbound.http import sources as _module

sys.modules[__name__] = _module
