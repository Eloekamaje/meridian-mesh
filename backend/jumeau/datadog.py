"""Compatibilité : datadog vit dans :mod:`meridian.adapters.outbound.connectors.datadog`."""
import sys

from meridian.adapters.outbound.connectors import datadog as _module

sys.modules[__name__] = _module
