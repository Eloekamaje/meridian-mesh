"""Compatibilité : application_memoire vit dans :mod:`meridian.adapters.outbound.postgres.application_memoire`."""
import sys

from meridian.adapters.outbound.postgres import application_memoire as _module

sys.modules[__name__] = _module
