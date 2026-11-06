#!/usr/bin/env python3
"""Réconciliation globale des liens d'un tenant.

Par défaut : dry-run. `--apply` persiste les propositions éligibles et les cas de
frontière ou de question. Aucun lien n'est confirmé, aucun agent n'est appelé.
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


def _afficher(tenant: str, rapport: dict) -> None:
    mode = "dry-run" if rapport["dry_run"] else "apply"
    print(
        f"--- {tenant} ({mode}) ---\n"
        f"{rapport['twins']} twin(s), {rapport['liens']} lien(s), "
        f"{rapport['propositions']} proposition(s), {rapport['cas']} cas, "
        f"{len(rapport['non_eligibles'])} lien(s) non éligible(s)"
    )
    for diagnostic in rapport["diagnostics"]:
        print(f"  diagnostic : {diagnostic}")


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python scripts/reconcilier-liens.py",
        description="Réconciliation globale des liens entre composants")
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--tenant", default=None, help="limiter à un tenant")
    analyseur.add_argument("--limite", type=_limite, default=None, help="borner le lot traité")
    analyseur.add_argument("--sans-schema", action="store_true",
                           help="ne pas rejouer schema.sql avant la réconciliation")
    groupe = analyseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", dest="appliquer", action="store_false")
    groupe.add_argument("--apply", dest="appliquer", action="store_true")
    analyseur.set_defaults(appliquer=False)
    args = analyseur.parse_args(argv)

    dsn = args.dsn or os.environ.get("JUMEAU_WORKER_PG_DSN") or os.environ.get("JUMEAU_PG_DSN")
    if not dsn:
        raise SystemExit("JUMEAU_PG_DSN (ou --dsn) requis")

    import psycopg

    from meridian.adapters.outbound.postgres import decouverte_naissance
    from meridian.adapters.outbound.postgres import depot as postgres_depot

    with psycopg.connect(dsn, autocommit=True) as conn:
        if not args.sans_schema:
            postgres_depot.appliquer_schema(conn)
        if args.tenant:
            tenants = [args.tenant]
        else:
            tenants = [ligne[0] for ligne in conn.execute(
                "SELECT DISTINCT tenant_id FROM jumeau ORDER BY tenant_id").fetchall()]
        with conn.transaction():
            rapports = [decouverte_naissance.reconcilier(
                conn, tenant, appliquer=args.appliquer, limite=args.limite)
                for tenant in tenants]
        for tenant, rapport in zip(tenants, rapports):
            _afficher(tenant, rapport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
