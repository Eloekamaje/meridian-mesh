"""Compatibilité : tours_redis vit dans :mod:`meridian.adapters.outbound.redis.tours_redis`."""
import sys

from meridian.adapters.outbound.redis import tours_redis as _module

sys.modules[__name__] = _module
