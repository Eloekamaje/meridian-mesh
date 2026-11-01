"""Compatibilité : agent vit dans :mod:`meridian.adapters.outbound.llm.agent`."""
import sys

from meridian.adapters.outbound.llm import agent as _module

sys.modules[__name__] = _module
