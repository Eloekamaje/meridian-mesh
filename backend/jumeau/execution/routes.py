"""Compatibilité : le routeur HTTP des runs vit dans :mod:`meridian.adapters.inbound.http.runs`."""
import sys

from meridian.adapters.inbound.http import runs as _module

sys.modules[__name__] = _module
