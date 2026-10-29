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
_TACHES = set()  # références gardées : un tour se termine même si personne ne le lit plus


SONDE_DECONNEXION = 0.25  # secondes entre deux questions « le client est-il parti ? »


# Ce que fait Flore, dit simplement, à mesure qu'elle appelle ses outils (la vraie activité, pas un défilé écrit
# d'avance). Un outil absent de la liste s'affiche sous son nom.
LIBELLES_OUTILS = {
    "mes_connaissances": "Je consulte ce que l'on sait de l'application…",
    "architecture": "Je regarde de quoi l'application est faite…",
    "chercher_texte": "Je cherche dans le code…", "chercher_symbole": "Je cherche dans le code…",
    "tracer_appels": "Je regarde qui appelle quoi…",
    "suivre_appels": "Je suis l'enchaînement dans le code…",
    "lire_code": "Je lis le code concerné…",
    "historique_du_code": "Je regarde l'histoire du code…", "ce_qui_a_change": "Je regarde ce qui a changé…",
    "chercher_dans": "Je cherche dans la documentation et les outils de l'équipe…",
    "lire_dans": "Je lis la documentation concernée…",
    "dessiner_schema": "Je dessine le schéma…",
    "consulter_jumeau": "Je consulte l'application concernée…",
    "montrer_sur_atlas": "Je prépare la carte…",
    "consulter_methode": "Je choisis comment m'y prendre…",
    "proposer_connaissance": "Je consigne ce que j'ai appris…",
    "eprouver_hypothese": "Je mets une hypothèse à l'épreuve…", "proposer_hypothese": "Je pose une hypothèse à vérifier…", "recouper_connaissance": "Je recoupe avec une autre source…",
}

EXTRAIT_OUTIL = 300  # caractères du résultat d'un outil montrés à l'écran (le reste est dans la réponse, cité)


def _extrait(resultat):
    """Le début du résultat d'un outil, en texte : une donnée lue, affichée comme telle, jamais une instruction."""
    texte = " ".join(b["text"] for b in resultat.get("content") or [] if isinstance(b, dict) and isinstance(b.get("text"), str))
    return texte if len(texte) <= EXTRAIT_OUTIL else texte[:EXTRAIT_OUTIL] + "…"


class SuiviOutils:
    """Le flux Strands d'un agent → les événements `outil` (début, arguments complets, issue, durée d'exécution).
    `parent` : le jumeau dont le sous-agent fait la mission (ses outils s'affichent sous sa consultation) ;
    `ignorer` : des outils internes (sortie structurée) qu'on ne montre pas."""

    def __init__(self, emit, parent=None, ignorer=()):
        self.emit, self.parent, self.ignorer, self.debuts = emit, parent, set(ignorer), {}

    async def suivre(self, e):
        """Rend True si l'événement concernait un outil (annoncé, exécuté ou fini)."""
        if (outil := e.get("current_tool_use")) and (oid := outil.get("toolUseId")):
            if oid not in self.debuts and outil.get("name") not in self.ignorer:
                self.debuts[oid] = time.monotonic()  # Strands répète l'appel pendant que ses arguments arrivent
                await self.emit({"type": "outil", "id": oid, "nom": outil.get("name"),
                                 "libelle": LIBELLES_OUTILS.get(outil.get("name")), "etat": "en_cours",
                                 **({"parent": self.parent} if self.parent else {})})
            return True
        if not isinstance(m := e.get("message"), dict):
            return False
        for bloc in m.get("content") or []:
            if (u := bloc.get("toolUse")) and u.get("toolUseId") in self.debuts:
                self.debuts[u["toolUseId"]] = time.monotonic()  # arguments complets : l'outil s'exécute maintenant
                await self.emit({"type": "outil", "id": u["toolUseId"], "arguments": u.get("input")})
            elif (r := bloc.get("toolResult")) and (oid := r.get("toolUseId")) in self.debuts:
                await self.emit({"type": "outil", "id": oid, "etat": "erreur" if r.get("status") == "error" else "fait",
                                 "duree": round(time.monotonic() - self.debuts[oid], 2), "extrait": _extrait(r)})
        return True


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
        elif e.get("type") == "mission":  # la fin de la mission d'un jumeau : sur sa (dernière) consultation
            i = next((k for k in range(len(self.ops) - 1, -1, -1) if (o := self.ops[k].get("outil") or {}).get("nom")
                      == "consulter_jumeau" and (o.get("arguments") or {}).get("jumeau") == e.get("jumeau")), None)
            if i is not None:
                bilan = {k: e.get(k) for k in ("etat", "confiance", "preuves", "constat")}
                self.ops = [*self.ops[:i], {**self.ops[i], "outil": {**self.ops[i]["outil"], "mission": bilan}},
                            *self.ops[i + 1:]]


CONSERVATION_TOUR = 600  # secondes : un tour fini reste lisible (reprise après coupure), puis il est oublié
TOURS = {}  # identifiant AG-UI du tour (runId) → Tour en cours ou récent


class Tour:
    """Un tour de Flore, indépendant de la connexion qui l'a lancé : la génération écrit ses événements AG-UI (déjà
    traduits) dans `lignes` ; chaque lecteur les lit depuis une position. Un lecteur qui part n'arrête rien : seul
    `arreter` annule (bouton « Arrêter »), et une coupure de réseau se rattrape par une reprise."""

    def __init__(self, fil, proprietaire):
        self.id = uuid.uuid4().hex
        self.proprietaire = proprietaire
        self.traducteur = Traducteur(fil or self.id, self.id)
        self.lignes = []
        self.fini = False
        self.tache = None
        self._signal = asyncio.Event()

    def publier(self, evenements):
        self.lignes.extend(encoder(e) for e in evenements)
        self._reveiller()

    def terminer(self):
        self.fini = True
        self._reveiller()
        asyncio.get_running_loop().call_later(CONSERVATION_TOUR, TOURS.pop, self.id, None)

    def _reveiller(self):
        signal, self._signal = self._signal, asyncio.Event()
        signal.set()

    async def lire(self, depuis=0, requete=None):
        """Les lignes depuis `depuis`, puis la suite en direct ; s'arrête à la fin du tour ou au départ du lecteur."""
        i = max(depuis, 0)
        while True:
            while i < len(self.lignes):
                yield self.lignes[i]
                i += 1
            if self.fini:
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


def _sse(generateur):
    return StreamingResponse(generateur, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def en_flux(produire, sur_interruption=None, requete=None, fil=None, proprietaire=None):
    """`produire(emit)` est une coroutine qui rend la réponse finale ; ses événements partent au fil de l'eau, en
    AG-UI. Le tour continue si le client se déconnecte (coupure : il se reprend par `/api/tours/{id}/flux`). Seul
    `arreter(id)` l'annule ; `sur_interruption(brouillon, activite)` reçoit alors ce qui avait été écrit (la
    concaténation des `texte`) et l'activité du tour. `fil` : le fil AG-UI (le Travail) ; `proprietaire` : le seul
    interlocuteur qui peut arrêter ou reprendre ce tour."""
    tour = Tour(fil, proprietaire)
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
        tour.publier(tour.traducteur.traduire(evenement))

    async def tache():
        horodatage["debut"] = time.monotonic()
        tour.publier(tour.traducteur.debut())
        try:
            reponse = await produire(emit)
            durees = reponse.get("durees") if isinstance(reponse, dict) else None
            if isinstance(durees, dict) and horodatage["premier_texte"] is not None:
                durees.setdefault("premier_texte", horodatage["premier_texte"])
            tour.publier(tour.traducteur.fin(json.loads(json.dumps(reponse, default=str))))  # dates en texte
        except asyncio.CancelledError:
            raise  # arrêt demandé : `arreter` finit le tour
        except HTTPException as e:
            tour.publier(tour.traducteur.erreur(str(e.detail)))
        except Exception:
            journal.exception("réponse au fil de l'eau")
            tour.publier(tour.traducteur.erreur("Flore est momentanément injoignable."))
        tour.terminer()

    tour._lancer = tache
    return _sse(_premiere_lecture(tour, requete))


async def _premiere_lecture(tour, requete):
    """Le tour démarre avec la première lecture (une boucle d'événements tourne alors) ; il est gardé dans _TACHES :
    il se termine même si ce lecteur part."""
    tour.tache = asyncio.create_task(tour._lancer())
    _TACHES.add(tour.tache)
    tour.tache.add_done_callback(_TACHES.discard)
    async for ligne in tour.lire(0, requete):
        yield ligne


async def arreter(tour_id, persona):
    """Bouton « Arrêter » : annule la génération, enregistre ce qui avait été écrit (sur_interruption), puis finit
    le tour (RUN_FINISHED, issue « cancelled »). Rend False si le tour est inconnu, d'un autre ou déjà fini."""
    tour = TOURS.get(tour_id)
    if tour is None or tour.proprietaire != persona or tour.fini:
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
    tour.publier(tour.traducteur.arret())
    tour.terminer()
    return True


def ajouter_routes_tours(router, header):
    """Arrêter et reprendre un tour : réservé à son interlocuteur (sinon 404, sans dire qu'il existe)."""
    from fastapi import Request

    @router.post("/tours/{tid}/arreter")
    async def arreter_tour(tid: str, x_persona: str = header("architecte")):
        if TOURS.get(tid) is None or TOURS[tid].proprietaire != x_persona:
            raise HTTPException(404, "Tour introuvable")
        return {"arrete": await arreter(tid, x_persona)}

    @router.get("/tours/{tid}/flux")
    async def reprendre_tour(tid: str, request: Request, depuis: int = 0, x_persona: str = header("architecte")):
        tour = TOURS.get(tid)
        if tour is None or tour.proprietaire != x_persona:
            raise HTTPException(404, "Tour introuvable")
        return _sse(tour.lire(depuis, request))
