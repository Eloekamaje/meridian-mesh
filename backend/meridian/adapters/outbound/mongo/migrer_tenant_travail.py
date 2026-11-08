"""Migration idempotente du tenant des collections Travail legacy.

    python -m meridian.adapters.outbound.mongo.migrer_tenant_travail \
        --tenant local --dry-run
    python -m meridian.adapters.outbound.mongo.migrer_tenant_travail \
        --tenant local --apply

Estampille ``tenant_id`` sur ``situations``, ``cases`` et ``initiatives``. Les documents
``tenant_id="demo"`` sont ramenés vers ``local`` (alias canonique unique) sauf avec
``--sans-alias``. Le mode dry-run ne modifie rien. L'opération est rejouable : seuls les
documents sans tenant (ou null) sont touchés.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

from meridian.application import pont_travail

__all__ = ["COLLECTIONS", "assurer_index", "estampiller", "main"]

COLLECTIONS = ("situations", "cases", "initiatives")
_SANS_TENANT = {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]}


def _collection(base, nom):
    return getattr(base, nom)


async def estampiller(base, tenant, *, dry_run: bool = True,
                      canoniser_alias: bool = True) -> dict:
    """Compte puis applique (si ``dry_run`` est faux) l'estampillage tenant."""
    tenant = pont_travail.normaliser_tenant(tenant)
    bilan = {"tenant": tenant, "dry_run": bool(dry_run), "collections": {}}
    for nom in COLLECTIONS:
        collection = _collection(base, nom)
        a_estamper = int(await collection.count_documents(_SANS_TENANT))
        alias = int(await collection.count_documents({"tenant_id": "demo"})) \
            if canoniser_alias and tenant == "local" else 0
        ecrits = 0
        if not dry_run:
            if a_estamper:
                resultat = await collection.update_many(
                    _SANS_TENANT, {"$set": {"tenant_id": tenant}})
                ecrits += int(getattr(resultat, "modified_count", 0) or 0)
            if alias:
                resultat = await collection.update_many(
                    {"tenant_id": "demo"}, {"$set": {"tenant_id": tenant}})
                ecrits += int(getattr(resultat, "modified_count", 0) or 0)
        bilan["collections"][nom] = {
            "a_estamper": a_estamper,
            "alias": alias,
            "ecrits": ecrits,
        }
    return bilan


async def assurer_index(base) -> list[str]:
    """Index de lecture des Travaux liés.

    Mongo indexe le chemin positionnel `situations.0` quand il l'accepte ; l'index multikey
    sur `situations` reste le filet de sécurité pour les versions qui le refusent.
    """
    crees: list[str] = []
    for cles, nom in (
        ([("tenant_id", 1), ("situations.0", 1)], "travail_tenant_situation_0"),
        ([("tenant_id", 1), ("situations", 1)], "travail_tenant_situations"),
    ):
        try:
            resultat = await base.cases.create_index(cles, name=nom)
            crees.append(resultat or nom)
        except Exception:  # noqa: BLE001 - un index absent ne bloque pas la migration
            continue
    return crees


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m meridian.adapters.outbound.mongo.migrer_tenant_travail",
        description="Estampille le tenant des collections Travail legacy")
    analyseur.add_argument(
        "--tenant", default=None,
        help="tenant propriétaire (défaut : JUMEAU_LEGACY_TENANT, JUMEAU_TENANT, local)")
    analyseur.add_argument("--mongo-url", default=None, help="URL Mongo (défaut : MONGO_URL)")
    analyseur.add_argument("--db-name", default=None, help="base Mongo (défaut : DB_NAME)")
    analyseur.add_argument("--sans-alias", action="store_true",
                           help="ne pas ramener tenant_id=demo vers local")
    groupe = analyseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", dest="appliquer", action="store_false")
    groupe.add_argument("--apply", dest="appliquer", action="store_true")
    analyseur.set_defaults(appliquer=False)
    args = analyseur.parse_args(argv)

    tenant = (args.tenant or os.environ.get(pont_travail.LEGACY_TENANT_ENV)
              or os.environ.get("JUMEAU_TENANT") or "local")
    url = args.mongo_url or os.environ.get("MONGO_URL")
    base_nom = args.db_name or os.environ.get("DB_NAME") or "meridian_db"
    if not url:
        raise SystemExit("MONGO_URL (ou --mongo-url) requis")
    client = AsyncIOMotorClient(url)

    async def scenario():
        try:
            base = client[base_nom]
            bilan = await estampiller(
                base, tenant, dry_run=not args.appliquer,
                canoniser_alias=not args.sans_alias)
            if args.appliquer:
                await assurer_index(base)
            return bilan
        finally:
            client.close()

    bilan = asyncio.run(scenario())
    mode = "apply" if args.appliquer else "dry-run"
    for nom, compte in bilan["collections"].items():
        print(f"{nom} : {compte['a_estamper']} sans tenant, {compte['alias']} alias demo, "
              f"{compte['ecrits']} écrits ({mode})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
