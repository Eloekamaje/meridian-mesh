#!/usr/bin/env python3
"""Backfill additif des manifestes de naissance pour les Twins antérieurs à l'ADR-0031.

Par défaut : dry-run. `--apply` écrit un manifeste `ARTIFACT` par Twin qui n'en a pas ; il ne
promeut aucun Twin, n'émet aucun `twin.born` et ne confirme aucune relation. Le schéma est
rejoué avant le backfill (idempotent) sauf avec `--sans-schema`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))


def _limite(valeur) -> int:
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("limite doit être un entier positif") from exc
    if borne < 1:
        raise argparse.ArgumentTypeError("limite doit être un entier positif")
    return borne


def _afficher(rapport) -> None:
    if rapport["dry_run"]:
        print(
            f"backfill manifestes de naissance (dry-run) : {len(rapport['a_creer'])} twin(s) à préparer, "
            f"{len(rapport['ignores'])} déjà pourvu(s), 0 écrit ; relancer avec --apply"
        )
    else:
        print(
            f"backfill manifestes de naissance : {len(rapport['crees'])} twin(s) préparé(s) "
            f"sur {rapport['twins']} examiné(s), {len(rapport['ignores'])} déjà pourvu(s)"
        )
    if rapport["a_creer"]:
        print("à préparer : " + ", ".join(rapport["a_creer"]))
    if rapport["ignores"]:
        print("déjà pourvus : " + ", ".join(rapport["ignores"]))


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python scripts/backfill-manifestes-naissance.py",
        description="Backfill idempotent des manifestes de naissance des Twins existants",
    )
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--tenant", default=None, help="limiter à un tenant")
    analyseur.add_argument("--limite", type=_limite, default=None, help="borner le lot traité")
    analyseur.add_argument("--sans-schema", action="store_true",
                           help="ne pas rejouer schema.sql avant le backfill")
    analyseur.add_argument("--refresh", action="store_true",
                           help="reconstruire aussi les manifestes legacy (portée, ressources)")
    groupe = analyseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", dest="appliquer", action="store_false")
    groupe.add_argument("--apply", dest="appliquer", action="store_true")
    analyseur.set_defaults(appliquer=False)
    args = analyseur.parse_args(argv)

    dsn = args.dsn or os.environ.get("JUMEAU_WORKER_PG_DSN") or os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise SystemExit("JUMEAU_PG_DSN (ou --dsn) requis")

    import psycopg

    from meridian.adapters.outbound.postgres import depot as postgres_depot
    from meridian.adapters.outbound.postgres import relations_naissance

    with psycopg.connect(dsn, autocommit=True) as conn:
        if not args.sans_schema:
            postgres_depot.appliquer_schema(conn)
        if args.tenant:
            tenants = [args.tenant]
        else:
            tenants = [ligne[0] for ligne in conn.execute(
                "SELECT DISTINCT tenant_id FROM jumeau ORDER BY tenant_id").fetchall()]
        with conn.transaction():
            rapports = [relations_naissance.backfill_manifestes(
                conn, tenant, appliquer=args.appliquer, limite=args.limite)
                for tenant in tenants]
            rafraichissements = ([relations_naissance.rafraichir_manifestes_legacy(
                conn, tenant, appliquer=args.appliquer, limite=args.limite)
                for tenant in tenants] if args.refresh else [])
        for tenant, rapport in zip(tenants, rapports):
            print(f"--- {tenant} ---")
            _afficher(rapport)
        for tenant, rafraichissement in zip(tenants, rafraichissements):
            if rafraichissement["dry_run"]:
                print(f"--- {tenant} (refresh legacy, dry-run) ---")
                print(f"{len(rafraichissement['a_rafraichir'])} manifeste(s) à reconstruire : "
                      + ", ".join(rafraichissement["a_rafraichir"]))
            else:
                print(f"--- {tenant} (refresh legacy) ---")
                print(f"{len(rafraichissement['rafraichis'])} manifeste(s) reconstruit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
