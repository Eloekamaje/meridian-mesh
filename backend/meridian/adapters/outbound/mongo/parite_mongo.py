"""Double lecture Mongo / canonique : constate les écarts avant tout retrait.

Ce module ne migre et ne supprime rien. Il compare les collections legacy aux identités Postgres,
aux objets canoniques et au GraphStore du tenant, pour rendre visible ce qui manque avant de couper
une lecture Mongo.
"""
from __future__ import annotations

import asyncio
import json
import os

from meridian.adapters.outbound.postgres.migration_canonique import _collection, _documents

__all__ = ["comparer"]

_TYPES_SITUATION = {"SITUATION"}
_TYPES_INITIATIVE = {"INITIATIVE"}


def _ids(documents):
    valeurs = set()
    for document in documents:
        identifiant = document.get("id") if isinstance(document, dict) else None
        if identifiant is not None:
            valeurs.add(str(identifiant))
    return valeurs


def _identites_postgres(conn, tenant):
    with conn.cursor() as cur:
        return {str(ligne[0]) for ligne in cur.execute(
            "SELECT id FROM jumeau WHERE tenant_id = %s", (tenant,)).fetchall()}


def _objets_postgres(conn, tenant):
    with conn.cursor() as cur:
        lignes = cur.execute(
            "SELECT id, type FROM objet_entreprise WHERE tenant_id = %s", (tenant,)).fetchall()
    par_type = {}
    for identifiant, type_ in lignes:
        par_type.setdefault(str(type_), set()).add(str(identifiant))
    return par_type


def _etat_graphe(store, tenant):
    if store is None:
        return {"twins": set(), "relations": set()}
    try:
        etat = store.as_dict(tenant)
    except TypeError:
        etat = store.as_dict()
    return {
        "twins": {str(noeud.get("id")) for noeud in etat.get("noeuds") or [] if isinstance(noeud, dict)},
        "relations": {str(arete.get("id")) for arete in etat.get("aretes") or [] if isinstance(arete, dict)},
    }


def _ecart(nature, mongo, canonique):
    manquants = sorted(mongo - canonique)
    return {
        "nature": nature,
        "mongo": len(mongo),
        "canonique": len(canonique),
        "manquants": manquants[:200],
        "manquants_total": len(manquants),
    }


async def comparer(db, conn, store, tenant) -> dict:
    """Rend les comptes et les ids legacy absents des stores canoniques."""
    situations = await _documents(_collection(db, "situations"))
    initiatives = await _documents(_collection(db, "initiatives"))
    jumeaux = await _documents(_collection(db, "jumeaux"))
    relations = await _documents(_collection(db, "relations"))

    identites = _identites_postgres(conn, tenant)
    objets = _objets_postgres(conn, tenant)
    graphe = _etat_graphe(store, tenant)
    objets_situations = set().union(*(ids for type_, ids in objets.items() if type_ in _TYPES_SITUATION), set())
    objets_initiatives = set().union(*(ids for type_, ids in objets.items() if type_ in _TYPES_INITIATIVE), set())

    return {
        "tenant": tenant,
        "mongo": {
            "jumeaux": len(jumeaux),
            "relations": len(relations),
            "situations": len(situations),
            "initiatives": len(initiatives),
        },
        "canonique": {
            "identites": len(identites),
            "twins_graphe": len(graphe["twins"]),
            "relations_graphe": len(graphe["relations"]),
            "objets": sum(len(ids) for ids in objets.values()),
        },
        "ecarts": [
            _ecart("identite", _ids(jumeaux), identites),
            _ecart("situation", _ids(situations), objets_situations),
            _ecart("initiative", _ids(initiatives), objets_initiatives),
            _ecart("relation_graphe", _ids(relations), graphe["relations"]),
        ],
    }


def main():
    import argparse

    import psycopg
    from motor.motor_asyncio import AsyncIOMotorClient

    from meridian.adapters.outbound.neo4j import graph_store

    parseur = argparse.ArgumentParser(description="Écarts Mongo / canonique")
    parseur.add_argument("--tenant", required=True)
    arguments = parseur.parse_args()

    async def lancer():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        contexte = graph_store.ouvrir()
        try:
            with psycopg.connect(os.environ["JUMEAU_PG_DSN"]) as conn:
                rapport = await comparer(
                    client[os.environ["DB_NAME"]], conn, contexte["store"], arguments.tenant)
            print(json.dumps(rapport, ensure_ascii=False, indent=2))
        finally:
            contexte["fermer"]()
            client.close()

    asyncio.run(lancer())


if __name__ == "__main__":
    main()
