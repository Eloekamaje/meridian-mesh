"""Compatibilité : twins_types vit dans :mod:`meridian.adapters.outbound.postgres.twins_types`."""
import sys

from meridian.adapters.outbound.postgres import twins_types as _module

sys.modules[__name__] = _module
