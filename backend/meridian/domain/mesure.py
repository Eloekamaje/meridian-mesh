"""Règles pures de mesure, partagées par le domaine, l'adaptateur et l'API.

Une mesure vide (``None``, booléen, chaîne blanche, mapping ou séquence vide) n'est pas
une mesure. Un nombre, y compris ``0``, en est une.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["mesure_renseignee"]


def mesure_renseignee(valeur: Any) -> bool:
    if valeur is None or isinstance(valeur, bool):
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    if isinstance(valeur, Mapping):
        return any(mesure_renseignee(element) for element in valeur.values())
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return bool(valeur)
    return True
