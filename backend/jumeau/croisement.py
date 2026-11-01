"""Compatibilité : croisement vit dans :mod:`meridian.adapters.outbound.postgres.croisement`."""
import sys

from meridian.adapters.outbound.postgres import croisement as _module

sys.modules[__name__] = _module
