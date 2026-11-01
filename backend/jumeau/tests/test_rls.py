"""RLS tenant : SQL statique, contexte transactionnel, activation opt-in et vérification."""
import re
from pathlib import Path

import pytest

from jumeau import rls
from jumeau.tests.conftest import besoin_pg

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Conn:
    def __init__(self):
        self.appels = []
        self.transactions = 0

    def execute(self, requete, params=()):
        self.appels.append((requete, params))
        return self

    def transaction(self):
        self.transactions += 1
        return _Transaction()


class _ConnexionCLI:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_activation_couvre_les_tables_avec_tenant_et_force_la_policy():
    sql = rls.sql_activation()
    for table in rls.TOUTES_LES_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql
        assert f"CREATE POLICY {rls.POLITIQUE} ON {table}" in sql
    assert "current_setting('meridian.tenant_id', true)" in sql
    assert "WITH CHECK" in sql


def test_activation_est_idempotente_et_drop_avant_create():
    sql = rls.sql_activation()
    for table in rls.TOUTES_LES_TABLES:
        drop = sql.index(f"DROP POLICY IF EXISTS {rls.POLITIQUE} ON {table};")
        create = sql.index(f"CREATE POLICY {rls.POLITIQUE} ON {table}")
        assert drop < create
    assert rls.sql_activation() == sql

    conn = _Conn()
    rls.activer(conn)
    assert conn.transactions == 1
    for table in rls.TOUTES_LES_TABLES:
        assert (f"DROP POLICY IF EXISTS {rls.POLITIQUE} ON {table}", ()) in conn.appels
        assert any(requete.startswith(f"CREATE POLICY {rls.POLITIQUE} ON {table}") for requete, _ in conn.appels)


def test_toutes_les_tables_avec_tenant_sont_couvertes():
    attendues = {
        "jumeau", "source", "preuve", "claim", "revue", "contradiction", "ancre", "consigne",
        "interface_contract", "interface_operation", "interface_binding", "interface_assertion",
        "discovery_run", "identity_decision", "objet_entreprise", "outil_audit",
        "valeur", "memoire_durable", "prediction_calibration",
        "execution_run", "execution_evenement", "execution_outbox", "execution_timer",
        "execution_effet", "execution_approbation", "execution_etape",
        "source_schedule", "ingestion_run",
    }
    assert attendues == set(rls.TABLES)
    assert set(rls.TABLES) | set(rls.TABLES_DERIVEES) == set(rls.TOUTES_LES_TABLES)


def test_schema_sql_et_rls_tables_restent_alignes():
    corps = dict(re.findall(
        r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SCHEMA.read_text(), re.S))
    avec_tenant = {nom for nom, definition in corps.items() if "tenant_id" in definition}
    assert avec_tenant == set(rls.TABLES)
    assert set(rls.TABLES_DERIVEES) <= set(corps)
    assert all("tenant_id" not in corps[nom] for nom in rls.TABLES_DERIVEES)


def test_les_tables_derivees_sont_filtrees_par_leur_parent():
    sql = rls.sql_activation()
    for table, (parent, colonne) in rls.TABLES_DERIVEES.items():
        assert (
            f"CREATE POLICY {rls.POLITIQUE} ON {table} USING ("
            f"EXISTS (SELECT 1 FROM {parent} p WHERE p.id = {table}.{colonne} "
            f"AND p.tenant_id = current_setting('meridian.tenant_id', true)))"
        ) in sql


def test_contexte_pose_et_retire_le_tenant_dans_une_transaction():
    conn = _Conn()
    with rls.contexte_tenant(conn, "Banque") as tenant:
        assert tenant == "banque"
    assert conn.transactions == 1
    assert conn.appels == [
        ("SELECT set_config('meridian.tenant_id', %s, true)", ("banque",)),
        ("SELECT set_config('meridian.tenant_id', '', true)", ()),
    ]


def test_contexte_refuse_un_tenant_invalide_avant_la_base():
    conn = _Conn()
    with pytest.raises(Exception):
        with rls.contexte_tenant(conn, "Banque Client"):
            pass
    assert conn.appels == []
    assert conn.transactions == 0


def test_contexte_session_ne_prend_pas_de_transaction_et_est_retire():
    conn = _Conn()
    with rls.contexte_tenant_session(conn, "Banque"):
        pass
    assert conn.transactions == 0
    assert conn.appels == [
        ("SELECT set_config(%s, %s, false)", ("meridian.tenant_id", "banque")),
        ("SELECT set_config(%s, '', false)", ("meridian.tenant_id",)),
    ]


def test_activation_est_opt_in():
    assert rls.est_actif({}) is False
    assert rls.est_actif({"JUMEAU_RLS": "0"}) is False
    assert rls.est_actif({"JUMEAU_RLS": "1"}) is True
    assert rls.est_actif({"JUMEAU_RLS": "true"}) is True


def test_mode_worker_distingue_bypass_et_contexte():
    assert rls.mode_worker({"contourne_rls": True}) == rls.MODE_WORKER_BYPASS
    assert rls.mode_worker({"contourne_rls": False}) == rls.MODE_WORKER_CONTEXTE


class _Result:
    def __init__(self, ligne):
        self.ligne = ligne

    def fetchone(self):
        return self.ligne


def test_configurer_worker_refuse_le_balayage_sans_tenant_ni_bypass(monkeypatch):
    monkeypatch.setenv("JUMEAU_RLS", "1")

    class _ConnRole:
        def __init__(self, superuser=False, bypass=False, rls=True):
            self.superuser, self.bypass, self.rls = superuser, bypass, rls

        def execute(self, requete, params=()):
            if requete == "SELECT current_user":
                return _Result(("meridian_app",))
            if "pg_roles" in requete:
                return _Result((self.superuser, self.bypass))
            if "relrowsecurity" in requete:
                return _Result((True, self.rls, self.rls))
            raise AssertionError(requete)

    with pytest.raises(rls.ConfigurationWorker, match="JUMEAU_WORKER_TENANTS"):
        rls.configurer_worker(_ConnRole(), tenants=())

    configuration = rls.configurer_worker(_ConnRole(), tenants=("Banque",))
    assert configuration["mode"] == rls.MODE_WORKER_CONTEXTE
    assert configuration["tenants"] == ("banque",)

    with pytest.raises(rls.ConfigurationWorker, match="exactement un tenant"):
        rls.configurer_worker(_ConnRole(), tenants=("banque", "autre"), multi=False)

    bypass = rls.configurer_worker(_ConnRole(bypass=True), tenants=())
    assert bypass["mode"] == rls.MODE_WORKER_BYPASS

    with pytest.raises(rls.ConfigurationWorker, match="policies RLS actives"):
        rls.configurer_worker(_ConnRole(rls=False), tenants=("banque",))

    with pytest.raises(rls.ConfigurationWorker, match="incompatible"):
        rls.configurer_worker(_ConnRole(bypass=True), tenants=("banque",))


def test_configurer_worker_garde_le_mode_non_rls_inchange(monkeypatch):
    monkeypatch.setenv("JUMEAU_RLS", "0")
    monkeypatch.setattr(rls, "role_courant", lambda conn: {
        "nom": "meridian", "superuser": False, "bypassrls": False, "contourne_rls": False,
    })
    monkeypatch.setattr(rls, "policies_actives", lambda conn: False)

    configuration = rls.configurer_worker(object())

    assert configuration["rls"] is False
    assert configuration["mode"] == rls.MODE_WORKER_CONTEXTE
    assert configuration["tenants"] == ()


@besoin_pg
def test_integration_policies_actives_suit_l_activation_par_table(conn):
    assert rls.policies_actives(conn, tables=("objet_entreprise",)) is False
    rls.activer(conn, tables=("objet_entreprise",))
    assert rls.policies_actives(conn, tables=("objet_entreprise",)) is True
    assert rls.policies_actives(conn, tables=("jumeau",)) is False
    assert rls.policies_actives(conn, tables=("objet_entreprise",), completes=True) is True
    assert rls.policies_actives(
        conn, tables=("objet_entreprise", "jumeau"), completes=True) is False
    rls.desactiver(conn, tables=("objet_entreprise",))
    assert rls.policies_actives(conn, tables=("objet_entreprise",)) is False


def test_tables_execution_memoire_ingestion_et_valeur_couvertes():
    attendues = {
        "memoire_durable", "valeur", "prediction_calibration",
        "execution_run", "execution_evenement", "execution_outbox", "execution_timer",
        "execution_effet", "execution_approbation", "execution_etape",
        "source_schedule", "ingestion_run",
    }
    assert attendues <= set(rls.TABLES)
    sql = rls.sql_activation()
    for table in attendues:
        assert f"CREATE POLICY {rls.POLITIQUE} ON {table}" in sql


def test_selection_refuse_une_table_inconnue():
    with pytest.raises(ValueError, match="inconnues"):
        rls.sql_activation(("objet_entreprise", "table_qui_n_existe_pas"))


def test_cli_refuse_un_role_superuser_ou_bypassrls(monkeypatch, capsys):
    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *_, **__: _ConnexionCLI())
    monkeypatch.setattr(rls, "role_courant", lambda conn: {
        "nom": "meridian", "superuser": True, "bypassrls": True, "contourne_rls": True,
    })

    assert rls.main(["--activer", "--dsn", "postgresql://test/test"]) == 2
    assert "REFUS" in capsys.readouterr().err


@besoin_pg
def test_integration_activation_verification_et_contexte(conn):
    rls.activer(conn)
    rls.activer(conn)  # idempotent : rejouer l'activation ne casse rien

    rapport = rls.verifier(conn)
    assert rapport["schema"] == conn.execute("SELECT current_schema()").fetchone()[0]
    assert {resultat["table"] for resultat in rapport["tables"]} == set(rls.TOUTES_LES_TABLES)
    assert rapport["tables_ok"], rapport
    role = rls.role_courant(conn)
    assert rapport["role_protege"] is (not role["contourne_rls"])
    assert rapport["ok"] is (rapport["tables_ok"] and rapport["role_protege"])

    # Même sur une connexion autocommit, le helper ouvre une transaction : le setting est visible
    # pendant le bloc puis retiré à la sortie.
    with rls.contexte_tenant(conn, "Banque"):
        assert conn.execute("SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "banque"
    assert conn.execute("SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] in (None, "")

    # Une erreur SQL dans le corps ne doit pas être masquée par le reset du setting.
    import psycopg

    with pytest.raises(psycopg.errors.DivisionByZero):
        with rls.contexte_tenant(conn, "Banque"):
            conn.execute("SELECT 1/0")
    assert conn.execute("SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] in (None, "")


@besoin_pg
def test_integration_contexte_session_survit_aux_transactions(conn):
    with rls.contexte_tenant_session(conn, "Banque"):
        assert conn.execute(
            "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "banque"
        with conn.transaction():
            assert conn.execute(
                "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "banque"
        assert conn.execute(
            "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] == "banque"
    assert conn.execute(
        "SELECT current_setting('meridian.tenant_id', true)").fetchone()[0] in (None, "")


@besoin_pg
def test_integration_la_policy_refuse_les_autres_tenants(conn):
    """Vérifie l'application réelle via un rôle existant non-superuser (`pg_monitor`).

    Aucun rôle global n'est créé : le test est ignoré si le DSN n'est pas superuser (impossible de
    faire `SET ROLE`) ou si `pg_monitor` n'est pas disponible/non contournant.
    """
    role = rls.role_courant(conn)
    if not role["superuser"]:
        pytest.skip("SET ROLE de vérification nécessite un rôle superuser de test")
    surveillant = conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = 'pg_monitor' AND NOT rolsuper AND NOT rolbypassrls"
    ).fetchone()
    if surveillant is None:
        pytest.skip("rôle pg_monitor indisponible")

    rls.activer(conn, tables=("jumeau", "objet_entreprise"))
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES "
        "('a', 'tenant-a', 'A', 'equipe'), ('b', 'tenant-b', 'B', 'equipe')"
    )
    conn.execute(
        "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode) VALUES "
        "('oa', 'tenant-a', 'connaissance', 'X', 'DECLARED'), "
        "('ob', 'tenant-b', 'connaissance', 'X', 'DECLARED')"
    )
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO pg_monitor")
    conn.execute("GRANT SELECT ON jumeau, objet_entreprise TO pg_monitor")

    with conn.transaction():
        conn.execute("SET LOCAL ROLE pg_monitor")
        with rls.contexte_tenant(conn, "tenant-a"):
            assert conn.execute("SELECT id FROM jumeau ORDER BY id").fetchall() == [("a",)]
            assert conn.execute("SELECT id FROM objet_entreprise ORDER BY id").fetchall() == [("oa",)]
        with rls.contexte_tenant(conn, "tenant-b"):
            assert conn.execute("SELECT id FROM objet_entreprise ORDER BY id").fetchall() == [("ob",)]
        assert conn.execute("SELECT count(*) FROM objet_entreprise").fetchone()[0] == 0

    assert conn.execute("SELECT current_user").fetchone()[0] == role["nom"]


@besoin_pg
def test_integration_activation_par_sous_ensemble_puis_desactivation(conn):
    rls.activer(conn, tables=("objet_entreprise",))
    assert rls.verifier(conn, tables=("objet_entreprise",))["tables_ok"]

    autre = rls.verifier(conn, tables=("jumeau",))["tables"][0]
    assert autre["existe"] is True and autre["rls"] is False

    rls.desactiver(conn, tables=("objet_entreprise",))
    apres = rls.verifier(conn, tables=("objet_entreprise",))["tables"][0]
    assert apres["rls"] is False and apres["politique"] is False
