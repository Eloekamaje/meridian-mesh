"""Compatibilité : examen vit dans :mod:`meridian.adapters.outbound.postgres.examen`."""
import sys

from meridian.adapters.outbound.postgres import examen as _module

sys.modules[__name__] = _module
