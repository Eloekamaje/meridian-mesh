"""Compatibilité : la rétention vit dans :mod:`meridian.adapters.outbound.postgres.retention`."""
import sys

from meridian.adapters.outbound.postgres import retention as _module

sys.modules[__name__] = _module
