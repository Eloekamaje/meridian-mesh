"""Compatibilité : retrieval_memoire vit dans :mod:`meridian.adapters.outbound.postgres.retrieval_memoire`."""
import sys

from meridian.adapters.outbound.postgres import retrieval_memoire as _module

sys.modules[__name__] = _module
