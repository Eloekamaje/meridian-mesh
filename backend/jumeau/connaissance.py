"""Compatibilité : connaissance vit dans :mod:`meridian.adapters.outbound.postgres.connaissance`."""
import sys

from meridian.adapters.outbound.postgres import connaissance as _module

sys.modules[__name__] = _module
