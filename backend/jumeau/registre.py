"""Compatibilité : registre vit dans :mod:`meridian.adapters.outbound.mongo.registre`."""
import sys

from meridian.adapters.outbound.mongo import registre as _module

sys.modules[__name__] = _module
