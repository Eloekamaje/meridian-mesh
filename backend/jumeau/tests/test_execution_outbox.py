import os

import psycopg

from jumeau.execution import depot
from jumeau.execution.outbox import DispatcherOutbox, planifier_projection
from jumeau.execution.projecteur_graphe import ProjecteurGraphe
from jumeau.graphe import GrapheMemoire
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def test_projection_via_outbox(conn):
    twins = [
        {"id": "app-a", "tenant_id": "banque", "nom": "App A", "type": "APPLICATION"},
        {"id": "app-b", "tenant_id": "banque", "nom": "App B", "type": "APPLICATION"},
    ]
    relations = [
        {"id": "rel-1", "tenant_id": "banque", "source": "app-a", "target": "app-b",
         "type": "DEPEND_DE", "etat": "supposee"},
    ]
    planifier_projection(conn, "banque", twins, relations)
    store = GrapheMemoire()
    dispatcher = DispatcherOutbox(_factory(conn), {
        "graph.synchroniser": ProjecteurGraphe(store).traiter,
    })
    assert dispatcher.traiter() == 1
    assert ("banque", "app-a") in store.noeuds
    assert ("banque", "rel-1") in store.aretes
    assert dispatcher.traiter() == 0


def test_projection_est_idempotente(conn):
    twins = [{"id": "app-a", "tenant_id": "banque", "nom": "App A", "type": "APPLICATION"}]
    store = GrapheMemoire()
    projecteur = ProjecteurGraphe(store)
    evenement = {"type": "graph.synchroniser", "tenant_id": "banque",
                 "payload": {"twins": twins, "relations": []}}
    assert projecteur.traiter(evenement)["twins"] == 1
    assert projecteur.traiter(evenement)["twins"] == 1
    assert len(store.noeuds) == 1
