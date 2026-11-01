"""Compatibilité : le Value Ledger vit dans :mod:`meridian.adapters.outbound.postgres.valeur_depot`."""
import sys

from meridian.adapters.outbound.postgres import valeur_depot as _module

sys.modules[__name__] = _module
