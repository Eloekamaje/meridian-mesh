"""Compatibilité : auth_source vit dans :mod:`meridian.adapters.outbound.connectors.auth_source`."""
import sys

from meridian.adapters.outbound.connectors import auth_source as _module

sys.modules[__name__] = _module
