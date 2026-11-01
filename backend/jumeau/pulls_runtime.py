"""Compatibilité : pulls_runtime vit dans :mod:`meridian.adapters.outbound.postgres.pulls_runtime`."""
import sys

from meridian.adapters.outbound.postgres import pulls_runtime as _module

sys.modules[__name__] = _module
