"""Compatibilité : specialiste_decouverte vit dans :mod:`meridian.adapters.outbound.postgres.specialiste_decouverte`."""
import sys

from meridian.adapters.outbound.postgres import specialiste_decouverte as _module

sys.modules[__name__] = _module
