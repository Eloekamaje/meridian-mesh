"""Compatibilité : audit_harness vit dans :mod:`meridian.adapters.outbound.postgres.audit_harness`."""
import sys

from meridian.adapters.outbound.postgres import audit_harness as _module

sys.modules[__name__] = _module
