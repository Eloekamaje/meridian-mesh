"""Compatibilité : specialiste_impact vit dans :mod:`meridian.adapters.outbound.postgres.specialiste_impact`."""
import sys

from meridian.adapters.outbound.postgres import specialiste_impact as _module

sys.modules[__name__] = _module
