"""Compatibilité : le dépôt Postgres vit dans :mod:`meridian.adapters.outbound.postgres.execution_depot`."""
import sys

from meridian.adapters.outbound.postgres import execution_depot as _module

sys.modules[__name__] = _module
