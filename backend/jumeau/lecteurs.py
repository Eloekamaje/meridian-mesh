"""Compatibilité : lecteurs vit dans :mod:`meridian.adapters.outbound.connectors.lecteurs`."""
import sys

from meridian.adapters.outbound.connectors import lecteurs as _module

sys.modules[__name__] = _module
