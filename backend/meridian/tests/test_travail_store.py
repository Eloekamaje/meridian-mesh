"""Sélection du store Travail et lecture Mongo sans base."""
import asyncio

import pytest

from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres
from meridian.adapters.outbound.travail_store import STORE_ENV, travail_store


class CurseurFaux:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, champs):
        for champ, sens in reversed(champs):
            self.documents.sort(key=lambda d: d.get(champ) or "", reverse=sens < 0)
        return self

    def limit(self, nombre):
        self.documents = self.documents[:nombre]
        return self

    async def to_list(self, nombre=None):
        return list(self.documents[:nombre]) if nombre else list(self.documents)


class CollectionFaux:
    def __init__(self, documents):
        self.documents = documents

    def find(self, filtre, projection):
        return CurseurFaux(self.documents)

    async def count_documents(self, filtre):
        return len(self.documents)


class BaseFaux:
    def __init__(self, documents):
        self.cases = CollectionFaux(documents)


def test_le_defaut_reste_mongo(monkeypatch):
    monkeypatch.delenv(STORE_ENV, raising=False)
    store = travail_store(BaseFaux([{"id": "a", "maj_le": "2"},
                                    {"id": "b", "maj_le": "1"}]))
    assert isinstance(store, TravailMongo)
    assert [d["id"] for d in asyncio.run(store.lister_recents(limite=None))] == ["a", "b"]
    assert asyncio.run(store.compter()) == 2


def test_postgres_est_selectionne_par_le_drapeau(monkeypatch):
    monkeypatch.setenv(STORE_ENV, "postgres")
    store = travail_store(BaseFaux([]), dsn="postgresql://x/y", tenant="banque")
    assert isinstance(store, TravailPostgres)
    assert store.tenant_id == "banque"


def test_postgres_sans_dsn_echoue_explicitement(monkeypatch):
    monkeypatch.setenv(STORE_ENV, "postgres")
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    with pytest.raises(RuntimeError, match="JUMEAU_PG_DSN"):
        travail_store(BaseFaux([]), dsn=None)


def test_un_drapeau_inconnu_est_refuse(monkeypatch):
    monkeypatch.setenv(STORE_ENV, "sqlite")
    with pytest.raises(RuntimeError, match="mongo ou postgres"):
        travail_store(BaseFaux([]))


from meridian.tests.conftest import besoin_pg


@besoin_pg
def test_upsert_postgres_ne_change_la_version_que_si_le_document_change(conn):
    depot = TravailPostgres(conn=conn, tenant_id="banque")
    document = {"_id": "mongo-1", "id": "c1",
                "maj_le": "2026-01-01T00:00:00+00:00", "titre": "A"}

    assert asyncio.run(depot.upsert(document)) is True
    assert conn.execute("SELECT version FROM travail").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM travail").fetchone()[0] == 1

    assert asyncio.run(depot.upsert(dict(document))) is False
    assert conn.execute("SELECT version FROM travail").fetchone()[0] == 1

    document["titre"] = "B"
    assert asyncio.run(depot.upsert(document)) is False
    assert conn.execute("SELECT version FROM travail").fetchone()[0] == 2
    assert asyncio.run(depot.lire("c1"))["titre"] == "B"
    assert asyncio.run(depot.compter()) == 1
    assert depot.dernier_curseur().id == "mongo-1"
