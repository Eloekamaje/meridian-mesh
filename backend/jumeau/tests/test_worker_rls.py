"""Configuration RLS des workers : DSN dédié, mode de rôle et passe par tenant."""
import asyncio
import os

import pytest

from jumeau.tests.conftest import besoin_pg
from meridian.adapters.inbound.worker.config import (
    DSN_ENV,
    DSN_WORKER_ENV,
    dsn_avec_tenant,
    dsn_worker,
    normaliser_tenants,
    option_connexion_tenant,
    tenants_worker,
)


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _ConnTenant:
    """Connexion factice qui retient le tenant posé par ``set_config``."""

    def __init__(self):
        self.tenant = None
        self.appels = []
        self.transactions = 0

    def transaction(self):
        self.transactions += 1
        return _Transaction()

    def execute(self, requete, params=()):
        self.appels.append((requete, params))
        if "set_config('meridian.tenant_id'" in requete:
            self.tenant = params[0] if params and params[0] else None
        return self


def test_dsn_worker_prefere_le_dsn_dedie_puis_replie():
    assert dsn_worker({}) is None
    assert dsn_worker({DSN_ENV: "postgresql://app/db"}) == "postgresql://app/db"
    assert dsn_worker({DSN_ENV: "postgresql://app/db", DSN_WORKER_ENV: "postgresql://worker/db"}) \
        == "postgresql://worker/db"
    assert dsn_worker({DSN_WORKER_ENV: "  ", DSN_ENV: " postgresql://app/db "}) \
        == "postgresql://app/db"


def test_tenants_worker_valide_deduplique_et_refuse_les_slugs_invalides():
    assert tenants_worker({"JUMEAU_WORKER_TENANTS": "Banque, tenant-b,banque"}) \
        == ("banque", "tenant-b")
    assert tenants_worker({"JUMEAU_WORKER_TENANT": "Banque"}) == ("banque",)
    assert tenants_worker({"JUMEAU_WORKER_TENANTS": "banque",
                           "JUMEAU_WORKER_TENANT": "autre"}) == ("banque",)
    assert normaliser_tenants(None) == ()
    with pytest.raises(ValueError):
        normaliser_tenants("banque client")


def test_option_connexion_tenant_est_validee_avant_interpolation():
    assert option_connexion_tenant("Banque") == "-c meridian.tenant_id=banque"
    assert option_connexion_tenant(None) is None
    with pytest.raises(ValueError):
        option_connexion_tenant("banque'; DROP TABLE jumeau; --")


def test_dsn_avec_tenant_ajoute_l_option_de_session():
    from psycopg.conninfo import conninfo_to_dict

    dsn = dsn_avec_tenant("postgresql://worker:secret@db:5432/meridian", "Banque")
    parametres = conninfo_to_dict(dsn)

    assert parametres["host"] == "db"
    assert parametres["dbname"] == "meridian"
    assert parametres["options"] == "-c meridian.tenant_id=banque"
    assert dsn_avec_tenant("postgresql://worker/db", None) == "postgresql://worker/db"

    fusionne = conninfo_to_dict(dsn_avec_tenant(
        "postgresql://worker/db?options=-c%20search_path%3Dmeridian", "banque"))
    assert fusionne["options"] == "-c search_path=meridian -c meridian.tenant_id=banque"


def test_source_worker_pose_le_contexte_pour_chaque_tenant(monkeypatch):
    from jumeau import source_worker

    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://base/db")
    vus = []

    def enregistrer(nom):
        def _appel(conn, *_args, **_kwargs):
            vus.append((nom, conn.tenant))
            return None if nom == "reclamer_run" else []
        return _appel

    for nom in ("reprendre_baux_expires", "planifier_sources", "enfiler_du", "reclamer_run"):
        monkeypatch.setattr(source_worker.runtime, nom, enregistrer(nom))

    conn = _ConnTenant()
    traites = asyncio.run(source_worker.boucle(
        conn, object(), "postgresql://worker/db",
        worker_id="worker-test", intervalle=1, bail=10, limite=10,
        une_passe=True, arret=asyncio.Event(), tenants=("banque", "autre")))

    assert traites == 0
    for nom in ("reprendre_baux_expires", "planifier_sources", "enfiler_du", "reclamer_run"):
        assert [tenant for appel, tenant in vus if appel == nom] == ["banque", "autre"]
    assert conn.tenant is None
    assert conn.transactions == 8  # quatre transactions courtes par tenant
    assert os.environ["JUMEAU_PG_DSN"] == "postgresql://base/db"


def test_source_worker_sans_tenant_garde_le_balayage_global(monkeypatch):
    from jumeau import source_worker

    vus = []

    def enregistrer(nom):
        def _appel(conn, *_args, **_kwargs):
            vus.append((nom, conn.tenant))
            return None if nom == "reclamer_run" else []
        return _appel

    for nom in ("reprendre_baux_expires", "planifier_sources", "enfiler_du", "reclamer_run"):
        monkeypatch.setattr(source_worker.runtime, nom, enregistrer(nom))

    conn = _ConnTenant()
    assert asyncio.run(source_worker.boucle(
        conn, object(), "postgresql://worker/db",
        worker_id="worker-test", intervalle=1, bail=10, limite=10,
        une_passe=True, arret=asyncio.Event())) == 0
    assert {tenant for _nom, tenant in vus} == {None}
    assert conn.transactions == 0


@besoin_pg
def test_connexion_worker_pose_le_tenant_au_niveau_session():
    import psycopg

    from jumeau.execution import worker as execution_worker

    with execution_worker._connexion(os.environ["JUMEAU_PG_DSN"], "Banque") as conn:
        assert conn.execute(
            "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "banque"
    with execution_worker._connexion(os.environ["JUMEAU_PG_DSN"]) as conn:
        assert conn.execute(
            "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] in (None, "")
    with psycopg.connect(dsn_avec_tenant(os.environ["JUMEAU_PG_DSN"], "Autre")) as conn:
        assert conn.execute(
            "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "autre"
