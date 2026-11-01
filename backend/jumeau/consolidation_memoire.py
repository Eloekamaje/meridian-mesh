"""Compatibilité : la consolidation mémoire vit dans :mod:`meridian.application.consolidation_memoire`."""
import sys

from meridian.application import consolidation_memoire as _module

sys.modules[__name__] = _module
