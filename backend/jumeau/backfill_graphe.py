"""Backfill contrôlé des Twins et relations canoniques vers le GraphStore.

Postgres (`jumeau`) porte les Twins ; Mongo (`relations`) porte les liens legacy du tenant. Le module
ne fait que lire ces deux sources et délègue l'écriture idempotente à `jumeau.graphe_sync` : upsert
par `(tenant_id, id)`, aucune suppression, aucun déplacement de `graphe_sync`.

`--dry-run` est le défaut : le mapping et les orphelins sont calculés sur un graphe mémoire, sans
ouvrir Neo4j. `--apply` exige `GRAPH_STORE=neo4j` et refuse un store mémoire, qui perdrait la
projection. Le rapport JSON est stable et ne contient aucun secret.

Usage :

    python -m jumeau.backfill_graphe --tenant demo --dry-run
    python -m jumeau.backfill_graphe --tenant demo --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping

import psycopg
from psycopg.rows import dict_row

from jumeau import graphe_sync, graph_store
from jumeau.graphe import GrapheMemoire


def lire_twins(conn, tenant_id: str) -> list[dict]:
    """Lit l'identité canonique des Twins du tenant, sans Claims ni preuves."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, tenant_id, type, nom AS label, mission, domaine, equipe "
            "FROM jumeau WHERE tenant_id = %s ORDER BY id",
            (tenant_id,),
        ).fetchall()
    return [dict(ligne) for ligne in lignes]


async def lire_relations(db, tenant_id: str, identifiants) -> list[dict]:
    """Lit les relations Mongo dont une extrémité est un Twin du tenant."""
    identifiants = [str(identifiant) for identifiant in identifiants if str(identifiant).strip()]
    if db is None or not identifiants:
        return []
    filtre = {"$or": [
        {"source": {"$in": identifiants}},
        {"cible": {"$in": identifiants}},
    ]}
    relations = []
    async for relation in db.relations.find(filtre, {"_id": 0}):
        document = dict(relation)
        document.setdefault("tenant_id", tenant_id)
        relations.append(document)
    return relations


def _compte_tenant(collection, tenant: str) -> int:
    return sum(
        1 for cle in collection
        if isinstance(cle, tuple) and cle and str(cle[0]) == tenant
    )


def etat_graphe(store, tenant_id: str) -> dict | None:
    """Compte les nœuds et arêtes du tenant, sans dépendre du type exact du store."""
    noeuds = getattr(store, "noeuds", None)
    aretes = getattr(store, "aretes", None)
    if isinstance(noeuds, Mapping) and isinstance(aretes, Mapping):
        return {
            "noeuds": _compte_tenant(noeuds, tenant_id),
            "aretes": _compte_tenant(aretes, tenant_id),
        }
    as_dict = getattr(store, "as_dict", None)
    if callable(as_dict):
        for arguments in ((tenant_id,), ()):
            try:
                etat = as_dict(*arguments)
            except TypeError:
                continue
            except Exception:
                return None
            if isinstance(etat, Mapping):
                return {
                    "noeuds": len(etat.get("noeuds") or []),
                    "aretes": len(etat.get("aretes") or []),
                }
    return None


def projeter(store, tenant_id: str, twins, relations, *, dry_run: bool = True) -> dict:
    """Projette un lot déjà chargé et rend un rapport stable, sans écriture en dry-run."""
    if store is None:
        raise ValueError("store attendu")
    tenant = str(tenant_id or "").strip()
    if not tenant:
        raise ValueError("tenant_id vide")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run doit être un booléen")

    twins = list(twins or ())
    relations = list(relations or ())
    rapport = graphe_sync.synchroniser(store, tenant, twins, relations, dry_run=dry_run)
    resultat = {
        "tenant": tenant,
        "dry_run": dry_run,
        "twins_lus": len(twins),
        "relations_lues": len(relations),
        "twins_projetes": rapport["twins"],
        "relations_projetees": rapport["relations"],
        "ignores": rapport["ignores"],
        "erreurs": rapport["erreurs"],
    }
    if not dry_run:
        resultat["graphe"] = etat_graphe(store, tenant)
    return resultat


def executer(conn, db, tenant_id: str, *, store=None, dry_run: bool = True) -> dict:
    """Charge Postgres/Mongo puis projette ; `store` peut être injecté pour les tests."""
    if store is None:
        if not dry_run:
            raise ValueError("GraphStore requis pour --apply")
        store = GrapheMemoire()
    twins = lire_twins(conn, tenant_id)
    relations = asyncio.run(lire_relations(db, tenant_id, [twin["id"] for twin in twins]))
    return projeter(store, tenant_id, twins, relations, dry_run=dry_run)


def principal(argv=None) -> int:
    parseur = argparse.ArgumentParser(
        description="Backfill idempotent des Twins et relations canoniques vers Neo4j",
    )
    parseur.add_argument("--tenant", required=True, help="tenant canonique à projeter")
    parseur.add_argument("--dsn", default=os.environ.get("JUMEAU_PG_DSN"),
                         help="DSN Postgres (défaut : JUMEAU_PG_DSN)")
    parseur.add_argument("--mongo-url", default=os.environ.get("MONGO_URL"),
                         help="URL Mongo (défaut : MONGO_URL)")
    parseur.add_argument("--db-name", default=os.environ.get("DB_NAME"),
                         help="base Mongo (défaut : DB_NAME)")
    mode = parseur.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="calcule sans écrire (défaut)")
    mode.add_argument("--apply", action="store_true",
                      help="écrit dans Neo4j (exige GRAPH_STORE=neo4j)")
    args = parseur.parse_args(argv)

    tenant = str(args.tenant or "").strip()
    if not tenant:
        raise SystemExit("--tenant vide")
    if not args.dsn:
        raise SystemExit("JUMEAU_PG_DSN ou --dsn requis")
    if not args.mongo_url or not args.db_name:
        raise SystemExit("MONGO_URL et DB_NAME requis (ou --mongo-url et --db-name)")
    dry_run = not args.apply

    contexte = None
    client = None
    conn = None
    try:
        if args.apply:
            contexte = graph_store.ouvrir()
            if contexte["mode"] != graph_store.MODE_NEO4J:
                raise SystemExit(
                    "--apply exige GRAPH_STORE=neo4j (un store mémoire perdrait la projection)")
            store = contexte["store"]
        else:
            store = GrapheMemoire()

        from motor.motor_asyncio import AsyncIOMotorClient

        conn = psycopg.connect(args.dsn, autocommit=True, connect_timeout=5)
        client = AsyncIOMotorClient(args.mongo_url, serverSelectionTimeoutMS=5000)
        rapport = executer(conn, client[args.db_name], tenant, store=store, dry_run=dry_run)
    finally:
        if client is not None:
            client.close()
        if conn is not None:
            conn.close()
        if contexte is not None:
            contexte["fermer"]()

    print(json.dumps(rapport, ensure_ascii=False, indent=2, default=str))
    return 0 if not rapport["erreurs"] else 2


if __name__ == "__main__":
    raise SystemExit(principal())
