"""Compatibilité : flore vit dans :mod:`meridian.adapters.outbound.llm.flore`."""
import sys

from meridian.adapters.outbound.llm import flore as _module

sys.modules[__name__] = _module
