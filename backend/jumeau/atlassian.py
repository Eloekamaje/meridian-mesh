"""Compatibilité : atlassian vit dans :mod:`meridian.adapters.outbound.connectors.atlassian`."""
import sys

from meridian.adapters.outbound.connectors import atlassian as _module

sys.modules[__name__] = _module
