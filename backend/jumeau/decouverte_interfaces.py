"""Compatibilité : decouverte_interfaces vit dans :mod:`meridian.adapters.outbound.postgres.decouverte_interfaces`."""
import sys

from meridian.adapters.outbound.postgres import decouverte_interfaces as _module

sys.modules[__name__] = _module
