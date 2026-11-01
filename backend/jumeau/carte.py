"""Compatibilité : carte vit dans :mod:`meridian.adapters.outbound.postgres.carte`."""
import sys

from meridian.adapters.outbound.postgres import carte as _module

sys.modules[__name__] = _module
