"""Compatibilité : evenements vit dans :mod:`meridian.adapters.outbound.redis.evenements`."""
import sys

from meridian.adapters.outbound.redis import evenements as _module

sys.modules[__name__] = _module
