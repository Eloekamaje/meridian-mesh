"""La vitrine Mongo reste réservée au tenant demo ; les autres tenants ne la voient pas."""
import asyncio
import os

from meridian.adapters.inbound.http.tenant_twins import jumeau_du_tenant, jumeaux_du_tenant


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, limite):
        return self.docs[:limite]


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, requete, projection):
        return _Curseur(self.docs)

    async def find_one(self, requete, projection):
        return next((doc for doc in self.docs if doc.get("id") == requete.get("id")), None)


class _Db:
    def __init__(self):
        self.jumeaux = _Collection([
            {"id": "conduit", "nom": "Conduit"},
            {"id": "paiements", "nom": "Paiements"},
        ])


def test_demo_utilise_la_vitrine_mongo():
    db = _Db()
    docs = asyncio.run(jumeaux_du_tenant(db, "demo"))
    assert [doc["id"] for doc in docs] == ["conduit", "paiements"]
    assert asyncio.run(jumeau_du_tenant(db, "demo", "conduit"))["nom"] == "Conduit"


def test_un_autre_tenant_ne_voit_pas_la_vitrine_demo_sans_postgres(monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    db = _Db()
    assert asyncio.run(jumeaux_du_tenant(db, "pilot")) == []
    assert asyncio.run(jumeau_du_tenant(db, "pilot", "conduit")) is None


def test_le_tenant_local_reste_compatible_demo():
    db = _Db()
    assert len(asyncio.run(jumeaux_du_tenant(db, "local"))) == 2
