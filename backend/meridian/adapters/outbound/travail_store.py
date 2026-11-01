"""Fabrique du store Travail : Mongo par défaut, Postgres quand `JUMEAU_TRAVAIL_STORE=postgres`.

Le chemin d'écriture reste Mongo dans ce lot : seul le read model d'Actualités change de
source. Le tenant Postgres suit `JUMEAU_TENANT` (défaut `local`, comme le reste de l'API).
"""
from __future__ import annotations

import os

from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
from meridian.adapters.outbound.postgres.travail_depot import TravailDepot as TravailPostgres

STORE_ENV = "JUMEAU_TRAVAIL_STORE"
TENANT_ENV = "JUMEAU_TENANT"
DEFAUT = "mongo"


def travail_store(db, dsn: str | None = None, tenant: str | None = None):
    choix = str(os.environ.get(STORE_ENV) or DEFAUT).strip().lower()
    if choix == "mongo":
        return TravailMongo(db.cases)
    if choix == "postgres":
        dsn = dsn or os.environ.get("JUMEAU_PG_DSN")
        if not dsn:
            raise RuntimeError(
                f"{STORE_ENV}=postgres mais JUMEAU_PG_DSN (ou le DSN fourni) est absent")
        return TravailPostgres(dsn=dsn,
                               tenant_id=tenant or os.environ.get(TENANT_ENV) or "local")
    raise RuntimeError(f"{STORE_ENV} doit valoir mongo ou postgres (reçu {choix!r})")
