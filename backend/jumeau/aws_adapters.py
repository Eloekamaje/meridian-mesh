"""Compatibilité : les adapters AWS vivent dans :mod:`meridian.adapters.outbound.aws`."""
import sys

from meridian.adapters.outbound.aws import adapters as _module

sys.modules[__name__] = _module
