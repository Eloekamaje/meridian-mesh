"""Rétention : politiques explicites, rapport borné au tenant et purge à blanc."""
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from meridian.adapters.outbound.postgres import retention
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
MAINTENANT = datetime.now(timezone.utc).replace(microsecond=0)

SCHEMA = """
CREATE TABLE memoire_durable (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    classe TEXT NOT NULL,
    cree_le TEXT,
    expire_le TEXT
);
CREATE TABLE claim (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    enregistre_le TEXT
);
CREATE TABLE preuve (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    observee_le TEXT
);
CREATE TABLE objet_entreprise (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    type TEXT NOT NULL,
    cree_le TEXT,
    PRIMARY KEY (tenant_id, id)
);
CREATE TABLE prediction_calibration (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    cree_le TEXT,
    outcome INTEGER,
    resolue_le TEXT,
    PRIMARY KEY (tenant_id, id)
);
"""


def _iso(instant):
    return instant.astimezone(timezone.utc).isoformat()


def _connexion():
    connexion = sqlite3.connect(":memory:")
    connexion.executescript(SCHEMA)
    return connexion


def _memoire(conn, identifiant, tenant=TENANT, classe="contexte", cree=None, expire=None):
    conn.execute(
        "INSERT INTO memoire_durable (id, tenant_id, classe, cree_le, expire_le) "
        "VALUES (?, ?, ?, ?, ?)",
        (identifiant, tenant, classe, _iso(cree), _iso(expire)),
    )


def _objet(conn, identifiant, type_objet, tenant=TENANT, cree=None):
    conn.execute(
        "INSERT INTO objet_entreprise (id, tenant_id, type, cree_le) VALUES (?, ?, ?, ?)",
        (identifiant, tenant, type_objet, _iso(cree)),
    )


def _prediction(conn, identifiant, tenant=TENANT, cree=None, outcome=None):
    conn.execute(
        "INSERT INTO prediction_calibration (id, tenant_id, cree_le, outcome, resolue_le) "
        "VALUES (?, ?, ?, ?, ?)",
        (identifiant, tenant, _iso(cree), outcome, _iso(cree) if outcome is not None else None),
    )


def _peupler(conn):
    _memoire(conn, "session-echue", classe="session", cree=MAINTENANT - timedelta(days=2),
             expire=MAINTENANT - timedelta(days=1))
    _memoire(conn, "session-age", classe="session", cree=MAINTENANT - timedelta(days=31),
             expire=MAINTENANT + timedelta(days=200))
    _memoire(conn, "session-future", classe="session", cree=MAINTENANT - timedelta(days=1),
             expire=MAINTENANT + timedelta(days=4))
    _memoire(conn, "memoire-echue", cree=MAINTENANT - timedelta(days=31),
             expire=MAINTENANT - timedelta(days=1))
    _memoire(conn, "memoire-future", classe="decision", cree=MAINTENANT - timedelta(days=500),
             expire=MAINTENANT + timedelta(days=200))
    conn.execute("INSERT INTO claim (id, tenant_id, enregistre_le) VALUES (1, ?, ?)",
                 (TENANT, _iso(MAINTENANT - timedelta(days=4000))))
    conn.execute("INSERT INTO preuve (id, tenant_id, observee_le) VALUES (1, ?, ?)",
                 (TENANT, _iso(MAINTENANT - timedelta(days=4000))))
    _objet(conn, "learning-1", "LEARNING", cree=MAINTENANT - timedelta(days=2000))
    _objet(conn, "outcome-1", "OUTCOME", cree=MAINTENANT - timedelta(days=2000))
    _prediction(conn, "pred-resolue", cree=MAINTENANT - timedelta(days=400), outcome=1)
    _prediction(conn, "pred-non-resolue", cree=MAINTENANT - timedelta(days=400))
    _prediction(conn, "pred-recente", cree=MAINTENANT - timedelta(days=31), outcome=0)

    _memoire(conn, "session-autre", tenant=AUTRE_TENANT, classe="session",
             cree=MAINTENANT - timedelta(days=2), expire=MAINTENANT - timedelta(days=1))
    _memoire(conn, "memoire-autre", tenant=AUTRE_TENANT, cree=MAINTENANT - timedelta(days=31),
             expire=MAINTENANT - timedelta(days=1))
    conn.execute("INSERT INTO claim (id, tenant_id, enregistre_le) VALUES (2, ?, ?)",
                 (AUTRE_TENANT, _iso(MAINTENANT - timedelta(days=4000))))
    _prediction(conn, "pred-autre", tenant=AUTRE_TENANT,
                cree=MAINTENANT - timedelta(days=400), outcome=1)
    conn.commit()


def _compter(conn, table, tenant=None):
    if tenant is None:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (tenant,)).fetchone()[0]


def test_politiques_explicites_export_et_as_dict():
    """Les durées, l'immuabilité et la suppression sont déclarées sans ambiguïté."""
    politiques = retention.POLITIQUES
    assert set(politiques) == {
        "memoire_durable", "session", "claim", "preuve", "learning", "outcome", "prediction",
    }
    assert politiques["session"].jours < politiques["memoire_durable"].jours
    assert politiques["claim"].immuable is True
    assert politiques["preuve"].immuable is True
    assert politiques["claim"].supprimable is False
    assert politiques["preuve"].supprimable is False
    assert politiques["learning"].jours > politiques["memoire_durable"].jours
    assert politiques["outcome"].jours > politiques["memoire_durable"].jours
    assert politiques["prediction"].jours == 365
    assert politiques["claim"]["immutable"] is True
    assert politiques["claim"]["retention_jours"] == politiques["claim"].jours

    export = retention.exporter_politique()
    assert set(export) == set(politiques)
    assert export["prediction"]["jours"] == 365
    assert export["preuve"]["immutable"] is True
    assert retention.as_dict()["session"]["jours"] == 7
    assert retention.as_dict("claim")["supprimable"] is False
    assert retention.as_dict(politiques["outcome"])["type_objet"] == "OUTCOME"

    with pytest.raises(KeyError):
        politiques["claim"]["inconnu"]
    with pytest.raises(TypeError):
        retention.as_dict(42)


def test_rapport_compte_expirees_immuables_et_prochaine_expiration():
    """Le rapport distingue les classes, les immuables et la prochaine échéance."""
    conn = _connexion()
    _peupler(conn)
    resultat = retention.rapport(conn, TENANT)

    assert resultat["tenant_id"] == TENANT
    assert resultat["classes"] is resultat["par_classe"]
    assert resultat["session"]["total"] == 3
    assert resultat["session"]["expirees"] == 2
    assert resultat["session"]["supprimables"] == 2
    assert resultat["session"]["prochaine_expiration"] == _iso(
        MAINTENANT + timedelta(days=4))
    assert resultat["memoire_durable"]["total"] == 2
    assert resultat["memoire_durable"]["expirees"] == 1
    assert resultat["claim"]["total"] == 1
    assert resultat["claim"]["immuables"] == 1
    assert resultat["claim"]["supprimables"] == 0
    assert resultat["preuve"]["immuables"] == 1
    assert resultat["learning"]["expirees"] == 1
    assert resultat["outcome"]["expirees"] == 1
    assert resultat["prediction"]["total"] == 3
    assert resultat["prediction"]["expirees"] == 2
    assert resultat["prediction"]["supprimables"] == 1
    assert resultat["total"] == 12
    assert resultat["expirees"] == 9
    assert resultat["supprimables"] == 4
    assert resultat["immuables"] == 2
    assert resultat["immuables_ignorees"] == 5
    assert resultat["prochaine_expiration"] == _iso(MAINTENANT + timedelta(days=4))
    assert resultat["limites"] == []
    assert resultat["complet"] is True


def test_rapport_tolere_les_tables_absentes_et_les_colonnes_manquantes():
    """Une table absente rend zéro et une limite, sans masquer les autres classes."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE memoire_durable (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, expire_le TEXT)"
    )
    conn.execute(
        "INSERT INTO memoire_durable (id, tenant_id, expire_le) VALUES (?, ?, ?)",
        ("ancienne", TENANT, _iso(MAINTENANT - timedelta(days=1))),
    )

    resultat = retention.rapport(conn, TENANT)

    assert resultat["memoire_durable"]["total"] == 1
    assert resultat["memoire_durable"]["expirees"] == 1
    assert resultat["session"]["total"] == 0
    assert resultat["claim"] == {
        "nom": "claim",
        "table": "claim",
        "jours": 3650,
        "immuable": True,
        "supprimable": False,
        "total": 0,
        "expirees": 0,
        "supprimables": 0,
        "immuables": 0,
        "prochaine_expiration": None,
        "disponible": False,
        "limite": resultat["claim"]["limite"],
    }
    assert resultat["claim"]["limite"]
    assert resultat["limites"]
    assert resultat["complet"] is False


def test_purge_a_blanc_ne_supprime_rien_et_compte_les_candidats():
    """Par défaut, la purge est un dry-run : aucune ligne ne quitte la base."""
    conn = _connexion()
    _peupler(conn)
    avant = _compter(conn, "memoire_durable")

    resultat = retention.purger(conn, TENANT)

    assert resultat["supprimees"] == 0
    assert resultat["auraient_ete_supprimees"] == 4
    assert resultat["immuables_ignorees"] == 5
    assert resultat["erreurs"] == []
    assert _compter(conn, "memoire_durable") == avant
    assert _compter(conn, "prediction_calibration", TENANT) == 3
    assert _compter(conn, "claim", TENANT) == 1


def test_purge_reelle_ne_supprime_que_le_mutable_du_tenant():
    """Le réel supprime mémoire et calibration résolue, jamais les preuves ni l'autre tenant."""
    conn = _connexion()
    _peupler(conn)

    resultat = retention.purger(conn, TENANT, dry_run=False, maintenant=MAINTENANT)

    assert resultat["supprimees"] == 4
    assert resultat["auraient_ete_supprimees"] == 0
    assert resultat["immuables_ignorees"] == 5
    assert resultat["erreurs"] == []
    restantes = {
        ligne[0] for ligne in conn.execute(
            "SELECT id FROM memoire_durable WHERE tenant_id = ?", (TENANT,))
    }
    assert restantes == {"session-future", "memoire-future"}
    predictions = {
        ligne[0] for ligne in conn.execute(
            "SELECT id FROM prediction_calibration WHERE tenant_id = ?", (TENANT,))
    }
    assert predictions == {"pred-non-resolue", "pred-recente"}
    assert _compter(conn, "claim", TENANT) == 1
    assert _compter(conn, "preuve", TENANT) == 1
    assert {
        ligne[0] for ligne in conn.execute(
            "SELECT id FROM objet_entreprise WHERE tenant_id = ?", (TENANT,))
    } == {"learning-1", "outcome-1"}

    assert _compter(conn, "memoire_durable", AUTRE_TENANT) == 2
    assert _compter(conn, "prediction_calibration", AUTRE_TENANT) == 1
    assert _compter(conn, "claim", AUTRE_TENANT) == 1


def test_purge_reelle_isole_le_tenant_et_conserve_les_immuables():
    """La purge d'un tenant ne voit ni ne supprime les lignes d'un autre tenant."""
    conn = _connexion()
    _peupler(conn)

    resultat = retention.purger(conn, AUTRE_TENANT, dry_run=False, maintenant=MAINTENANT)

    assert resultat["supprimees"] == 3
    assert resultat["immuables_ignorees"] == 1
    assert _compter(conn, "memoire_durable", AUTRE_TENANT) == 0
    assert _compter(conn, "prediction_calibration", AUTRE_TENANT) == 0
    assert _compter(conn, "claim", AUTRE_TENANT) == 1
    assert _compter(conn, "memoire_durable", TENANT) == 5
    assert _compter(conn, "prediction_calibration", TENANT) == 3
    assert _compter(conn, "claim", TENANT) == 1


def test_purge_reelle_tolere_les_tables_absentes():
    """Une table absente ne fait pas échouer la purge des classes disponibles."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE memoire_durable ("
        " id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, classe TEXT NOT NULL,"
        " cree_le TEXT, expire_le TEXT)"
    )
    conn.execute(
        "INSERT INTO memoire_durable (id, tenant_id, classe, cree_le, expire_le) "
        "VALUES (?, ?, ?, ?, ?)",
        ("echue", TENANT, "contexte", _iso(MAINTENANT - timedelta(days=31)),
         _iso(MAINTENANT - timedelta(days=1))),
    )

    resultat = retention.purger(conn, TENANT, dry_run=False, maintenant=MAINTENANT)

    assert resultat["supprimees"] == 1
    assert resultat["erreurs"] == []
    assert _compter(conn, "memoire_durable", TENANT) == 0


def test_maintenant_invalide_et_tenant_invalide_sont_refuses():
    """Les contrats d'entrée restent stricts même en purge à blanc."""
    conn = _connexion()
    with pytest.raises(ValueError, match="maintenant"):
        retention.purger(conn, TENANT, maintenant="pas-une-date")
    with pytest.raises(ValueError):
        retention.purger(conn, "Banque !")


@besoin_pg
def test_pg_rapport_et_purge_sur_le_schema_reel(conn):
    """Le même contrat fonctionne sur PostgreSQL, y compris les dates typées."""
    tenant = "banque-retention"
    maintenant = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO memoire_durable "
        "(id, tenant_id, scope, scope_id, classe, contenu, provenance, expire_le, cree_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("session-age", tenant, "session", "s-1", "session", "note", "test",
         maintenant + timedelta(days=30), maintenant - timedelta(days=10)),
    )
    conn.execute(
        "INSERT INTO memoire_durable "
        "(id, tenant_id, scope, scope_id, classe, contenu, provenance, expire_le, cree_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("durable-echue", tenant, "twin", "t-1", "contexte", "note", "test",
         maintenant - timedelta(days=1), maintenant - timedelta(days=10)),
    )
    conn.execute(
        "INSERT INTO memoire_durable "
        "(id, tenant_id, scope, scope_id, classe, contenu, provenance, expire_le, cree_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("durable-longue", tenant, "twin", "t-1", "decision", "note", "test",
         maintenant + timedelta(days=200), maintenant - timedelta(days=500)),
    )
    conn.execute(
        "INSERT INTO prediction_calibration "
        "(id, tenant_id, decision_id, confidence, outcome, cree_le, resolue_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("pred-ancienne", tenant, "d-1", 0.8, True,
         maintenant - timedelta(days=400), maintenant - timedelta(days=399)),
    )
    conn.execute(
        "INSERT INTO prediction_calibration "
        "(id, tenant_id, decision_id, confidence, outcome, cree_le, resolue_le) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        ("pred-ouverte", tenant, "d-2", 0.4, None, maintenant - timedelta(days=400), None),
    )

    rapport = retention.rapport(conn, tenant)
    assert rapport["session"]["total"] == 1
    assert rapport["session"]["expirees"] == 1
    assert rapport["memoire_durable"]["total"] == 2
    assert rapport["memoire_durable"]["expirees"] == 1
    assert rapport["prediction"]["expirees"] == 2
    assert rapport["prediction"]["supprimables"] == 1

    a_blanc = retention.purger(conn, tenant, maintenant=maintenant)
    assert a_blanc["auraient_ete_supprimees"] == 3
    assert retention.rapport(conn, tenant)["memoire_durable"]["total"] == 2

    reel = retention.purger(conn, tenant, dry_run=False, maintenant=maintenant)
    assert reel["supprimees"] == 3
    restantes = {
        ligne[0] for ligne in conn.execute(
            "SELECT id FROM memoire_durable WHERE tenant_id = %s", (tenant,)).fetchall()
    }
    assert restantes == {"durable-longue"}
    predictions = {
        ligne[0] for ligne in conn.execute(
            "SELECT id FROM prediction_calibration WHERE tenant_id = %s", (tenant,)).fetchall()
    }
    assert predictions == {"pred-ouverte"}
