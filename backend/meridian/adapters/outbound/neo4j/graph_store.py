"""Fabrique du port `GraphStore` : Neo4j quand il est configuré, mémoire en développement.

La configuration est lue explicitement (`GRAPH_STORE=neo4j`, `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, `NEO4J_DATABASE`) ; sans `GRAPH_STORE=neo4j`, le store reste en mémoire. Le driver
`neo4j` n'est importé que dans `ouvrir`, jamais à l'import du module, et aucun secret n'est recopié
dans un message d'erreur.

Limites assumées :

- `ouvrir` ne teste pas la connexion : le premier appel au store révèle un serveur injoignable ;
- la fermeture est explicite et idempotente ; l'appelant doit l'invoquer, par exemple dans un `finally` ;
- `NEO4J_DATABASE` vaut `neo4j` par défaut, comme la base par défaut du serveur ;
- `synchroniser_depuis_identites` ne fait que déléguer à `jumeau.graphe_sync.synchroniser`.
"""
from __future__ import annotations

import os

from meridian.application import graphe_sync
from meridian.domain.graphe import GrapheMemoire
from meridian.adapters.outbound.neo4j.graphe_neo4j import GrapheNeo4j

MODE_MEMOIRE = "memoire"
MODE_NEO4J = "neo4j"
DATABASE_DEFAUT = "neo4j"
_VARIABLES_NEO4J = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")


def _valeur(env, nom: str) -> str:
    return str(env.get(nom) or "").strip()


def depuis_environnement(env=None) -> dict:
    """Rend la configuration du store sans ouvrir de connexion ni exposer de secret dans une erreur."""
    env = os.environ if env is None else env
    mode = _valeur(env, "GRAPH_STORE").lower()
    if not mode or mode == MODE_MEMOIRE:
        return {"mode": MODE_MEMOIRE}
    if mode != MODE_NEO4J:
        raise ValueError("GRAPH_STORE inconnu : valeurs acceptées neo4j ou memoire")

    manquants = [nom for nom in _VARIABLES_NEO4J if not _valeur(env, nom)]
    if manquants:
        raise ValueError("configuration Neo4j incomplète : " + ", ".join(manquants))

    return {
        "mode": MODE_NEO4J,
        "uri": _valeur(env, "NEO4J_URI"),
        "user": _valeur(env, "NEO4J_USER"),
        "password": _valeur(env, "NEO4J_PASSWORD"),
        "database": _valeur(env, "NEO4J_DATABASE") or DATABASE_DEFAUT,
    }


def _fermeur(driver, session):
    etat = {"ferme": False}

    def fermer():
        if etat["ferme"]:
            return
        etat["ferme"] = True
        try:
            session.close()
        finally:
            driver.close()

    return fermer


def ouvrir(env=None):
    """Ouvre le store configuré et rend `{store, mode, fermer}` ; le driver reste paresseux."""
    configuration = depuis_environnement(env)
    if configuration["mode"] == MODE_MEMOIRE:
        return {"store": GrapheMemoire(), "mode": MODE_MEMOIRE, "fermer": lambda: None}

    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise RuntimeError(
            "Neo4j demandé mais le paquet neo4j n'est pas installé"
        ) from None

    try:
        driver = GraphDatabase.driver(
            configuration["uri"],
            auth=(configuration["user"], configuration["password"]),
        )
    except Exception as exc:
        raise RuntimeError(
            f"connexion Neo4j impossible ({type(exc).__name__})"
        ) from None

    try:
        session = driver.session(database=configuration["database"])
        store = GrapheNeo4j(session)
    except Exception as exc:
        driver.close()
        raise RuntimeError(
            f"session Neo4j impossible ({type(exc).__name__})"
        ) from None

    return {
        "store": store,
        "mode": MODE_NEO4J,
        "fermer": _fermeur(driver, session),
    }


def synchroniser_depuis_identites(store, tenant, twins, relations, dry_run=False) -> dict:
    """Synchronise des identités déjà chargées vers le store, sans lire Postgres ni ouvrir de connexion."""
    return graphe_sync.synchroniser(store, tenant, twins, relations, dry_run=dry_run)
