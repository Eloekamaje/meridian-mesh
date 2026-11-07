"""Migration idempotente du tenant des collections Travail legacy."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aides_pont import CollectionPont

from meridian.adapters.outbound.mongo import migrer_tenant_travail as migration


def _base():
    return SimpleNamespace(
        situations=CollectionPont([{"id": "sit-1"}, {"id": "sit-2", "tenant_id": None},
                                   {"id": "sit-3", "tenant_id": "demo"}]),
        cases=CollectionPont([{"id": "case-1"}, {"id": "case-2", "tenant_id": "assurance"}]),
        initiatives=CollectionPont([{"id": "init-1", "tenant_id": "demo"}]),
    )


def test_dry_run_compte_sans_rien_ecrire():
    base = _base()

    bilan = asyncio.run(migration.estampiller(base, "local", dry_run=True))

    assert bilan["collections"]["situations"] == {
        "a_estamper": 2, "alias": 1, "ecrits": 0}
    assert [doc.get("tenant_id") for doc in base.situations.documents] == [
        None, None, "demo"]


def test_apply_est_idempotent_et_canonise_demo_vers_local():
    base = _base()

    premier = asyncio.run(migration.estampiller(base, "local", dry_run=False))
    second = asyncio.run(migration.estampiller(base, "local", dry_run=False))

    assert premier["collections"]["situations"]["ecrits"] == 3
    assert second["collections"]["situations"]["ecrits"] == 0
    assert {doc.get("tenant_id") for doc in base.situations.documents} == {"local"}
    assert {doc.get("tenant_id") for doc in base.cases.documents} == {"local", "assurance"}
    assert {doc.get("tenant_id") for doc in base.initiatives.documents} == {"local"}


def test_l_index_des_travaux_lies_est_cree_une_seule_fois():
    base = _base()

    asyncio.run(migration.assurer_index(base))
    asyncio.run(migration.assurer_index(base))

    cles = [appel[1] for appel in base.cases.appels if appel[0] == "create_index"]
    assert [("tenant_id", 1), ("situations.0", 1)] in cles
    assert [("tenant_id", 1), ("situations", 1)] in cles
