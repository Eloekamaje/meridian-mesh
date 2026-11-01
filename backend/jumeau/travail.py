"""Compatibilité : travail vit dans :mod:`meridian.adapters.outbound.mongo.travail`."""
import sys

from meridian.adapters.outbound.mongo import travail as _module

sys.modules[__name__] = _module
