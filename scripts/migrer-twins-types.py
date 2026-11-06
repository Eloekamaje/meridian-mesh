#!/usr/bin/env python3
"""Backfill additif des Twins historiques : `type = APPLICATION`, `application_id = id`.

Par défaut : dry-run. `--apply` ne renseigne que `application_id` des lignes APPLICATION qui n'en ont
pas encore ; aucun autre type n'est modifié, aucune ligne n'est supprimée. Le schéma est rejoué avant
la migration (idempotent) sauf avec `--sans-schema`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))


def _texte(valeur, champ: str) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ValueError(f"{champ} obligatoire")
    return texte


def _limite(valeur) -> int:
    if isinstance(valeur, bool):
        raise ValueError("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise ValueError("limite doit être un entier positif") from exc
    if borne < 1:
        raise ValueError("limite doit être un entier positif")
    return borne


def _lignes_a_migrer(conn, tenant=None, limite=None) -> list[tuple[str, str]]:
    conditions = ["application_id IS NULL", "type = 'APPLICATION'"]
    parametres: list[object] = []
    if tenant is not None:
        conditions.append("tenant_id = %s")
        parametres.append(_texte(tenant, "tenant"))
    requete = (
        "SELECT id, tenant_id FROM jumeau WHERE " + " AND ".join(conditions)
        + " ORDER BY tenant_id, id"
    )
    if limite is not None:
        requete += " LIMIT %s"
        parametres.append(_limite(limite))
    return [(ligne[0], ligne[1]) for ligne in conn.execute(requete, parametres).fetchall()]


def migrer(conn, tenant=None, limite=None, *, appliquer: bool = False) -> dict:
    """Compte ou applique le backfill ; deux appels de dry-run rendent le même rapport."""
    if not isinstance(appliquer, bool):
        raise TypeError("appliquer doit être un booléen")
    lignes = _lignes_a_migrer(conn, tenant=tenant, limite=limite)
    rapport = {
        "dry_run": not appliquer,
        "a_migrer": len(lignes),
        "migres": 0,
        "ids": [identifiant for identifiant, _ in lignes],
    }
    if not appliquer:
        return rapport
    for identifiant, _ in lignes:
        resultat = conn.execute(
            "UPDATE jumeau SET application_id = %s, type = 'APPLICATION' "
            "WHERE id = %s AND type = 'APPLICATION' AND application_id IS NULL",
            (identifiant, identifiant),
        )
        rapport["migres"] += resultat.rowcount
    return rapport


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python scripts/migrer-twins-types.py",
        description="Backfill idempotent des Twins historiques (type APPLICATION, application_id = id)",
    )
    analyseur.add_argument("--dsn", default=None,
                           help="DSN Postgres (défaut : JUMEAU_WORKER_PG_DSN puis JUMEAU_PG_DSN)")
    analyseur.add_argument("--tenant", default=None, help="limiter à un tenant")
    analyseur.add_argument("--limite", type=int, default=None, help="borner le lot traité")
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

    with psycopg.connect(dsn, autocommit=True) as conn:
        if not args.sans_schema:
            postgres_depot.appliquer_schema(conn)
        if args.appliquer:
            with conn.transaction():
                rapport = migrer(
                    conn, tenant=args.tenant, limite=args.limite, appliquer=True)
        else:
            rapport = migrer(conn, tenant=args.tenant, limite=args.limite)

    if rapport["dry_run"]:
        print(
            f"migration twins types (dry-run) : {rapport['a_migrer']} twin(s) à migrer, "
            "0 écrit ; relancer avec --apply"
        )
    else:
        print(
            f"migration twins types : {rapport['migres']} twin(s) migré(s) "
            f"sur {rapport['a_migrer']} examiné(s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
