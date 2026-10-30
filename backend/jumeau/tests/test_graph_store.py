"""Fabrique GraphStore : choix mémoire/Neo4j, import paresseux, secret tu, fermeture et délégation de sync."""
import importlib
import sys
import types

import pytest

from jumeau import graph_store, graphe_sync
from jumeau.graphe import GrapheMemoire
from jumeau.graphe_neo4j import GrapheNeo4j

TENANT = "banque"
SECRET = "mot-de-passe-sentinelle-a-ne-jamais-fuiter"


def env_neo4j(**extra):
    return {
        "GRAPH_STORE": "neo4j",
        "NEO4J_URI": "neo4j://graph.local:7687",
        "NEO4J_USER": "mesh",
        "NEO4J_PASSWORD": SECRET,
        "NEO4J_DATABASE": "topologie",
        **extra,
    }


def twin(identifiant, type_="APPLICATION"):
    return {"id": identifiant, "tenant_id": TENANT, "type": type_, "nom": identifiant.upper()}


def relation(identifiant, source, cible):
    return {
        "id": identifiant,
        "tenant_id": TENANT,
        "source": source,
        "cible": cible,
        "type": "echange",
        "etat": "validation",
    }


def installer_faux_neo4j(monkeypatch):
    appels = {"driver": [], "sessions": [], "fermetures_driver": [], "fermetures_session": []}

    class FausseSession:
        def run(self, requete, params=None):
            return []

        def close(self):
            appels["fermetures_session"].append(self)

    class FauxDriver:
        def session(self, **options):
            session = FausseSession()
            appels["sessions"].append((options, session))
            return session

        def close(self):
            appels["fermetures_driver"].append(self)

    class FauxGraphDatabase:
        @staticmethod
        def driver(uri, auth=None, **options):
            driver = FauxDriver()
            appels["driver"].append((uri, auth, options, driver))
            return driver

    module = types.ModuleType("neo4j")
    module.GraphDatabase = FauxGraphDatabase
    monkeypatch.setitem(sys.modules, "neo4j", module)
    return appels


def test_environnement_vide_choisit_la_memoire():
    assert graph_store.depuis_environnement({}) == {"mode": "memoire"}
    assert graph_store.depuis_environnement({"GRAPH_STORE": "memoire"}) == {"mode": "memoire"}
    assert graph_store.depuis_environnement({"GRAPH_STORE": " MEMOIRE "}) == {"mode": "memoire"}


def test_neo4j_incomplet_echoue_sans_divulguer_le_secret():
    for manquant in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
        env = env_neo4j()
        env.pop(manquant)
        with pytest.raises(ValueError) as exc:
            graph_store.depuis_environnement(env)
        message = str(exc.value)
        assert "configuration Neo4j incomplète" in message
        assert manquant in message
        assert SECRET not in message
        assert "graph.local" not in message


def test_mode_inconnu_est_refuse():
    with pytest.raises(ValueError, match="GRAPH_STORE"):
        graph_store.depuis_environnement({"GRAPH_STORE": "neptune"})


def test_ouvrir_en_memoire_ne_charge_pas_le_driver(monkeypatch):
    appels = installer_faux_neo4j(monkeypatch)
    resultat = graph_store.ouvrir({})
    assert resultat["mode"] == "memoire"
    assert isinstance(resultat["store"], GrapheMemoire)
    resultat["fermer"]()
    assert appels["driver"] == []


def test_configuration_complete_appelle_driver_et_session(monkeypatch):
    appels = installer_faux_neo4j(monkeypatch)
    resultat = graph_store.ouvrir(env_neo4j())

    assert resultat["mode"] == "neo4j"
    assert isinstance(resultat["store"], GrapheNeo4j)
    assert len(appels["driver"]) == 1
    uri, auth, options, _driver = appels["driver"][0]
    assert uri == "neo4j://graph.local:7687"
    assert auth == ("mesh", SECRET)
    assert options == {}
    assert len(appels["sessions"]) == 1
    assert appels["sessions"][0][0] == {"database": "topologie"}
    assert resultat["store"].session is appels["sessions"][0][1]


def test_database_par_defaut_et_fermeture_explicite_idempotente(monkeypatch):
    appels = installer_faux_neo4j(monkeypatch)
    env = env_neo4j()
    env.pop("NEO4J_DATABASE")
    resultat = graph_store.ouvrir(env)

    assert appels["sessions"][0][0] == {"database": "neo4j"}
    fermer = resultat["fermer"]
    fermer()
    fermer()
    assert len(appels["fermetures_session"]) == 1
    assert len(appels["fermetures_driver"]) == 1


def test_synchroniser_depuis_identites_delegue_et_transmet_dry_run(monkeypatch):
    store = GrapheMemoire()
    twin_ = twin("a")
    relation_ = relation("r1", "a", "b")
    recu = []

    def faux_synchroniser(store_, tenant, twins, relations, dry_run=False):
        recu.append((store_, tenant, twins, relations, dry_run))
        return {"rapport": "délégué"}

    monkeypatch.setattr(graphe_sync, "synchroniser", faux_synchroniser)
    rapport = graph_store.synchroniser_depuis_identites(
        store, TENANT, [twin_], [relation_], dry_run=True
    )

    assert rapport == {"rapport": "délégué"}
    assert recu == [(store, TENANT, [twin_], [relation_], True)]


def test_synchronisation_reelle_et_dry_run_avec_memoire():
    store = GrapheMemoire()
    twins = [twin("a"), twin("b", "PROCESS")]
    relations = [relation("r1", "a", "b")]

    simulation = graph_store.synchroniser_depuis_identites(
        store, TENANT, twins, relations, dry_run=True
    )
    assert simulation == {"twins": 2, "relations": 1, "ignores": [], "erreurs": []}
    assert store.noeuds == {} and store.aretes == {}

    reel = graph_store.synchroniser_depuis_identites(store, TENANT, twins, relations)
    assert reel == simulation
    assert set(store.noeuds) == {(TENANT, "a"), (TENANT, "b")}
    assert set(store.aretes) == {(TENANT, "r1")}
    assert [voisin["id"] for voisin in store.voisins(TENANT, "a")] == ["b"]


def test_import_du_module_ne_tente_aucune_connexion(monkeypatch):
    appels = []

    class GraphDatabaseInterdit:
        @staticmethod
        def driver(*args, **kwargs):
            appels.append((args, kwargs))
            raise AssertionError("connexion tentée à l'import")

    module = types.ModuleType("neo4j")
    module.GraphDatabase = GraphDatabaseInterdit
    monkeypatch.setitem(sys.modules, "neo4j", module)

    importlib.reload(graph_store)
    assert appels == []
    assert graph_store.depuis_environnement({}) == {"mode": "memoire"}
