"""Compatibilité : conception vit dans :mod:`meridian.adapters.outbound.llm.conception`."""
import sys

from meridian.adapters.outbound.llm import conception as _module

sys.modules[__name__] = _module
