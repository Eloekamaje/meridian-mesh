"""Bus d'événements par persona pour le canal SSE global de l'application.

Sans Redis, le bus vit dans le processus (un worker, tests, développement). Avec `REDIS_URL`, chaque événement
est aussi publié sur le canal de la persona ; les flux SSE de tous les workers le reçoivent.
"""
import asyncio
from collections import defaultdict

from jumeau import partage


class Bus:
    """Files d'abonnés par persona. Un client lent perd ses plus anciens événements, jamais les plus récents."""

    def __init__(self, taille=256):
        self.taille = taille
        self._files = defaultdict(set)

    def abonner(self, persona):
        file = asyncio.Queue(maxsize=self.taille)
        self._files[persona].add(file)
        return file

    def desabonner(self, persona, file):
        files = self._files.get(persona)
        if files is None:
            return
        files.discard(file)
        if not files:
            self._files.pop(persona, None)

    def publier(self, persona, evenement):
        if not persona:
            return
        for file in list(self._files.get(persona, ())):
            self._offrir(file, evenement)

    def _offrir(self, file, evenement):
        if file.full():
            try:
                file.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            file.put_nowait(evenement)
        except asyncio.QueueFull:
            pass

    def fermer(self):
        """Ferme les flux SSE à l'arrêt du serveur : sinon uvicorn attend indéfiniment leurs connexions."""
        for files in list(self._files.values()):
            for file in list(files):
                self._offrir(file, {"type": "fermeture"})
        self._files.clear()


BUS = Bus()
_TACHES = set()


def _planifier(coro):
    try:
        tache = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        return
    _TACHES.add(tache)

    def oublier(t):
        _TACHES.discard(t)
        try:
            t.exception()
        except Exception:
            pass

    tache.add_done_callback(oublier)


def publier(persona, type_, **champs):
    """Publie un événement nommé pour une persona ; sans persona, personne n'est concerné."""
    evenement = {"type": type_, **champs}
    BUS.publier(persona, evenement)
    if partage.actif():
        _planifier(partage.publier(persona, evenement))


def fermer():
    BUS.fermer()
    if partage.actif():
        _planifier(partage.publier_arret())
