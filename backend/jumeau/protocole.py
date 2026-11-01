"""Compatibilité : protocole vit dans :mod:`meridian.application.protocole`."""
import sys

from meridian.application import protocole as _module

sys.modules[__name__] = _module
