"""Fabrique du store Travail : Mongo par défaut, Postgres quand `JUMEAU_TRAVAIL_STORE=postgres`.

La lecture suit `JUMEAU_TRAVAIL_STORE` ; l'écriture bascule avec
`JUMEAU_TRAVAIL_WRITE=postgres` (voir `mongo/travail_proxy.py`). Le tenant Postgres
suit le contexte de requête, puis `JUMEAU_TENANT` (défaut `local`).
"""
from __future__ import annotations

import os

from meridian.adapters.outbound.mongo.travail_depot import TravailDepot as TravailMongo
from meridian.application import tenant_context
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
        return TravailPostgres(
            dsn=dsn,
            tenant_id=(tenant or tenant_context.courant_explicite()
                       or os.environ.get(TENANT_ENV) or "local"))
    raise RuntimeError(f"{STORE_ENV} doit valoir mongo ou postgres (reçu {choix!r})")
