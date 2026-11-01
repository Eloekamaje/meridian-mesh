"""Compatibilité : source_git vit dans :mod:`meridian.adapters.outbound.connectors.source_git`."""
import sys

from meridian.adapters.outbound.connectors import source_git as _module

sys.modules[__name__] = _module
