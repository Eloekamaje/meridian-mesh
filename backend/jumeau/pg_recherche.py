"""Compatibilité : la recherche Postgres vit dans :mod:`meridian.adapters.outbound.postgres.pg_recherche`."""
import sys

from meridian.adapters.outbound.postgres import pg_recherche as _module

sys.modules[__name__] = _module
