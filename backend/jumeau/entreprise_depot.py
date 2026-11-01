"""Compatibilité : le dépôt d'entreprise vit dans :mod:`meridian.adapters.outbound.postgres.entreprise_depot`."""
import sys

from meridian.adapters.outbound.postgres import entreprise_depot as _module

sys.modules[__name__] = _module
