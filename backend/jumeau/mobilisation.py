"""Compatibilité : mobilisation vit dans :mod:`meridian.adapters.outbound.llm.mobilisation`."""
import sys

from meridian.adapters.outbound.llm import mobilisation as _module

sys.modules[__name__] = _module
