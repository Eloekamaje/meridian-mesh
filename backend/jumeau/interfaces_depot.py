"""Compatibilité : le dépôt d'interfaces vit dans :mod:`meridian.adapters.outbound.postgres.interfaces_depot`."""
import sys

from meridian.adapters.outbound.postgres import interfaces_depot as _module

sys.modules[__name__] = _module
