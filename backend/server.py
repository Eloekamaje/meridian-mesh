"""Point d'entrée ASGI : le code HTTP vit dans :mod:`meridian.adapters.inbound.http.legacy`.

Le module est remplacé dans ``sys.modules`` par l'adapter legacy afin que les monkeypatches de
tests et les accès ``server.db`` / ``server.app`` continuent de viser les mêmes globals.
"""
import sys

from meridian.adapters.inbound.http import legacy

sys.modules[__name__] = legacy
