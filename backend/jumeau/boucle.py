"""Compatibilité : boucle vit dans :mod:`meridian.adapters.outbound.postgres.boucle`."""
import sys

from meridian.adapters.outbound.postgres import boucle as _module

sys.modules[__name__] = _module
