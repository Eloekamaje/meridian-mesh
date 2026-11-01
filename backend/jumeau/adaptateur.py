"""Compatibilité : adaptateur vit dans :mod:`meridian.adapters.outbound.connectors.adaptateur`."""
import sys

from meridian.adapters.outbound.connectors import adaptateur as _module

sys.modules[__name__] = _module
