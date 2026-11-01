"""Compatibilité : servicenow vit dans :mod:`meridian.adapters.outbound.connectors.servicenow`."""
import sys

from meridian.adapters.outbound.connectors import servicenow as _module

sys.modules[__name__] = _module
