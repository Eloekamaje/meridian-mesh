"""Compatibilité : temps vit dans :mod:`meridian.adapters.outbound.postgres.temps`."""
import sys

from meridian.adapters.outbound.postgres import temps as _module

sys.modules[__name__] = _module
