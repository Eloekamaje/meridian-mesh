"""Compatibilité : memoire_org vit dans :mod:`meridian.adapters.outbound.postgres.memoire_org`."""
import sys

from meridian.adapters.outbound.postgres import memoire_org as _module

sys.modules[__name__] = _module
