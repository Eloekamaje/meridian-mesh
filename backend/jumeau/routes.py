"""Compatibilité : le routeur des interfaces vit dans :mod:`meridian.adapters.inbound.http.interfaces`."""
import sys

from meridian.adapters.inbound.http import interfaces as _module

sys.modules[__name__] = _module
