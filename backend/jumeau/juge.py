"""Compatibilité : juge vit dans :mod:`meridian.adapters.outbound.llm.juge`."""
import sys

from meridian.adapters.outbound.llm import juge as _module

sys.modules[__name__] = _module
