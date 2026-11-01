"""Compatibilité : contradicteur vit dans :mod:`meridian.adapters.outbound.llm.contradicteur`."""
import sys

from meridian.adapters.outbound.llm import contradicteur as _module

sys.modules[__name__] = _module
