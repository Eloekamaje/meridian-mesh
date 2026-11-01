"""Compatibilité : le registre capacitaire vit dans :mod:`meridian.domain.capacites`."""
import sys

from meridian.domain import capacites as _module

sys.modules[__name__] = _module
