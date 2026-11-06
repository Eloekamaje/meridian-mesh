"""Port d'indexation de code : chaque fournisseur rend des observations, jamais des Claims."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["CodeIndexPort"]


class CodeIndexPort(Protocol):
    provider: str

    def index(self, racine: str, *, fichiers: Sequence[str] = ()) -> list[Observation]: ...

    def couverture(self, racine: str, *, fichiers: Sequence[str] = ()) -> list[CouvertureFichier]: ...
