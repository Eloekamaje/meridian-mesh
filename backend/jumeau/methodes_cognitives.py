"""Compatibilité : les méthodes cognitives vivent dans :mod:`meridian.domain.methodes_cognitives`."""
import sys

from meridian.domain import methodes_cognitives as _module

sys.modules[__name__] = _module
