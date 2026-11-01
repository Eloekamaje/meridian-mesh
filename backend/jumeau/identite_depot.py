"""Compatibilité : le dépôt d'identité vit dans :mod:`meridian.adapters.outbound.postgres.identite_depot`."""
import sys

from meridian.adapters.outbound.postgres import identite_depot as _module

sys.modules[__name__] = _module
