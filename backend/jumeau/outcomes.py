"""Compatibilité : outcomes vit dans :mod:`meridian.adapters.outbound.postgres.outcomes`."""
import sys

from meridian.adapters.outbound.postgres import outcomes as _module

sys.modules[__name__] = _module
