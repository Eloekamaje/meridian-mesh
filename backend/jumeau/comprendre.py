"""Compatibilité : comprendre vit dans :mod:`meridian.adapters.outbound.postgres.comprendre`."""
import sys

from meridian.adapters.outbound.postgres import comprendre as _module

sys.modules[__name__] = _module
