"""Port étroit du runtime de naissance d'un jumeau."""
from __future__ import annotations

from typing import Any, Protocol


class NaissanceRuntime(Protocol):
    def disponible(self) -> bool: ...

    def en_cours(self, jid: str) -> bool: ...

    async def demarrer(
        self, commande: dict[str, Any], jid: str, *, acteur: str, espace_id: str
    ) -> None: ...

    async def notifier(self, jid: str, texte: str) -> None: ...
