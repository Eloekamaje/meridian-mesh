"""Runtime local des naissances : tâche asyncio, notifications et journal restent dans l'adapter.

La naissance réelle vit dans :mod:`meridian.adapters.outbound.connectors.naissance`; ce runtime ne fait que
borner les exécutions simultanées et refléter leur issue sur la commande. Les références de tâches et
l'ensemble des naissances en cours sont propres au processus, comme avant l'extraction.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

import psycopg

from meridian.adapters.outbound.connectors import naissance as module_naissance
from meridian.application import commandes as commandes_app
from meridian.ports.commandes import CommandesStore

journal = logging.getLogger("meridian")

TACHES_NAISSANCE = set()  # références fortes : une tâche asyncio sans référence peut être collectée en cours de route
NAISSANCES_EN_COURS = set()  # un seul lancement par jumeau, même si deux demandes arrivent en même temps
NAISSANCES_SIMULTANEES = asyncio.Semaphore(2)
DUREE_MAX_NAISSANCE = 30 * 60  # secondes

Notifier = Callable[[str, str, str], Awaitable[None]]
Journaler = Callable[[str, str, str, str, str], Awaitable[None]]


class NaissanceRuntimeLocal:
    def __init__(
        self,
        db,
        store: CommandesStore,
        *,
        notifier: Notifier,
        journaler: Journaler,
        dsn: str | None = None,
        duree_max: int | None = None,
    ):
        self.db = db
        self.store = store
        self._notifier = notifier
        self._journaler = journaler
        self._dsn = dsn
        self._duree_max = duree_max or DUREE_MAX_NAISSANCE

    def disponible(self) -> bool:
        return bool(self._dsn or os.environ.get("JUMEAU_PG_DSN"))

    def en_cours(self, jid: str) -> bool:
        return jid in NAISSANCES_EN_COURS

    async def demarrer(
        self, commande: dict[str, Any], jid: str, *, acteur: str, espace_id: str
    ) -> None:
        pretes = [s for s in commande.get("sources", []) if s.get("statut") == "prete"]
        nom = (commande.get("jumeau") or {}).get("nom") or jid
        await self._journaler(
            acteur, espace_id, "lancement d'une commande", jid,
            f"{nom} — {len(pretes)} source(s) prête(s)",
        )
        NAISSANCES_EN_COURS.add(jid)
        t = asyncio.create_task(self._naitre(commande, jid))
        TACHES_NAISSANCE.add(t)
        t.add_done_callback(TACHES_NAISSANCE.discard)
        t.add_done_callback(lambda _: NAISSANCES_EN_COURS.discard(jid))

    async def notifier(self, jid: str, texte: str) -> None:
        await self._notifier("naissance", texte, f"/jumeaux/{jid}/revue")

    async def _naitre(self, commande: dict[str, Any], jid: str) -> None:
        """ponytail: tâche dans le processus de l'API, bornée en nombre et en durée ; Step Functions sur AWS."""
        try:
            async with NAISSANCES_SIMULTANEES:
                with psycopg.connect(self._dsn or os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
                    await asyncio.wait_for(
                        module_naissance.naitre(conn, self.db, commande, jid), self._duree_max
                    )
            etat = await self.store.lire(commande["id"])
            naissance = (etat or {}).get("naissance") or {}
            if naissance.get("etat") == "echec":
                await commandes_app.echec_naissance(
                    self.store, self, commande, jid,
                    naissance.get("message") or "erreur pendant la naissance",
                )
            elif naissance.get("etat") == "sans_substance":
                await commandes_app.notifier_naissance(
                    self, jid,
                    f"Le jumeau {commande.get('jumeau', {}).get('nom') or jid} est créé, mais sa naissance est "
                    f"incomplète : {naissance.get('message') or 'source de substance manquante'}.",
                )
        except asyncio.TimeoutError:
            await commandes_app.echec_naissance(self.store, self, commande, jid, "durée dépassée")
        except Exception:  # noqa: BLE001 - la commande doit refléter un échec, jamais rester « en cours »
            journal.exception("naissance de %s", jid)
            await commandes_app.echec_naissance(
                self.store, self, commande, jid, "erreur pendant la naissance"
            )
