#!/usr/bin/env python3
"""Backfill additif de `jumeau.perimetre_id` depuis le texte libre `jumeau.perimetre`.

Par défaut : dry-run. `--apply` ne renseigne que les lignes dont `perimetre_id` est NULL ; une
valeur existante n'est jamais écrasée. Le schéma est rejoué avant la migration (idempotent) sauf
avec `--sans-schema`.
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
            f"backfill perimetre_id (dry-run) : {rapport['a_migrer']} twin(s) à migrer, "
            f"{len(rapport['ignores'])} ignoré(s) (périmètre vide), 0 écrit ; "
            "relancer avec --apply"
        )
    else:
        print(
            f"backfill perimetre_id : {rapport['migres']} twin(s) migré(s) "
            f"sur {rapport['a_migrer']} examiné(s), "
            f"{len(rapport['ignores'])} ignoré(s) (périmètre vide)"
        )
    if rapport["valeurs"]:
        print("valeurs calculées :")
        for identifiant, perimetre_id in rapport["valeurs"].items():
            print(f"  {identifiant} -> {perimetre_id}")
    if rapport["ignores"]:
        print("ignorés (périmètre vide) : " + ", ".join(rapport["ignores"]))


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python scripts/backfill-perimetre-id.py",
        description="Backfill idempotent de jumeau.perimetre_id depuis jumeau.perimetre",
    )
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--tenant", default=None, help="limiter à un tenant")
    analyseur.add_argument("--limite", type=_limite, default=None, help="borner le lot traité")
    analyseur.add_argument("--sans-schema", action="store_true",
                           help="ne pas rejouer schema.sql avant la migration")
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
    from meridian.application.backfill_perimetre import migrer

    with psycopg.connect(dsn, autocommit=True) as conn:
        if not args.sans_schema:
            postgres_depot.appliquer_schema(conn)
        if args.appliquer:
            with conn.transaction():
                rapport = migrer(
                    conn, tenant=args.tenant, limite=args.limite, appliquer=True)
        else:
            rapport = migrer(conn, tenant=args.tenant, limite=args.limite)

    _afficher(rapport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
