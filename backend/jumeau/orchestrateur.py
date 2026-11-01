"""Compatibilité : orchestrateur vit dans :mod:`meridian.adapters.outbound.llm.orchestrateur`."""
import sys

from meridian.adapters.outbound.llm import orchestrateur as _module

sys.modules[__name__] = _module
