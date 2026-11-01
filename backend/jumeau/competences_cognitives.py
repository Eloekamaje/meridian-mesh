"""Compatibilité : les compétences cognitives vivent dans :mod:`meridian.domain.competences_cognitives`."""
import sys

from meridian.domain import competences_cognitives as _module

sys.modules[__name__] = _module
