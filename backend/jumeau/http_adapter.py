"""Compatibilité : http_adapter vit dans :mod:`meridian.adapters.outbound.connectors.http_adapter`."""
import sys

from meridian.adapters.outbound.connectors import http_adapter as _module

sys.modules[__name__] = _module
