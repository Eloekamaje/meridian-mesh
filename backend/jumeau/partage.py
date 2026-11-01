"""Compatibilité : partage vit dans :mod:`meridian.adapters.outbound.redis.partage`."""
import sys

from meridian.adapters.outbound.redis import partage as _module

sys.modules[__name__] = _module
