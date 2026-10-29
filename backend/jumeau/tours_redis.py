"""État partagé des tours dans Redis : flux AG-UI, métadonnées, heartbeat et arrêt coopératif.

Le registre `TOURS` local ne contient que les tours dont ce worker possède la tâche. Les autres workers
lisent le flux Redis et peuvent demander l'arrêt par le canal de contrôle. Chaque flux porte un `id:`
Redis Stream : la reprise utilise donc un curseur opaque, stable et rejouable.
"""
import asyncio
import json
import os
import socket
import uuid

from redis.exceptions import ResponseError

from jumeau import evenements, partage
from jumeau.protocole import encoder

SONDE = 0.25  # secondes entre deux vérifications de déconnexion quand aucune ligne n'arrive
WORKER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

_LOCAUX = set()
_BATTEMENT = None
_REAPER = None


def actif():
    return partage.actif()


def _ttl():
    return int(os.getenv("TOUR_TTL", "600"))


def _battement():
    return float(os.getenv("TOUR_HEARTBEAT", "5"))


def _stale():
    return float(os.getenv("TOUR_STALE", "30"))


def _reaper_delai():
    return float(os.getenv("TOUR_REAPER", "10"))


def _cle(tid, suffixe):
    return f"{partage.prefixe()}tour:{tid}:{suffixe}"


def _encours(persona):
    return f"{partage.prefixe()}encours:{persona}"


def _actifs():
    return f"{partage.prefixe()}tours:actifs"


def _reveil(tid):
    return _cle(tid, "reveil")


def _meta(tid):
    return _cle(tid, "meta")


def _lignes(tid):
    return _cle(tid, "lignes")


async def _maintenant(r):
    secondes, microsecondes = await r.time()
    return float(secondes) + float(microsecondes) / 1e6


def _ligne_erreur():
    return "data: " + json.dumps(
        {"type": "RUN_ERROR", "message": "Flore a été interrompue : le worker qui produisait cette réponse ne répond plus."},
        ensure_ascii=False,
    ) + "\n\n"


class TourRedis:
    """Même surface que `flux.Tour`, mais le flux et l'état vivent dans Redis."""

    def __init__(self, fil, proprietaire):
        self.id = uuid.uuid4().hex
        self.fil = fil
        self.proprietaire = proprietaire
        self.fini = False
        self.tache = None
        self.sur_interruption = None
        self.brouillon = []
        self.activite = None
        self.traducteur = None

    async def creer(self):
        _LOCAUX.add(self.id)
        r = await partage.client()
        now = await _maintenant(r)
        pipe = r.pipeline()
        pipe.hset(_meta(self.id), mapping={
            "fil": self.fil or "",
            "proprietaire": self.proprietaire or "",
            "worker": WORKER,
            "heartbeat": now,
            "fini": 0,
            "fin_lue": 0,
            "lecteurs": 0,
            "cree": now,
        })
        pipe.expire(_meta(self.id), _ttl())
        if self.proprietaire:
            pipe.sadd(_encours(self.proprietaire), self.id)
        pipe.sadd(_actifs(), self.id)
        await pipe.execute()

    async def publier(self, evenements):
        lignes = [encoder(e) for e in evenements if e]
        if not lignes or self.fini:
            return
        r = await partage.client()
        if await r.hget(_meta(self.id), "fini") == "1":
            self.fini = True
            _LOCAUX.discard(self.id)
            return
        maintenant = await _maintenant(r)
        pipe = r.pipeline()
        for ligne in lignes:
            pipe.xadd(_lignes(self.id), {"data": ligne})
        pipe.expire(_lignes(self.id), _ttl())
        pipe.expire(_meta(self.id), _ttl())
        pipe.hset(_meta(self.id), mapping={"heartbeat": maintenant, "worker": WORKER})
        pipe.publish(_reveil(self.id), "1")
        await pipe.execute()

    async def terminer(self):
        if self.fini:
            return
        self.fini = True
        _LOCAUX.discard(self.id)
        r = await partage.client()
        meta = await r.hgetall(_meta(self.id))
        if not meta:
            return
        if meta.get("erreur") == "1":  # déjà ramassé par le reaper : pas de second tour.fini
            self.fini = True
            return
        pipe = r.pipeline()
        pipe.hset(_meta(self.id), mapping={"fini": 1, "heartbeat": await _maintenant(r)})
        pipe.expire(_meta(self.id), _ttl())
        if meta.get("proprietaire"):
            pipe.srem(_encours(meta["proprietaire"]), self.id)
        pipe.srem(_actifs(), self.id)
        pipe.publish(_reveil(self.id), "1")
        await pipe.execute()
        evenements.publier(self.proprietaire, "tour.fini", fil=self.fil, tour=self.id)

    async def abandonner(self):
        _LOCAUX.discard(self.id)
        r = await partage.client()
        pipe = r.pipeline()
        pipe.delete(_meta(self.id))
        pipe.delete(_lignes(self.id))
        pipe.srem(_actifs(), self.id)
        if self.proprietaire:
            pipe.srem(_encours(self.proprietaire), self.id)
        await pipe.execute()

    async def etat_fin(self):
        return await etat_fin(self.id)

    async def lire(self, depuis=0, requete=None):
        async for ligne in lire(self.id, depuis, requete):
            yield ligne


async def etat_fin(tid):
    r = await partage.client()
    meta = await r.hgetall(_meta(tid))
    if not meta:
        return 0, False
    return int(meta.get("lecteurs", 0) or 0), meta.get("fin_lue") == "1"


def _depuis_stream(depuis):
    """Un `depuis` numérique est l'ancien curseur (nombre d'événements) : on rejoue depuis le début."""
    valeur = str(depuis or "0")
    if valeur.isdigit():
        return "0-0"
    return valeur


def _min_id(dernier):
    return "-" if dernier in ("", "0", "0-0") else f"({dernier}"


async def _entrees(r, tid, dernier):
    return await r.xrange(_lignes(tid), min=_min_id(dernier), max="+")


async def lire(tid, depuis=0, requete=None):
    """Lit le flux Redis depuis un ID opaque ; le TTL supprime le flux entier, jamais un préfixe."""
    r = await partage.client()
    meta_key = _meta(tid)
    if not await r.exists(meta_key):
        return
    pubsub = r.pubsub()
    await pubsub.subscribe(_reveil(tid), partage.canal_arret())
    dernier = _depuis_stream(depuis)
    await r.hincrby(meta_key, "lecteurs", 1)
    try:
        while True:
            try:
                entrees = await _entrees(r, tid, dernier)
            except ResponseError:  # curseur illisible : on rejoue depuis le début plutôt que de casser le flux
                dernier = "0-0"
                continue
            for entree_id, champs in entrees:
                dernier = entree_id
                yield f"id: {entree_id}\n{champs.get('data', '')}"
            meta = await r.hgetall(meta_key)
            if not meta:
                return
            if meta.get("fini") == "1":
                # Le terminal a pu être ajouté entre le XRANGE et la lecture de `fini` : on draine avant de sortir.
                for entree_id, champs in await _entrees(r, tid, dernier):
                    dernier = entree_id
                    yield f"id: {entree_id}\n{champs.get('data', '')}"
                if requete is not None and await requete.is_disconnected():
                    return
                await r.hset(meta_key, "fin_lue", 1)
                return
            if requete is not None and await requete.is_disconnected():
                return
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=SONDE)
            except Exception:
                return
            if message is not None:
                if message.get("channel") == partage.canal_arret():
                    return
                continue
    finally:
        try:
            if await r.exists(meta_key):
                await r.hincrby(meta_key, "lecteurs", -1)
        except Exception:
            pass
        try:
            await pubsub.unsubscribe(_reveil(tid), partage.canal_arret())
            await pubsub.aclose()
        except Exception:
            pass


async def meta(tid):
    r = await partage.client()
    return await r.hgetall(_meta(tid))


async def actifs(persona):
    """Les fils avec au moins un tour non fini pour cette persona, vus par n'importe quel worker."""
    if not persona:
        return []
    r = await partage.client()
    identifiants = await r.smembers(_encours(persona))
    fils = set()
    for tid in identifiants:
        m = await r.hgetall(_meta(tid))
        if not m or m.get("fini") == "1":
            await r.srem(_encours(persona), tid)
            continue
        if m.get("fil"):
            fils.add(m["fil"])
    return sorted(fils)


async def reaper():
    """Marque comme terminé un tour dont le worker propriétaire ne donne plus signe de vie."""
    r = await partage.client()
    maintenant = await _maintenant(r)
    for tid in await r.smembers(_actifs()):
        meta = await r.hgetall(_meta(tid))
        if not meta:
            await r.srem(_actifs(), tid)
            continue
        if meta.get("fini") == "1":
            await r.srem(_actifs(), tid)
            if meta.get("proprietaire"):
                await r.srem(_encours(meta["proprietaire"]), tid)
            continue
        try:
            heartbeat = float(meta.get("heartbeat") or meta.get("cree") or 0)
        except ValueError:
            heartbeat = 0
        if maintenant - heartbeat <= _stale():
            continue
        verrou = _cle(tid, "reap")
        if not await r.set(verrou, "1", nx=True, ex=10):
            continue
        meta = await r.hgetall(_meta(tid))
        if not meta or meta.get("fini") == "1":
            continue
        try:
            heartbeat = float(meta.get("heartbeat") or meta.get("cree") or 0)
        except ValueError:
            heartbeat = 0
        if await _maintenant(r) - heartbeat <= _stale():
            continue
        pipe = r.pipeline()
        pipe.xadd(_lignes(tid), {"data": _ligne_erreur()})
        pipe.hset(_meta(tid), mapping={"fini": 1, "erreur": 1, "fin_lue": 1})
        pipe.expire(_meta(tid), _ttl())
        pipe.expire(_lignes(tid), _ttl())
        if meta.get("proprietaire"):
            pipe.srem(_encours(meta["proprietaire"]), tid)
        pipe.srem(_actifs(), tid)
        pipe.publish(_reveil(tid), "1")
        await pipe.execute()
        evenements.publier(meta.get("proprietaire"), "tour.fini", fil=meta.get("fil"), tour=tid)


async def _battre():
    while True:
        await asyncio.sleep(_battement())
        if not _LOCAUX:
            continue
        try:
            r = await partage.client()
            maintenant = await _maintenant(r)
            for tid in list(_LOCAUX):
                if not await r.exists(_meta(tid)):
                    _LOCAUX.discard(tid)
                    continue
                await r.hset(_meta(tid), mapping={"heartbeat": maintenant, "worker": WORKER})
                await r.expire(_meta(tid), _ttl())
        except Exception:
            continue


async def _reaper_loop():
    while True:
        await asyncio.sleep(_reaper_delai())
        try:
            await reaper()
        except Exception:
            continue


async def demarrer_taches():
    global _BATTEMENT, _REAPER
    if not actif():
        return
    if _BATTEMENT is None:
        _BATTEMENT = asyncio.create_task(_battre())
    if _REAPER is None:
        _REAPER = asyncio.create_task(_reaper_loop())


async def arreter_taches():
    global _BATTEMENT, _REAPER
    for tache in (_BATTEMENT, _REAPER):
        if tache is not None:
            tache.cancel()
            await asyncio.gather(tache, return_exceptions=True)
    _BATTEMENT = _REAPER = None


async def demander_arret(tid, persona):
    r = await partage.client()
    await r.publish(partage.canal_controle(), json.dumps({"tour": tid, "persona": persona}))


async def ecouter_controle(callback):
    """Chaque worker écoute le canal : seul celui qui possède la tâche annule réellement."""
    r = await partage.client()
    pubsub = r.pubsub()
    await pubsub.subscribe(partage.canal_controle())
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message.get("data") or "{}")
                await callback(data.get("tour"), data.get("persona"))
            except Exception:
                continue
    finally:
        try:
            await pubsub.unsubscribe(partage.canal_controle())
            await pubsub.aclose()
        except Exception:
            pass
