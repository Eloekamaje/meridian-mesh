"""Compatibilité : depot vit dans :mod:`meridian.adapters.outbound.postgres.depot`."""
import sys

from meridian.adapters.outbound.postgres import depot as _module

sys.modules[__name__] = _module
