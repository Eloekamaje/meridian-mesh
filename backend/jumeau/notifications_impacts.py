"""Compatibilité : notifications_impacts vit dans :mod:`meridian.adapters.outbound.redis.notifications_impacts`."""
import sys

from meridian.adapters.outbound.redis import notifications_impacts as _module

sys.modules[__name__] = _module
