"""Compatibilité : chargeur_manifestes vit dans :mod:`meridian.adapters.outbound.connectors.chargeur_manifestes`."""
import sys

from meridian.adapters.outbound.connectors import chargeur_manifestes as _module

sys.modules[__name__] = _module
