import asyncio
import logging
import os
import time

import psycopg
import pytest

from jumeau import gardien, graph_store
from jumeau.execution.outbox import (
    MODE_DIRECT,
    MODE_OUTBOX,
    DispatcherOutbox,
    mode_projection,
    planifier_projection,
)
from jumeau.execution.outbox_worker import BoucleOutbox
from jumeau.execution.projecteur_graphe import ProjecteurGraphe
from jumeau.graphe import GrapheMemoire
from jumeau.tests.conftest import besoin_pg


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def _db(relations=()):
    class _Relations:
        def find(self, _filtre, _projection):
            async def lignes():
                for relation in relations:
                    yield dict(relation)
            return lignes()

    class _Db:
        pass

    base = _Db()
    base.relations = _Relations()
    return base


def _identite(conn, identifiant, tenant="banque"):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
        (identifiant, tenant, identifiant.upper(), "equipe"),
    )


@besoin_pg
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


@besoin_pg
def test_projection_est_idempotente(conn):
    twins = [{"id": "app-a", "tenant_id": "banque", "nom": "App A", "type": "APPLICATION"}]
    store = GrapheMemoire()
    projecteur = ProjecteurGraphe(store)
    evenement = {"type": "graph.synchroniser", "tenant_id": "banque",
                 "payload": {"twins": twins, "relations": []}}
    assert projecteur.traiter(evenement)["twins"] == 1
    assert projecteur.traiter(evenement)["twins"] == 1
    assert len(store.noeuds) == 1


def test_mode_projection_valide_les_valeurs_et_refuse_l_inconnu():
    assert mode_projection({}) == MODE_DIRECT
    assert mode_projection({"JUMEAU_GRAPH_PROJECTION": "  "}) == MODE_DIRECT
    assert mode_projection({"JUMEAU_GRAPH_PROJECTION": " outbox "}) == MODE_OUTBOX
    with pytest.raises(ValueError, match="JUMEAU_GRAPH_PROJECTION"):
        mode_projection({"JUMEAU_GRAPH_PROJECTION": "eventual"})


@besoin_pg
def test_mode_outbox_planifie_sans_ecrire_directement_dans_le_graphe(conn, monkeypatch):
    monkeypatch.setenv("JUMEAU_GRAPH_PROJECTION", "outbox")
    monkeypatch.setenv("GRAPH_STORE", "memoire")
    monkeypatch.setattr(graph_store, "ouvrir", lambda *a, **k: pytest.fail(
        "le mode outbox ne doit pas ouvrir le GraphStore"))
    _identite(conn, "app-a")
    _identite(conn, "app-b")
    relation = {"id": "rel-1", "tenant_id": "banque", "source": "app-a", "cible": "app-b",
                "type": "echange", "etat": "supposee"}
    store = GrapheMemoire()

    rapport = asyncio.run(gardien._synchroniser_graphe(
        conn, _db([relation]), {"id": "app-a", "tenant_id": "banque"}, store=store))

    assert rapport is None
    assert store.noeuds == {} and store.aretes == {}
    ligne = conn.execute(
        "SELECT tenant_id, type, payload, publie_le FROM execution_outbox ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert ligne[0] == "banque" and ligne[1] == "graph.synchroniser"
    assert {t["id"] for t in ligne[2]["twins"]} == {"app-a", "app-b"}
    assert ligne[2]["relations"][0]["id"] == "rel-1"
    assert ligne[3] is None

    dispatcher = DispatcherOutbox(_factory(conn), {
        "graph.synchroniser": ProjecteurGraphe(store).traiter,
    })
    assert dispatcher.traiter() == 1
    assert set(store.noeuds) == {("banque", "app-a"), ("banque", "app-b")}
    assert ("banque", "rel-1") in store.aretes


@besoin_pg
def test_mode_direct_synchronise_et_planifie_toujours(conn, monkeypatch):
    monkeypatch.setenv("JUMEAU_GRAPH_PROJECTION", "direct")
    monkeypatch.setenv("GRAPH_STORE", "memoire")
    _identite(conn, "app-a")
    store = GrapheMemoire()

    rapport = asyncio.run(gardien._synchroniser_graphe(
        conn, _db(), {"id": "app-a", "tenant_id": "banque"}, store=store))

    assert rapport["twins"] == 1
    assert ("banque", "app-a") in store.noeuds
    assert conn.execute("SELECT count(*) FROM execution_outbox").fetchone()[0] == 1


@besoin_pg
def test_mode_inconnu_refuse_sans_ecriture(conn, monkeypatch, caplog):
    monkeypatch.setenv("JUMEAU_GRAPH_PROJECTION", "eventual")
    monkeypatch.setenv("GRAPH_STORE", "memoire")
    _identite(conn, "app-a")
    store = GrapheMemoire()

    with caplog.at_level(logging.ERROR, logger="meridian.gardien"):
        rapport = asyncio.run(gardien._synchroniser_graphe(
            conn, _db(), {"id": "app-a", "tenant_id": "banque"}, store=store))

    assert rapport is None
    assert store.noeuds == {}
    assert conn.execute("SELECT count(*) FROM execution_outbox").fetchone()[0] == 0
    assert "JUMEAU_GRAPH_PROJECTION" in caplog.text


def test_boucle_outbox_tourne_et_s_arrete_avec_des_doubles():
    class _Dispatcher:
        def __init__(self):
            self.appels = 0

        def traiter(self, limite=100):
            self.appels += 1
            return 1

    dispatcher = _Dispatcher()
    boucle = BoucleOutbox(dispatcher, intervalle=0.01)
    fil = boucle.demarrer()
    limite = time.monotonic() + 2
    while dispatcher.appels == 0 and time.monotonic() < limite:
        time.sleep(0.01)
    boucle.arreter(timeout=1)

    assert dispatcher.appels >= 1
    assert not fil.is_alive()


def test_un_publieur_generique_recoit_les_types_sans_consommateur_specifique():
    recus = []
    dispatcher = DispatcherOutbox(lambda: None, {"*": recus.append})
    dispatcher._publier({"type": "outil.audit", "id": 1})
    assert recus == [{"type": "outil.audit", "id": 1}]
