"""Reconstruit l'index de code des dépôts d'un jumeau au commit ingéré (idempotent).

    python -m jumeau.reindexer --jumeau tbt
"""
import argparse
import os
import subprocess

import psycopg

from meridian.adapters.outbound.connectors import cbm
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.connectors.ingerer import indexer_au_sha


def reindexer(conn, jumeau_id):
    """Réindexe chaque dépôt dont l'index manque, est périmé ou au format ancien ; noms des dépôts refaits."""
    sources = depot.sources_du_jumeau(conn, jumeau_id)
    if not sources:
        raise ValueError(f"aucun dépôt ingéré pour le jumeau {jumeau_id}")
    refaits = []
    for s in sources:
        if (s["index_code"] or "").startswith(cbm.PREFIXE) and cbm.indexe(s):
            continue  # déjà à jour pour ce commit
        copie, projet = indexer_au_sha(jumeau_id, s["emplacement"], s["curseur"])
        depot.maj_index(conn, s["id"], copie, projet)
        cbm.retirer_ancien(s["index_code"], projet)
        refaits.append(s["nom"])
    return refaits


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    a = p.parse_args()
    try:
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            print({"reindexes": reindexer(conn, a.jumeau)})
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"réindexation interrompue : {e}")


if __name__ == "__main__":
    main()
