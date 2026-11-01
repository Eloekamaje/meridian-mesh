"""Bus d'événements par acteur pour le canal SSE global de l'application.

Sans Redis, le bus vit dans le processus (un worker, tests, développement). Avec `REDIS_URL`, chaque événement
est aussi publié sur le canal de l'acteur, ou sur le canal global « * » ; les flux SSE de tous les workers le reçoivent.
"""
import asyncio
from collections import defaultdict

from jumeau import partage


class Bus:
    """Files d'abonnés par acteur. Un client lent perd ses plus anciens événements, jamais les plus récents."""

    def __init__(self, taille=256):
        self.taille = taille
        self._files = defaultdict(set)

    def abonner(self, acteur):
        file = asyncio.Queue(maxsize=self.taille)
        self._files[acteur].add(file)
        return file

    def desabonner(self, acteur, file):
        files = self._files.get(acteur)
        if files is None:
            return
        files.discard(file)
        if not files:
            self._files.pop(acteur, None)

    def publier(self, acteur, evenement):
        if not acteur:
            return
        if acteur == "*":  # notification tenant-wide : tous les flux abonnés
            files = {file for files in self._files.values() for file in files}
        else:
            files = set(self._files.get(acteur, ()))
        for file in files:
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


def publier(acteur, type_, **champs):
    """Publie un événement nommé pour un acteur, ou pour tous avec « * »."""
    evenement = {"type": type_, **champs}
    BUS.publier(acteur, evenement)
    if partage.actif():
        _planifier(partage.publier(acteur, evenement))


def fermer():
    BUS.fermer()
    if partage.actif():
        _planifier(partage.publier_arret())
