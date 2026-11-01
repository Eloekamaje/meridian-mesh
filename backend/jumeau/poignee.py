"""Compatibilité : poignee vit dans :mod:`meridian.adapters.outbound.llm.poignee`."""
import sys

from meridian.adapters.outbound.llm import poignee as _module

sys.modules[__name__] = _module
