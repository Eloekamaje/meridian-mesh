"""RLS tenant : SQL statique, contexte transactionnel et activation opt-in."""
import pytest

from jumeau import rls


class _Conn:
    def __init__(self):
        self.appels = []

    def execute(self, requete, params=()):
        self.appels.append((requete, params))
        return self


def test_activation_couvre_les_tables_avec_tenant_et_force_la_policy():
    sql = rls.sql_activation()
    for table in rls.TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql
        assert f"CREATE POLICY {rls.POLITIQUE} ON {table}" in sql
    assert "current_setting('meridian.tenant_id', true)" in sql
    assert "WITH CHECK" in sql


def test_contexte_pose_et_retire_le_tenant():
    conn = _Conn()
    with rls.contexte_tenant(conn, "Banque") as tenant:
        assert tenant == "banque"
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


def test_activation_est_opt_in():
    assert rls.est_actif({}) is False
    assert rls.est_actif({"JUMEAU_RLS": "0"}) is False
    assert rls.est_actif({"JUMEAU_RLS": "1"}) is True
    assert rls.est_actif({"JUMEAU_RLS": "true"}) is True
