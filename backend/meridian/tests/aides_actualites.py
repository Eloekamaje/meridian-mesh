"""Faux minimal pour la route Actualités : seules les collections lues sont simulées."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

NO_ID = {"_id": 0}


class CurseurFaux:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], list):
            champs = args[0]
        elif len(args) == 2:
            champs = [(args[0], args[1])]
        else:
            champs = []
        for champ, sens in reversed(champs):
            self.documents.sort(key=lambda d: d.get(champ) or "", reverse=sens < 0)
        return self

    def limit(self, nombre):
        self.documents = self.documents[:int(nombre)]
        return self

    def __aiter__(self):
        self._iter = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, nombre=None):
        return list(self.documents[:int(nombre)]) if nombre else list(self.documents)


class CollectionFaux:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    def find(self, filtre=None, projection=None):
        return CurseurFaux(self.documents)


class CollectionInterdite:
    def __getattr__(self, nom):
        raise AssertionError(
            "la route Aujourd'hui doit lire les travaux via TravailStore, pas db.cases")


class DbFaux:
    def __init__(self, jumeaux=None):
        self.jumeaux = CollectionFaux(jumeaux)
        self.situations = CollectionFaux()
        self.relations = CollectionFaux()
        self.journal = CollectionFaux()
        self.actualites_ecartees = CollectionFaux()
        self.cases = CollectionInterdite()


class StoreFaux:
    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.appels = []

    async def lister_recents(self, limite=500):
        self.appels.append(("lister_recents", limite))
        return self.documents[:int(limite)] if limite else list(self.documents)

    async def lire(self, cid):
        self.appels.append(("lire", cid))
        return next((d for d in self.documents if d.get("id") == cid), None)

    async def compter(self):
        self.appels.append(("compter",))
        return len(self.documents)


def cas(cid, titre, quand=None, **champs):
    quand = quand or datetime.now(timezone.utc).isoformat()
    document = {
        "id": cid, "titre": titre, "objectif": f"Objectif de {titre}",
        "statut": "ouvert", "portee": "personnel", "responsable": "demo",
        "participants": ["demo"], "jumeaux": [], "conversation": [],
        "historique": [{"quand": quand, "texte": f"Travail conservé — {titre}"}],
        "cree_le": quand, "maj_le": quand,
    }
    document.update(champs)
    return document


def client_actualites(monkeypatch, store=None, db=None):
    from meridian.adapters.inbound.http import actualites as module

    if store is not None:
        monkeypatch.setattr(module, "travail_store", lambda db, dsn: store)
    deps = {
        "db": db or DbFaux(),
        "resoudre_perimetre": lambda acteur, espace: (acteur, {"id": "perso", "label": "Mon espace"}),
        "autorisations": lambda espace, ids: set(ids),
        "filtre_situation": lambda situation, aut, nom_vers_id: None,
        "ESPACES": [{"id": "perso", "label": "Mon espace"}],
        "NO_ID": NO_ID,
        "timezone": timezone,
        "slugify": lambda texte: texte,
        "journaler": lambda *args, **kwargs: None,
    }
    api = APIRouter(prefix="/api")
    api.include_router(module.build_actualites_router(deps))
    app = FastAPI()
    app.include_router(api)
    return TestClient(app)
