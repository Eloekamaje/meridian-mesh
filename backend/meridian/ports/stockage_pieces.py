"""Port de stockage binaire des pièces jointes.

Les métadonnées restent dans la collection `pieces` ; ce port ne gère que le contenu
du fichier et son identifiant de stockage (`fichier_id`).
"""
from __future__ import annotations

from typing import Any, Protocol


class StockagePieces(Protocol):
    async def ecrire(self, cle: str, data: bytes, metadata: dict[str, Any]) -> str:
        """Écrit le contenu et rend son identifiant de stockage."""

    async def lire(self, identifiant: str) -> bytes:
        """Lit le contenu ; lève FileNotFoundError s'il a disparu."""

    async def supprimer(self, identifiant: str) -> None:
        """Supprime le contenu ; idempotent."""

    async def deplacer(self, identifiants: list[str], case_id: str) -> None:
        """Met à jour les métadonnées de stockage après un déplacement de pièces."""

    async def vider(self) -> None:
        """Supprime tous les contenus du stockage (réinitialisation de démonstration)."""
