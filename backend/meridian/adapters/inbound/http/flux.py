"""Réponse de Flore au fil de l'eau (exigences non fonctionnelles §8 : progression visible < 3 s).

Sur le fil : le protocole AG-UI (Server-Sent Events, traduction dans meridian/application/protocole.py). `produire(emit)` émet
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

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

from meridian.adapters.outbound.redis import evenements
from meridian.adapters.outbound.redis import partage
from meridian.adapters.outbound.redis import tours_redis as magasin
from meridian.application.protocole import Traducteur, encoder

journal = logging.getLogger("meridian.jumeau")
_TACHES = set()  # références gardées : un tour se termine même si personne ne le lit plus


SONDE_DECONNEXION = 0.25  # secondes entre deux questions « le client est-il parti ? »


# Ce que fait Flore, dit simplement, à mesure qu'elle appelle ses outils (la vraie activité, pas un défilé écrit
# d'avance). Un outil absent de la liste s'affiche sous son nom.
from meridian.application.progression import (
    EXTRAIT_OUTIL,
    LIBELLES_OUTILS,
    Activite,
    SuiviOutils,
    _extrait,
)


CONSERVATION_TOUR = 600  # secondes : un tour fini reste lisible (reprise après coupure), puis il est oublié
TOURS = {}  # identifiant AG-UI du tour (runId) → Tour en cours ou récent


class Tour:
    """Un tour de Flore, indépendant de la connexion qui l'a lancé : la génération écrit ses événements AG-UI (déjà
    traduits) dans `lignes` ; chaque lecteur les lit depuis une position. Un lecteur qui part n'arrête rien : seul
    `arreter` annule (bouton « Arrêter »), et une coupure de réseau se rattrape par une reprise."""

    def __init__(self, fil, proprietaire):
        self.id = uuid.uuid4().hex
        self.fil = fil
        self.proprietaire = proprietaire
        self.traducteur = Traducteur(fil or self.id, self.id)
        self.lignes = []
        self.lecteurs = 0  # connexions qui lisent ce tour en ce moment
        self.fin_lue = False  # au moins un lecteur a lu la fin publiée
        self.fini = False
        self.tache = None
        self._signal = asyncio.Event()

    async def publier(self, evenements):
        self.lignes.extend(encoder(e) for e in evenements)
        self._reveiller()

    async def terminer(self):
        if self.fini:
            return
        self.fini = True
        evenements.publier(self.proprietaire, "tour.fini", fil=self.fil, tour=self.id)
        self._reveiller()

    async def etat_fin(self):
        return self.lecteurs, self.fin_lue

    def _reveiller(self):
        signal, self._signal = self._signal, asyncio.Event()
        signal.set()

    async def lire(self, depuis=0, requete=None):
        """Les lignes depuis `depuis`, puis la suite en direct ; s'arrête à la fin du tour ou au départ du lecteur."""
        try:
            i = max(int(depuis), 0)
        except (TypeError, ValueError):
            i = 0  # curseur opaque d'un autre backend : on rejoue depuis le début
        self.lecteurs += 1
        try:
            while True:
                while i < len(self.lignes):
                    yield self.lignes[i]
                    i += 1
                if self.fini:
                    await asyncio.sleep(0)  # une déconnexion déjà reçue peut annuler ce lecteur ici
                    if requete is not None and await requete.is_disconnected():
                        return
                    self.fin_lue = True  # ce lecteur était là jusqu'à la fin
                    return
                signal = self._signal
                if requete is None:
                    await signal.wait()
                    continue
                try:
                    await asyncio.wait_for(signal.wait(), SONDE_DECONNEXION)
                except asyncio.TimeoutError:
                    if await requete.is_disconnected():
                        return  # le lecteur est parti ; le tour, lui, continue
        finally:
            self.lecteurs -= 1


async def _laisser_lire_la_fin(tour, delai=1.0):
    """La fin vient d'être publiée : laisse un court instant aux lecteurs encore là pour la lire (ou pour constater
    leur départ). Au-delà, on considère que personne n'écoutait."""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        lecteurs, fin_lue = await tour.etat_fin()
        if lecteurs == 0 or fin_lue:
            return
        await asyncio.sleep(0.01)


def _sse(generateur):
    return StreamingResponse(generateur, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _ligne_evenement(evenement):
    return "data: " + json.dumps(evenement, ensure_ascii=False, default=str) + "\n\n"


async def _canal_evenements(requete, acteur):
    """Un seul canal par onglet : instantané à l'ouverture, puis les changements de cette acteur.

    Avec Redis, l'abonnement précède l'instantané : un tour qui démarre pendant la lecture de `fils`
    est livré après le `pret`, jamais perdu. Le canal d'arrêt ferme les flux au shutdown."""
    if magasin.actif():
        pubsub = await partage.abonner(acteur)
        try:
            fils = await fils_en_cours(acteur)
            yield _ligne_evenement({"type": "pret", "fils": fils})
            while True:
                if await requete.is_disconnected():
                    return
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20)
                except Exception:
                    return
                if message is None:
                    yield ": ping\n\n"
                    continue
                if message.get("channel") == partage.canal_arret():
                    return
                yield "data: " + (message.get("data") or "") + "\n\n"
        finally:
            try:
                await pubsub.unsubscribe(partage.canal(acteur), partage.canal("*"), partage.canal_arret())
                await pubsub.aclose()
            except Exception:
                pass
        return

    file = evenements.BUS.abonner(acteur)
    try:
        fils = await fils_en_cours(acteur)
        yield _ligne_evenement({"type": "pret", "fils": fils})
        while True:
            if await requete.is_disconnected():
                return
            try:
                evenement = await asyncio.wait_for(file.get(), 20)
            except asyncio.TimeoutError:
                yield ": ping\n\n"  # garde la connexion vivante à travers les proxies
                continue
            if evenement.get("type") == "fermeture":
                return
            yield _ligne_evenement(evenement)
    finally:
        evenements.BUS.desabonner(acteur, file)


def en_flux(produire, sur_interruption=None, requete=None, fil=None, proprietaire=None, si_seul=None):
    """`produire(emit)` est une coroutine qui rend la réponse finale ; ses événements partent au fil de l'eau, en
    AG-UI. Le tour continue si le client se déconnecte (coupure : il se reprend par `/api/tours/{id}/flux`). Seul
    `arreter(id)` l'annule ; `sur_interruption(brouillon, activite)` reçoit alors ce qui avait été écrit (la
    concaténation des `texte`) et l'activité du tour. `fil` : le fil AG-UI (le Travail) ; `proprietaire` : le seul
    interlocuteur qui peut arrêter ou reprendre ce tour. `si_seul(reponse)` : appelé quand le tour finit sans plus
    personne pour le lire (l'interlocuteur a quitté la page : on le prévient que l'analyse est prête)."""
    tour = magasin.TourRedis(fil, proprietaire) if magasin.actif() else Tour(fil, proprietaire)
    tour.traducteur = Traducteur(fil or tour.id, tour.id)
    TOURS[tour.id] = tour
    tour.sur_interruption = sur_interruption
    tour.brouillon = []
    tour.activite = Activite()
    horodatage = {"debut": None, "premier_texte": None}

    async def emit(evenement):
        tour.activite.suivre(evenement)
        if evenement.get("type") == "texte":
            tour.brouillon.append(evenement.get("delta") or "")
            if horodatage["premier_texte"] is None and horodatage["debut"]:
                horodatage["premier_texte"] = round(time.monotonic() - horodatage["debut"], 2)
        await tour.publier(tour.traducteur.traduire(evenement))

    async def tache():
        horodatage["debut"] = time.monotonic()
        await tour.publier(tour.traducteur.debut())
        try:
            reponse = await produire(emit)
            durees = reponse.get("durees") if isinstance(reponse, dict) else None
            if isinstance(durees, dict) and horodatage["premier_texte"] is not None:
                durees.setdefault("premier_texte", horodatage["premier_texte"])
            await tour.publier(tour.traducteur.fin(json.loads(json.dumps(reponse, default=str))))  # dates en texte
            await tour.terminer()  # les lecteurs présents peuvent maintenant lire la fin et sortir
            if si_seul is not None:
                await _laisser_lire_la_fin(tour)
                _, fin_lue = await tour.etat_fin()
                if not fin_lue:  # personne n'a lu la fin : l'interlocuteur a quitté la page
                    try:
                        await si_seul(reponse)
                    except Exception:
                        journal.exception("prévenir de la fin d'un tour")
        except asyncio.CancelledError:
            raise  # arrêt demandé : `arreter` finit le tour
        except HTTPException as e:
            await tour.publier(tour.traducteur.erreur(str(e.detail)))
        except Exception:
            journal.exception("réponse au fil de l'eau")
            await tour.publier(tour.traducteur.erreur("Flore est momentanément injoignable."))
        await tour.terminer()
        asyncio.get_running_loop().call_later(CONSERVATION_TOUR, TOURS.pop, tour.id, None)

    tour._lancer = tache
    return _sse(_premiere_lecture(tour, requete))


async def _premiere_lecture(tour, requete):
    """Le tour démarre avec la première lecture (une boucle d'événements tourne alors) ; il est gardé dans _TACHES :
    il se termine même si ce lecteur part. L'état Redis est créé avant de publier le démarrage."""
    if hasattr(tour, "creer"):
        try:
            await tour.creer()
        except BaseException:
            TOURS.pop(tour.id, None)
            if hasattr(tour, "abandonner"):
                try:
                    await tour.abandonner()
                except Exception:
                    pass
            raise
    evenements.publier(tour.proprietaire, "tour.demarre", fil=tour.fil, tour=tour.id)
    tour.tache = asyncio.create_task(tour._lancer())
    _TACHES.add(tour.tache)
    tour.tache.add_done_callback(_TACHES.discard)
    async for ligne in tour.lire(0, requete):
        yield ligne


async def arreter(tour_id, acteur):
    """Bouton « Arrêter » : annule la génération, enregistre ce qui avait été écrit (sur_interruption), puis finit
    le tour (RUN_FINISHED, issue « cancelled »). Rend False si le tour est inconnu, d'un autre ou déjà fini."""
    tour = TOURS.get(tour_id)
    if tour is None or tour.proprietaire != acteur or tour.fini:
        return False
    if tour.tache is not None:
        tour.tache.cancel()
        await asyncio.gather(tour.tache, return_exceptions=True)
    if tour.fini:  # fini juste avant l'arrêt : rien à enregistrer
        return True
    if tour.sur_interruption is not None:
        try:
            await tour.sur_interruption("".join(tour.brouillon), tour.activite.ops)
        except Exception:
            journal.exception("enregistrement d'une réponse interrompue")
    await tour.publier(tour.traducteur.arret())
    await tour.terminer()
    asyncio.get_running_loop().call_later(CONSERVATION_TOUR, TOURS.pop, tour.id, None)
    return True


async def fils_en_cours(proprietaire):
    """Les fils (Travaux) dont un tour de Flore tourne encore pour cet interlocuteur. Un tour fini reste
    consultable `CONSERVATION_TOUR` secondes, mais ne compte plus comme « en cours »."""
    if magasin.actif():
        return await magasin.actifs(proprietaire)
    return sorted({t.fil for t in TOURS.values()
                   if t.fil and not t.fini and t.proprietaire == proprietaire})


_CONTROLE = None


async def demarrer_controle():
    """Avec Redis, chaque worker écoute les demandes d'arrêt ; seul le propriétaire de la tâche agit."""
    global _CONTROLE
    if not magasin.actif() or _CONTROLE is not None:
        return

    async def arreter_distant(tid, acteur):
        tour = TOURS.get(tid)
        if tour is not None and tour.proprietaire == acteur:
            await arreter(tid, acteur)

    async def veiller():
        while True:
            try:
                await magasin.ecouter_controle(arreter_distant)
            except asyncio.CancelledError:
                raise
            except Exception:
                journal.exception("écoute des arrêts Redis")
                await asyncio.sleep(2)

    _CONTROLE = asyncio.create_task(veiller())


async def arreter_controle():
    global _CONTROLE
    if _CONTROLE is not None:
        _CONTROLE.cancel()
        await asyncio.gather(_CONTROLE, return_exceptions=True)
        _CONTROLE = None


def fermer_lecteurs():
    """Ferme les SSE mémoire locaux au shutdown ; les lecteurs Redis écoutent le canal d'arrêt."""
    for tour in list(TOURS.values()):
        if isinstance(tour, Tour):
            tour.fini = True
            tour._reveiller()


def ajouter_routes_tours(router):
    """Arrêter, reprendre et suivre un tour : réservé à son interlocuteur (sinon 404, sans dire qu'il existe)."""
    from fastapi import Request

    from auth import acteur as acteur_courant

    @router.get("/evenements")
    async def canal_evenements(request: Request, acteur: str = Depends(acteur_courant)):
        return _sse(_canal_evenements(request, acteur))

    @router.get("/tours/en-cours")
    async def tours_en_cours(acteur: str = Depends(acteur_courant)):
        return {"fils": await fils_en_cours(acteur)}

    @router.post("/tours/{tid}/arreter")
    async def arreter_tour(tid: str, acteur: str = Depends(acteur_courant)):
        tour = TOURS.get(tid)
        if tour is not None and tour.proprietaire == acteur:
            return {"arrete": await arreter(tid, acteur)}
        if magasin.actif():
            m = await magasin.meta(tid)
            if m and m.get("proprietaire") == acteur:
                if m.get("fini") == "1":
                    return {"arrete": False}
                await magasin.demander_arret(tid, acteur)
                for _ in range(20):
                    courant = await magasin.meta(tid)
                    if not courant or courant.get("fini") == "1":
                        return {"arrete": True}
                    await asyncio.sleep(0.1)
                return {"arrete": False, "accepte": True}
        raise HTTPException(404, "Tour introuvable")

    @router.get("/tours/{tid}/flux")
    async def reprendre_tour(tid: str, request: Request, depuis: str = "0", acteur: str = Depends(acteur_courant)):
        tour = TOURS.get(tid)
        if tour is not None and tour.proprietaire == acteur:
            return _sse(tour.lire(depuis, request))
        if magasin.actif():
            m = await magasin.meta(tid)
            if m and m.get("proprietaire") == acteur:
                return _sse(magasin.lire(tid, depuis, request))
        raise HTTPException(404, "Tour introuvable")
