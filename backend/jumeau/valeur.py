"""Compatibilité : valeur vit dans :mod:`meridian.adapters.outbound.postgres.valeur`."""
import sys

from meridian.adapters.outbound.postgres import valeur as _module

sys.modules[__name__] = _module
