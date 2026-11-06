"""Backfill `perimetre_id` : dry-run, apply, non-écrasement, idempotence et périmètre vide."""
from meridian.application import backfill_perimetre
from meridian.tests.conftest import besoin_pg

pytestmark = besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"


def _inserer(conn, identifiant, perimetre=None, perimetre_id=None, tenant=TENANT):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe, perimetre, perimetre_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (identifiant, tenant, f"Twin {identifiant}", "equipe-test", perimetre, perimetre_id),
    )


def _perimetre_id(conn, identifiant):
    return conn.execute(
        "SELECT perimetre_id FROM jumeau WHERE id = %s", (identifiant,)
    ).fetchone()[0]


def test_un_twin_avec_perimetre_est_migre_en_dry_run_puis_apply(conn):
    _inserer(conn, "app-paie", perimetre="Paiements Cartes")

    rapport = backfill_perimetre.migrer(conn)

    assert rapport == {
        "dry_run": True,
        "a_migrer": 1,
        "migres": 0,
        "ignores": [],
        "ids": ["app-paie"],
        "valeurs": {"app-paie": "paiements-cartes"},
    }
    assert _perimetre_id(conn, "app-paie") is None

    applique = backfill_perimetre.migrer(conn, appliquer=True)

    assert applique == {
        "dry_run": False,
        "a_migrer": 1,
        "migres": 1,
        "ignores": [],
        "ids": ["app-paie"],
        "valeurs": {"app-paie": "paiements-cartes"},
    }
    assert _perimetre_id(conn, "app-paie") == "paiements-cartes"


def test_un_perimetre_id_existant_n_est_pas_ecrase(conn):
    _inserer(conn, "app-legacy", perimetre="Paiements Cartes",
             perimetre_id="portefeuille-cartes")
    _inserer(conn, "app-nouveau", perimetre="Paiements Cartes")

    rapport = backfill_perimetre.migrer(conn, appliquer=True)

    assert rapport["a_migrer"] == 1
    assert rapport["migres"] == 1
    assert rapport["ids"] == ["app-nouveau"]
    assert rapport["valeurs"] == {"app-nouveau": "paiements-cartes"}
    assert _perimetre_id(conn, "app-legacy") == "portefeuille-cartes"
    assert _perimetre_id(conn, "app-nouveau") == "paiements-cartes"


def test_le_deuxieme_apply_ne_migre_rien(conn):
    _inserer(conn, "app-paie", perimetre="Périmètre Paiements Europe")

    assert backfill_perimetre.migrer(conn, appliquer=True)["migres"] == 1

    second = backfill_perimetre.migrer(conn, appliquer=True)

    assert second == {
        "dry_run": False,
        "a_migrer": 0,
        "migres": 0,
        "ignores": [],
        "ids": [],
        "valeurs": {},
    }
    assert _perimetre_id(conn, "app-paie") == "perimetre-paiements-europe"


def test_un_perimetre_vide_est_ignore(conn):
    _inserer(conn, "sans-perimetre", perimetre="")
    _inserer(conn, "sans-texte", perimetre=None)

    rapport = backfill_perimetre.migrer(conn, appliquer=True)

    assert rapport["a_migrer"] == 0
    assert rapport["migres"] == 0
    assert rapport["ids"] == []
    assert rapport["valeurs"] == {}
    assert rapport["ignores"] == ["sans-perimetre", "sans-texte"]
    assert _perimetre_id(conn, "sans-perimetre") is None
    assert _perimetre_id(conn, "sans-texte") is None


def test_tenant_et_limite_bornent_le_lot(conn):
    _inserer(conn, "app-a", perimetre="Alpha")
    _inserer(conn, "app-b", perimetre="Beta")
    _inserer(conn, "app-autre", perimetre="Autre", tenant=AUTRE_TENANT)

    rapport = backfill_perimetre.migrer(conn, tenant=TENANT, limite=1)

    assert rapport["a_migrer"] == 1
    assert rapport["ids"] == ["app-a"]
    assert rapport["valeurs"] == {"app-a": "alpha"}

    assert backfill_perimetre.migrer(
        conn, tenant=TENANT, limite=1, appliquer=True)["migres"] == 1
    assert _perimetre_id(conn, "app-a") == "alpha"
    assert _perimetre_id(conn, "app-b") is None
    assert _perimetre_id(conn, "app-autre") is None
