"""Compatibilité : connecteurs vit dans :mod:`meridian.adapters.outbound.connectors.connecteurs`."""
import sys

from meridian.adapters.outbound.connectors import connecteurs as _module

sys.modules[__name__] = _module
