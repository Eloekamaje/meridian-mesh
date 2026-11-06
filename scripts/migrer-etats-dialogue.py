#!/usr/bin/env python3
"""Backfill additif de `etat_tour` dans les Travaux Mongo.

Par défaut : dry-run. `--apply` écrit uniquement `etat_tour` ; la conversation,
les preuves, les Claims et les autres champs ne sont jamais modifiés.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from dotenv import load_dotenv


async def _compter(collection, filtre):
    return await collection.count_documents(filtre)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", help="limiter à un tenant")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--apply", action="store_true", help="écrire etat_tour")
    parser.add_argument("--verifier", action="store_true", help="ne compter que l'état")
    args = parser.parse_args()
    load_dotenv(RACINE / "backend" / ".env")
    url, base = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url or not base:
        raise SystemExit("MONGO_URL et DB_NAME requis")
    from motor.motor_asyncio import AsyncIOMotorClient
    from meridian.application.tour_dialogue import EtatTour

    client = AsyncIOMotorClient(url)
    try:
        collection = client[base].cases
        filtre = {"etat_tour": {"$exists": False}}
        if args.tenant:
            filtre["tenant_id"] = args.tenant
        if args.verifier:
            total = await _compter(collection, filtre)
            print(f"{total} Travail(s) sans etat_tour")
            return
        curseur = collection.find(filtre, {"_id": 0}).limit(max(1, int(args.limit)))
        lignes = await curseur.to_list(None)
        if not args.apply:
            print(f"dry-run : {len(lignes)} Travail(s) à migrer (--apply pour écrire)")
            return
        ecrits = 0
        for case in lignes:
            etat = EtatTour.depuis_case(case)
            resultat = await collection.update_one(
                {"id": case["id"], "etat_tour": {"$exists": False}},
                {"$set": {"etat_tour": etat.as_dict()}},
            )
            ecrits += int(getattr(resultat, "modified_count", 0) or 0)
        print(f"{ecrits} Travail(s) migré(s)")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
