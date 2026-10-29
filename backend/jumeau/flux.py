"""Réponse de Flore au fil de l'eau (exigences non fonctionnelles §8 : progression visible < 3 s).

Contrat (Server-Sent Events, une ligne `data: <json>` par événement) :
- {"type": "etape", "libelle": "Je suis l'enchaînement…"} : un outil réellement appelé, en mots simples ;
- {"type": "texte", "delta": "…"} : le brouillon qui s'écrit (encore en relecture) ;
- {"type": "relecture"} : le brouillon est fini, la relecture et les contrôles tournent ;
- {"type": "final", "reponse": {...}} : la réponse relue, contrôlée, à afficher (remplace le brouillon) ;
- {"type": "erreur", "message": "…"}.

La réponse finale porte `durees.premier_texte` : l'instant du premier mot envoyé, mesuré ici et nulle part ailleurs
(plan de remédiation L0.6 : une latence annoncée doit être une latence mesurée).
"""
import asyncio
import json
import logging
import time

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

journal = logging.getLogger("meridian.jumeau")
_TACHES = set()


SONDE_DECONNEXION = 0.25  # secondes entre deux questions « le client est-il parti ? »


class _ClientParti(Exception):
    pass


def en_flux(produire, sur_interruption=None, requete=None):
    """`produire(emit)` est une coroutine qui rend la réponse finale ; ses événements partent au fil de l'eau.
    Sans `sur_interruption`, si le client se déconnecte la réponse se termine quand même (elle peut être enregistrée).
    Avec `sur_interruption(brouillon)` (coroutine), la déconnexion ANNULE la génération puis remet au rappel ce qui
    avait été écrit (la concaténation des événements `texte`). La déconnexion est vue par la fermeture du flux ou,
    si `requete` est donnée, par `requete.is_disconnected()`."""
    file = asyncio.Queue()
    brouillon = []
    horodatage = {"debut": None, "premier_texte": None}

    async def emit(evenement):
        if evenement.get("type") == "texte":
            brouillon.append(evenement.get("delta") or "")
        if evenement.get("type") == "texte" and horodatage["premier_texte"] is None and horodatage["debut"]:
            horodatage["premier_texte"] = round(time.monotonic() - horodatage["debut"], 2)
        await file.put(evenement)

    async def tache():
        horodatage["debut"] = time.monotonic()
        try:
            reponse = await produire(emit)
            durees = reponse.get("durees") if isinstance(reponse, dict) else None
            if isinstance(durees, dict) and horodatage["premier_texte"] is not None:
                durees.setdefault("premier_texte", horodatage["premier_texte"])
            await file.put({"type": "final", "reponse": reponse})
        except HTTPException as e:
            await file.put({"type": "erreur", "message": str(e.detail)})
        except Exception:
            journal.exception("réponse au fil de l'eau")
            await file.put({"type": "erreur", "message": "Flore est momentanément injoignable."})
        finally:
            await file.put(None)

    async def interrompre(en_cours):
        """Annule la génération, attend qu'elle soit finie, puis remet le brouillon. Tâche à part : la
        déconnexion peut avoir annulé la nôtre."""
        en_cours.cancel()
        await asyncio.gather(en_cours, return_exceptions=True)
        try:
            await sur_interruption("".join(brouillon))
        except Exception:
            journal.exception("enregistrement d'une réponse interrompue")

    async def suivante():
        """Le prochain événement ; lève _ClientParti si `requete` dit que le client est parti."""
        if requete is None:
            return await file.get()
        lecture = asyncio.ensure_future(file.get())
        try:
            while True:
                fait, _ = await asyncio.wait({lecture}, timeout=SONDE_DECONNEXION)
                if fait:
                    return lecture.result()
                if await requete.is_disconnected():
                    raise _ClientParti()
        finally:
            if not lecture.done():
                lecture.cancel()

    async def evenements():
        en_cours = asyncio.create_task(tache())
        _TACHES.add(en_cours)  # référence gardée : la réponse se termine même si le client part
        en_cours.add_done_callback(_TACHES.discard)
        termine = False
        try:
            while (e := await suivante()) is not None:
                yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
            termine = True
        except _ClientParti:
            pass
        finally:
            if not termine and sur_interruption is not None and not en_cours.done():
                relais = asyncio.create_task(interrompre(en_cours))
                _TACHES.add(relais)
                relais.add_done_callback(_TACHES.discard)

    return StreamingResponse(evenements(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
