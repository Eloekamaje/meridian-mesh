"""Compatibilité : mcp_outils vit dans :mod:`meridian.application.mcp_outils`."""
import sys

from meridian.application import mcp_outils as _module

sys.modules[__name__] = _module
