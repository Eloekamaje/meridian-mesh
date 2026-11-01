"""Les sources branchées changent de version : curseur et situation, sans extraction de delta."""
import asyncio

from psycopg.rows import dict_row

from meridian.adapters.outbound.llm import gardien
from meridian.adapters.outbound.postgres import ingestion_runtime
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg


class LecteurFaux:
    def __init__(self, version):
        self.version = version

    def version_courante(self):
        return self.version


class SituationsFausses:
    def __init__(self):
        self.documents = {}

    async def update_many(self, filtre, maj):
        for identifiant, document in list(self.documents.items()):
            if document.get("statut") == "active":
                self.documents[identifiant] = {**document, **maj.get("$set", {})}

    async def replace_one(self, filtre, document, upsert=False):
        self.documents[document["id"]] = dict(document)


class DbFausse:
    def __init__(self):
        self.situations = SituationsFausses()


def _source(conn, type_="CONFLUENCE", curseur="v1"):
    conn.execute("INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES ('tbt', 'banque', 'TBT', 'eq')")
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur, url) "
            "VALUES ('banque', 'tbt', %s, 'doc', 'page-1', %s, 'https://exemple.test/page-1') "
            "RETURNING *", (type_, curseur)).fetchone()


def test_une_source_branchee_publie_une_situation_au_changement_de_version(conn):
    source = _source(conn)
    db = DbFausse()

    premier = asyncio.run(gardien.veiller_source(conn, db, "tbt", source, lecteur=LecteurFaux("v1")))
    assert premier["changement"] is False
    assert db.situations.documents == {}

    second = asyncio.run(gardien.veiller_source(conn, db, "tbt", source, lecteur=LecteurFaux("v2")))
    assert second["changement"] is True
    assert len(db.situations.documents) == 1
    situation = next(iter(db.situations.documents.values()))
    assert situation["type"] == "source" and situation["jumeaux"] == ["tbt"]
    assert conn.execute("SELECT curseur FROM source WHERE id = %s", (source["id"],)).fetchone()[0] == "v2"

    identique = asyncio.run(gardien.veiller_source(conn, db, "tbt", source, lecteur=LecteurFaux("v2")))
    assert identique["changement"] is False
    assert len(db.situations.documents) == 1


def test_planifier_sources_inclut_les_sources_branchees(conn):
    source = _source(conn, type_="JIRA", curseur=None)
    assert ingestion_runtime.planifier_sources(conn, 3600) == 1
    assert conn.execute(
        "SELECT 1 FROM source_schedule WHERE source_id = %s", (source["id"],)).fetchone() is not None
