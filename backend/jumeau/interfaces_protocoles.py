"""Compatibilité : interfaces_protocoles vit dans :mod:`meridian.application.interfaces_protocoles`."""
import sys

from meridian.application import interfaces_protocoles as _module

sys.modules[__name__] = _module
