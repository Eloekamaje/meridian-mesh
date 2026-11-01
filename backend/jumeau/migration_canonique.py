"""Compatibilité : migration_canonique vit dans :mod:`meridian.adapters.outbound.postgres.migration_canonique`."""
import sys

from meridian.adapters.outbound.postgres import migration_canonique as _module

sys.modules[__name__] = _module
