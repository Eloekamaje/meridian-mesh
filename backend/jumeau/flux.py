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


def en_flux(produire):
    """`produire(emit)` est une coroutine qui rend la réponse finale ; ses événements partent au fil de l'eau.
    ponytail: si le client se déconnecte, la réponse se termine quand même (elle peut être enregistrée)."""
    file = asyncio.Queue()
    horodatage = {"debut": None, "premier_texte": None}

    async def emit(evenement):
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

    async def evenements():
        en_cours = asyncio.create_task(tache())
        _TACHES.add(en_cours)  # référence gardée : la réponse se termine même si le client part
        en_cours.add_done_callback(_TACHES.discard)
        while (e := await file.get()) is not None:
            yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(evenements(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
