"""Compatibilité : jira vit dans :mod:`meridian.adapters.outbound.connectors.jira`."""
import sys

from meridian.adapters.outbound.connectors import jira as _module

sys.modules[__name__] = _module
