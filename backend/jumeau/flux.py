"""Réponse de Flore au fil de l'eau (exigences non fonctionnelles §8 : progression visible < 3 s).

Sur le fil : le protocole AG-UI (Server-Sent Events, traduction dans jumeau/protocole.py). `produire(emit)` émet
le vocabulaire interne de Flore :
- {"type": "etape", "libelle": "Je regarde Conduit…"} → STEP_STARTED / STEP_FINISHED ;
- {"type": "outil", "id", "nom", "libelle", "etat": "en_cours"}, puis {"id", "arguments"}, puis
  {"id", "etat": "fait"|"erreur", "duree", "extrait"} → TOOL_CALL_START / ARGS / END / RESULT ;
- {"type": "texte", "delta": "…"} : le brouillon (encore en relecture) → TEXT_MESSAGE_* ;
- {"type": "relecture"} : brouillon fini, relecture en cours → CUSTOM « relecture ».
La réponse relue, contrôlée, part dans RUN_FINISHED.result ; une erreur lisible dans RUN_ERROR.message.

La réponse finale porte `durees.premier_texte` : l'instant du premier mot envoyé, mesuré ici et nulle part ailleurs
(plan de remédiation L0.6 : une latence annoncée doit être une latence mesurée).
"""
import asyncio
import json
import logging
import time
import uuid

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from jumeau.protocole import Traducteur, encoder

journal = logging.getLogger("meridian.jumeau")
_TACHES = set()


SONDE_DECONNEXION = 0.25  # secondes entre deux questions « le client est-il parti ? »


class _ClientParti(Exception):
    pass


class Activite:
    """L'activité d'un tour, telle qu'elle a eu lieu : étapes et outils dans l'ordre, au format que l'interface
    affiche (`{label, outil?}`, comme journalActivite). Gardée avec la réponse, et avec un tour arrêté."""

    def __init__(self):
        self.ops = []

    def suivre(self, e):
        if e.get("type") == "etape":
            self.ops = [*self.ops, {"label": e.get("libelle") or ""}]
        elif e.get("type") == "outil":
            champs = {k: v for k, v in e.items() if k != "type"}
            i = next((k for k, o in enumerate(self.ops) if (o.get("outil") or {}).get("id") == e.get("id")), None)
            if i is None:
                self.ops = [*self.ops, {"label": e.get("libelle") or e.get("nom") or "", "outil": champs}]
            else:
                self.ops = [*self.ops[:i], {**self.ops[i], "outil": {**self.ops[i]["outil"], **champs}}, *self.ops[i + 1:]]


def en_flux(produire, sur_interruption=None, requete=None, fil=None):
    """`produire(emit)` est une coroutine qui rend la réponse finale ; ses événements partent au fil de l'eau.
    Sans `sur_interruption`, si le client se déconnecte la réponse se termine quand même (elle peut être enregistrée).
    Avec `sur_interruption(brouillon, activite)` (coroutine), la déconnexion ANNULE la génération puis remet au
    rappel ce qui avait été écrit (la concaténation des événements `texte`) et l'activité du tour (Activite.ops). La déconnexion est vue par la fermeture du flux ou,
    si `requete` est donnée, par `requete.is_disconnected()`. `fil` : l'identifiant AG-UI du fil (le Travail)."""
    file = asyncio.Queue()
    brouillon = []
    activite = Activite()
    horodatage = {"debut": None, "premier_texte": None}

    async def emit(evenement):
        activite.suivre(evenement)
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
            await sur_interruption("".join(brouillon), activite.ops)
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
        tour = uuid.uuid4().hex
        ag = Traducteur(fil or tour, tour)
        try:
            for ev in ag.debut():
                yield encoder(ev)
            while (e := await suivante()) is not None:
                if e["type"] == "final":
                    sortie = ag.fin(json.loads(json.dumps(e["reponse"], default=str)))  # dates en texte, comme avant
                elif e["type"] == "erreur":
                    sortie = ag.erreur(e["message"])
                else:
                    sortie = ag.traduire(e)
                for ev in sortie:
                    yield encoder(ev)
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
