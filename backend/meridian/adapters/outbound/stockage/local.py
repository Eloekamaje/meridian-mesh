"""Stockage local sur système de fichiers, pour les déploiements sans objet distant."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any


class LocalStockage:
    nom = "local"

    def __init__(self, racine: str | Path):
        self.racine = Path(racine).expanduser().resolve()

    def _chemin(self, cle: str) -> Path:
        morceaux = [morceau for morceau in str(cle).replace("\\", "/").split("/") if morceau]
        if not morceaux or any(morceau in {".", ".."} for morceau in morceaux):
            raise ValueError(f"clé de stockage invalide : {cle!r}")
        chemin = (self.racine / Path(*morceaux)).resolve()
        if self.racine not in chemin.parents and chemin != self.racine:
            raise ValueError(f"clé de stockage hors racine : {cle!r}")
        return chemin

    async def ecrire(self, cle: str, data: bytes, metadata: dict[str, Any]) -> str:
        chemin = self._chemin(cle)

        def ecrire():
            chemin.parent.mkdir(parents=True, exist_ok=True)
            temporaire = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
            temporaire.write_bytes(data)
            temporaire.replace(chemin)

        await asyncio.to_thread(ecrire)
        return chemin.relative_to(self.racine).as_posix()

    async def lire(self, identifiant: str) -> bytes:
        chemin = self._chemin(identifiant)
        try:
            return await asyncio.to_thread(chemin.read_bytes)
        except FileNotFoundError:
            raise

    async def supprimer(self, identifiant: str) -> None:
        chemin = self._chemin(identifiant)
        try:
            await asyncio.to_thread(chemin.unlink)
        except FileNotFoundError:
            pass

    async def deplacer(self, identifiants: list[str], case_id: str) -> None:
        return None

    async def vider(self) -> None:
        def vider():
            if not self.racine.exists():
                return
            for enfant in self.racine.iterdir():
                if enfant.is_dir():
                    shutil.rmtree(enfant)
                else:
                    enfant.unlink()

        await asyncio.to_thread(vider)
