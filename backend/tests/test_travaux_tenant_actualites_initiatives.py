"""Tenant des Travaux créés par Actualités et Initiatives (revue C2)."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import actualites as actualites_module
from meridian.adapters.inbound.http import initiatives as initiatives_module
from test_conversation_routes import Collection
from aides_pont import CollectionPont


def _situation(tenant="local"):
    return {
        "id": "sit-1", "tenant_id": tenant, "titre": "Latence",
        "resume": "Le délai monte", "statut": "active", "score": 50,
        "jumeaux": [], "detectee": "2026-11-05T09:00:00+00:00",
        "cree_le": "2026-11-05T09:00:00+00:00",
    }


def _db(situation_tenant="local", initiative=None):
    return SimpleNamespace(
        jumeaux=Collection([]),
        situations=Collection([_situation(situation_tenant)]),
        relations=Collection([]),
        journal=Collection([]),
        actualites_ecartees=Collection([]),
        cases=Collection([]),
        initiatives=Collection([initiative] if initiative else []),
        pont_canonique=CollectionPont(),
    )


def _client(module, router, db):
    async def journaler(*args, **kwargs):
        return None

    deps = {
        "db": db,
        "resoudre_perimetre": lambda acteur, espace: (acteur, {"id": "perso"}),
        "autorisations": lambda espace, ids: set(ids),
        "filtre_situation": lambda situation, aut, nom_vers_id: situation,
        "ESPACES": [{"id": "perso"}],
        "NO_ID": {"_id": 0},
        "timezone": __import__("datetime").timezone,
        "slugify": lambda texte: texte.lower().replace(" ", "-"),
        "journaler": journaler,
    }
    api = APIRouter(prefix="/api")
    api.include_router(router(deps))
    app = FastAPI()
    app.include_router(api)
    return TestClient(app)


def test_actualites_stamp_le_tenant_du_travail_cree():
    db = _db()
    client = _client(actualites_module, actualites_module.build_actualites_router, db)

    r = client.post("/api/actualites/histoire/sit-sit-1/travail",
                    json={"intention": "comprendre"})

    assert r.status_code == 200, r.text
    assert db.cases.docs[0]["tenant_id"] == "local"


def test_actualites_ne_lit_pas_une_situation_d_un_autre_tenant():
    db = _db(situation_tenant="assurance")
    client = _client(actualites_module, actualites_module.build_actualites_router, db)

    r = client.post("/api/actualites/histoire/sit-sit-1/travail",
                    json={"intention": "comprendre"})

    assert r.status_code == 404
    assert db.cases.docs == []


def _initiative(tenant="local"):
    return {
        "id": "init-1", "tenant_id": tenant, "titre": "Initiative",
        "statut": "en_attente", "genre": "a_confirmer", "jumeaux": [],
        "raison": "Raison", "confiance": "moyenne",
    }


def test_initiatives_stamp_le_tenant_du_travail_cree():
    db = _db(initiative=_initiative())
    client = _client(initiatives_module, initiatives_module.build_initiatives_router, db)

    r = client.post("/api/initiatives/init-1/travail", json={"intention": "comprendre"})

    assert r.status_code == 200, r.text
    assert db.cases.docs[0]["tenant_id"] == "local"


def test_initiatives_ne_lit_pas_une_initiative_d_un_autre_tenant():
    db = _db(initiative=_initiative("assurance"))
    client = _client(initiatives_module, initiatives_module.build_initiatives_router, db)

    r = client.post("/api/initiatives/init-1/travail", json={"intention": "comprendre"})

    assert r.status_code == 404
    assert db.cases.docs == []


def test_initiatives_stamp_le_tenant_de_la_reponse():
    db = _db(initiative=_initiative())
    client = _client(initiatives_module, initiatives_module.build_initiatives_router, db)

    r = client.post("/api/initiatives/init-1/repondre", json={"choix": "Ignorer"})

    assert r.status_code == 200, r.text
    assert db.initiatives.docs[0]["tenant_id"] == "local"
    assert db.initiatives.docs[0]["statut"] == "refusee"
