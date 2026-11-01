"""Compatibilité : decision_cognitive vit dans :mod:`meridian.adapters.outbound.postgres.decision_cognitive`."""
import sys

from meridian.adapters.outbound.postgres import decision_cognitive as _module

sys.modules[__name__] = _module
