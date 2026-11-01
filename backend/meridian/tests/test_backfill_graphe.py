"""Backfill graphe : lecture canonique, dry-run sans écriture, apply idempotent, orphelins."""
import asyncio

import pytest

from meridian.adapters.outbound.neo4j import backfill_graphe
from meridian.domain.graphe import GrapheMemoire
from meridian.tests.conftest import besoin_pg

TENANT = "banque"

RELATION = {
    "id": "rel-1",
    "tenant_id": TENANT,
    "source": "app-a",
    "cible": "app-b",
    "type": "echange",
    "etat": "supposee",
}


class _Collection:
    def __init__(self, documents):
        self.documents = list(documents)
        self.filtre = None

    async def find(self, filtre, projection):
        self.filtre = filtre
        for document in self.documents:
            yield dict(document)


class _Db:
    def __init__(self, relations=()):
        self.relations = _Collection(relations)


def _identite(conn, identifiant, tenant=TENANT, type_="APPLICATION"):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe, type) VALUES (%s, %s, %s, %s, %s)",
        (identifiant, tenant, identifiant.upper(), "equipe", type_),
    )


def test_lire_relations_filtre_les_extremites_et_complete_le_tenant():
    db = _Db([RELATION])

    relations = asyncio.run(backfill_graphe.lire_relations(db, TENANT, ["app-a", "app-b"]))

    assert relations == [RELATION]
    assert db.relations.filtre == {"$or": [
        {"source": {"$in": ["app-a", "app-b"]}},
        {"cible": {"$in": ["app-a", "app-b"]}},
    ]}
    assert asyncio.run(backfill_graphe.lire_relations(db, TENANT, [])) == []


@besoin_pg
def test_executer_dry_run_lit_postgres_et_mongo_sans_ecrire(conn):
    _identite(conn, "app-a")
    _identite(conn, "app-b", type_="PROCESS")
    store = GrapheMemoire()

    rapport = backfill_graphe.executer(conn, _Db([RELATION]), TENANT, store=store, dry_run=True)

    assert rapport["tenant"] == TENANT and rapport["dry_run"] is True
    assert (rapport["twins_lus"], rapport["relations_lues"]) == (2, 1)
    assert (rapport["twins_projetes"], rapport["relations_projetees"]) == (2, 1)
    assert rapport["ignores"] == [] and rapport["erreurs"] == []
    assert "graphe" not in rapport
    assert store.noeuds == {} and store.aretes == {}


@besoin_pg
def test_apply_ecrit_une_fois_et_est_idempotent(conn):
    _identite(conn, "app-a")
    _identite(conn, "app-b", type_="PROCESS")
    store = GrapheMemoire()

    premier = backfill_graphe.executer(
        conn, _Db([RELATION]), TENANT, store=store, dry_run=False)
    second = backfill_graphe.executer(
        conn, _Db([RELATION]), TENANT, store=store, dry_run=False)

    assert premier["graphe"] == {"noeuds": 2, "aretes": 1}
    assert second["graphe"] == {"noeuds": 2, "aretes": 1}
    assert set(store.noeuds) == {(TENANT, "app-a"), (TENANT, "app-b")}
    assert set(store.aretes) == {(TENANT, "rel-1")}
    assert store.noeuds[(TENANT, "app-b")].type == "PROCESS"


@besoin_pg
def test_relation_orpheline_est_ignoree_et_isolation_tenant_respectee(conn):
    _identite(conn, "app-a")
    relations = [
        {**RELATION, "id": "rel-orpheline", "cible": "absent"},
        {**RELATION, "id": "rel-autre", "tenant_id": "autre"},
    ]

    rapport = backfill_graphe.executer(
        conn, _Db(relations), TENANT, store=GrapheMemoire(), dry_run=False)

    assert rapport["twins_projetes"] == 1
    assert rapport["relations_projetees"] == 0
    assert rapport["ignores"][0]["id"] == "rel-orpheline"
    assert rapport["ignores"][0]["absents"] == ["absent"]
    assert rapport["erreurs"][0]["id"] == "rel-autre"
    assert "autre tenant" in rapport["erreurs"][0]["raison"]


@besoin_pg
def test_lire_twins_ne_renvoie_que_le_tenant_demande(conn):
    _identite(conn, "app-a")
    _identite(conn, "app-x", tenant="autre")

    twins = backfill_graphe.lire_twins(conn, TENANT)

    assert [twin["id"] for twin in twins] == ["app-a"]
    assert twins[0]["label"] == "APP-A"


def test_apply_refuse_un_store_memoire(monkeypatch):
    monkeypatch.delenv("GRAPH_STORE", raising=False)

    with pytest.raises(SystemExit, match="GRAPH_STORE=neo4j"):
        backfill_graphe.principal([
            "--tenant", TENANT, "--apply",
            "--dsn", "postgresql://meridian:secret@127.0.0.1:1/meridian",
            "--mongo-url", "mongodb://127.0.0.1:1",
            "--db-name", "meridian",
        ])
