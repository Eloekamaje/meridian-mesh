"""Compatibilité : harness vit dans :mod:`meridian.adapters.outbound.llm.harness`."""
import sys

from meridian.adapters.outbound.llm import harness as _module

sys.modules[__name__] = _module
