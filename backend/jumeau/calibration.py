"""Compatibilité : la calibration vit dans :mod:`meridian.adapters.outbound.postgres.calibration`."""
import sys

from meridian.adapters.outbound.postgres import calibration as _module

sys.modules[__name__] = _module
