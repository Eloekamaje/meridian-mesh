"""Compatibilité : le routeur vit dans :mod:`meridian.adapters.inbound.http.mesh_vue`.

Le module est remplacé dans ``sys.modules`` pour que les monkeypatches de tests visent les mêmes globals.
"""
import sys

from meridian.adapters.inbound.http import mesh_vue as _module

sys.modules[__name__] = _module
