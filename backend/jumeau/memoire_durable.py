"""Compatibilité : la mémoire durable vit dans :mod:`meridian.adapters.outbound.postgres.memoire_durable`."""
import sys

from meridian.adapters.outbound.postgres import memoire_durable as _module

sys.modules[__name__] = _module
