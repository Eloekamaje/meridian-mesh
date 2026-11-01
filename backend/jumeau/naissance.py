"""Compatibilité : naissance vit dans :mod:`meridian.adapters.outbound.connectors.naissance`."""
import sys

from meridian.adapters.outbound.connectors import naissance as _module

sys.modules[__name__] = _module
