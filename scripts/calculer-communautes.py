#!/usr/bin/env python3
"""Calcule les communautés du graphe et leurs rapports précompilés."""
import argparse
import asyncio
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="local")
    args = parser.parse_args()
    load_dotenv(RACINE / "backend" / ".env")
    import psycopg
    from meridian.adapters.outbound.neo4j import graph_store
    from meridian.adapters.outbound.postgres import community_store
    from meridian.adapters.outbound.llm import rapport_communaute
    from meridian.application import communautes

    dsn = os.environ["JUMEAU_PG_DSN"]
    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT id, domaine FROM jumeau WHERE tenant_id = %s", (args.tenant,)).fetchall()
    domaines = {str(i): str(d or "") for i, d in rows}
    contexte = graph_store.ouvrir()
    try:
        niveaux = communautes.construire_hierarchique(
            contexte["store"], args.tenant, list(domaines), domaines=domaines)
    finally:
        contexte["fermer"]()
    groupes = []
    for niveau in niveaux:
        for groupe in niveau["communautes"]:
            groupe["id"] = f"{groupe['fingerprint']}-l{niveau['niveau']}"
            groupe["level"] = niveau["niveau"]
            groupe["rapport"] = communautes.rapport(groupe)
            if rapport_communaute.disponible():
                synthese = await rapport_communaute.resumer(groupe["rapport"])
                if synthese:
                    groupe["rapport"] = synthese
            groupes.append(groupe)
    total = community_store.remplacer(args.tenant, groupes)
    print(f"{total} communauté(s) calculée(s)")


if __name__ == "__main__":
    asyncio.run(main())
