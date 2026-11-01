"""Compatibilité : ingestion_runtime vit dans :mod:`meridian.adapters.outbound.postgres.ingestion_runtime`."""
import sys

from meridian.adapters.outbound.postgres import ingestion_runtime as _module

sys.modules[__name__] = _module
