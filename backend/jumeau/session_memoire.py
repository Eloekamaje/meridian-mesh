"""Compatibilité : la mémoire de session vit dans :mod:`meridian.adapters.outbound.postgres.session_memoire`."""
import sys

from meridian.adapters.outbound.postgres import session_memoire as _module

sys.modules[__name__] = _module
