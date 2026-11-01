"""Compatibilité : recoupement vit dans :mod:`meridian.adapters.outbound.postgres.recoupement`."""
import sys

from meridian.adapters.outbound.postgres import recoupement as _module

sys.modules[__name__] = _module
