"""Compatibilité : portefeuille vit dans :mod:`meridian.adapters.outbound.postgres.portefeuille`."""
import sys

from meridian.adapters.outbound.postgres import portefeuille as _module

sys.modules[__name__] = _module
