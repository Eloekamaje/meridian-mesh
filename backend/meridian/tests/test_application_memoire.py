"""Application d'une consolidation : archive tracée, tenant, sélection et idempotence."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from meridian.adapters.outbound.postgres import application_memoire
from meridian.application import consolidation_memoire
from meridian.adapters.outbound.postgres import memoire_durable
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"

SCHEMA_MEMOIRE = """
CREATE TABLE IF NOT EXISTS memoire_durable (
    id          text NOT NULL,
    tenant_id   text NOT NULL,
    scope       text NOT NULL,
    scope_id    text NOT NULL,
    classe      text NOT NULL,
    contenu     text NOT NULL,
    provenance  text NOT NULL,
    consentement boolean NOT NULL DEFAULT false,
    consenti_le timestamptz,
    expire_le   timestamptz,
    confiance   double precision NOT NULL DEFAULT 0.5,
    donnees     jsonb NOT NULL DEFAULT '{}'::jsonb,
    cree_le     timestamptz NOT NULL DEFAULT now(),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id)
)
"""

SCHEMA_SQLITE = """
CREATE TABLE memoire_durable (
    id          TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    scope       TEXT NOT NULL,
    scope_id    TEXT NOT NULL,
    classe      TEXT NOT NULL,
    contenu     TEXT NOT NULL,
    provenance  TEXT NOT NULL,
    consentement INTEGER NOT NULL DEFAULT 0,
    consenti_le TEXT,
    expire_le   TEXT NOT NULL,
    confiance   REAL NOT NULL DEFAULT 0.5,
    donnees     TEXT NOT NULL DEFAULT '{}',
    cree_le     TEXT NOT NULL,
    maj_le      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id)
)
"""


def proposition(groupes, conflits=()):
    return consolidation_memoire.PropositionConsolidation(
        groupes=tuple(
            groupe if isinstance(groupe, consolidation_memoire.GroupeFusion)
            else consolidation_memoire.GroupeFusion(*groupe)
            for groupe in groupes
        ),
        conflits=tuple(conflits),
    )


def groupe(keep_id, remove_ids, raison="doublon"):
    return consolidation_memoire.GroupeFusion(
        keep_id=keep_id,
        remove_ids=tuple(remove_ids),
        raison=raison,
        confiance=0.95,
    )


@pytest.fixture
def conn_sqlite():
    connexion = sqlite3.connect(":memory:")
    connexion.execute(SCHEMA_SQLITE)
    yield connexion
    connexion.close()


def _inserer(
    connexion,
    identifiant,
    *,
    tenant=TENANT,
    provenance="test",
    donnees=None,
    expire_le=None,
):
    maintenant = datetime.now(timezone.utc)
    expiration = expire_le if expire_le is not None else maintenant + timedelta(days=30)
    if isinstance(expiration, datetime):
        expiration = expiration.isoformat()
    connexion.execute(
        "INSERT INTO memoire_durable (id, tenant_id, scope, scope_id, classe, contenu, provenance, "
        "consentement, consenti_le, expire_le, confiance, donnees, cree_le, maj_le) "
        "VALUES (?, ?, 'session', 's-1', 'contexte', ?, ?, 0, NULL, ?, 0.7, ?, ?, ?)",
        (
            identifiant,
            tenant,
            f"contenu {identifiant}",
            provenance,
            expiration,
            json.dumps(donnees or {}, ensure_ascii=False),
            maintenant.isoformat(),
            maintenant.isoformat(),
        ),
    )


def _ligne(connexion, identifiant, tenant=TENANT):
    ligne = connexion.execute(
        "SELECT id, provenance, expire_le, donnees FROM memoire_durable "
        "WHERE tenant_id = ? AND id = ?",
        (tenant, identifiant),
    ).fetchone()
    assert ligne is not None
    return {
        "id": ligne[0],
        "provenance": ligne[1],
        "expire_le": ligne[2],
        "donnees": json.loads(ligne[3]),
    }


def test_applique_le_groupe_selectionne_et_archive_sans_supprimer(conn_sqlite):
    _inserer(conn_sqlite, "m1", donnees={"canal": "web"})
    _inserer(conn_sqlite, "m2")
    _inserer(conn_sqlite, "m3")
    conflit = consolidation_memoire.Conflit(
        ids=("m2", "m3"), raison="désaccord déclaré", type="fait")
    prop = proposition([groupe("m1", ("m2", "m3"), raison="même politique")], [conflit])

    resultat = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m1"], acteur="alice")

    assert resultat["tenant"] == TENANT
    assert len(resultat["groupes"]) == 1
    assert resultat["groupes"][0]["garder"] == "m1"
    assert resultat["groupes"][0]["retirer"] == ["m2", "m3"]
    assert resultat["gardees"] == ["m1"]
    assert set(resultat["archivees"]) == {"m2", "m3"}
    assert resultat["ignorees"] == []
    assert resultat["ecritures"] is True
    assert resultat["conflits"] == [{
        "ids": ["m2", "m3"],
        "raison": "désaccord déclaré",
        "type": "fait",
        "gravite": "moyenne",
    }]

    garde = _ligne(conn_sqlite, "m1")
    assert "consolidation: alice" in garde["provenance"]
    assert garde["donnees"]["canal"] == "web"
    assert garde["donnees"]["consolidation"]["acteur"] == "alice"
    assert garde["donnees"]["consolidation"]["fusionne_avec"] == ["m2", "m3"]

    for identifiant in ("m2", "m3"):
        archivee = _ligne(conn_sqlite, identifiant)
        assert archivee["donnees"]["archive"] == {
            "raison": "même politique",
            "fusionne_dans": "m1",
            "acteur": "alice",
        }
        assert datetime.fromisoformat(archivee["expire_le"]) <= datetime.now(timezone.utc)

    assert conn_sqlite.execute("SELECT count(*) FROM memoire_durable").fetchone()[0] == 3


def test_ids_ne_selectionne_que_les_keep_ids_et_ignore_les_inconnus(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    _inserer(conn_sqlite, "m2")
    _inserer(conn_sqlite, "m3")
    _inserer(conn_sqlite, "m4")
    prop = proposition([groupe("m1", ("m2",)), groupe("m3", ("m4",))])

    par_retiree = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m2"], acteur="alice")

    assert par_retiree["groupes"] == []
    assert par_retiree["gardees"] == [] and par_retiree["archivees"] == []
    assert par_retiree["ignorees"] == ["m2"]
    assert _ligne(conn_sqlite, "m1")["provenance"] == "test"
    assert datetime.fromisoformat(_ligne(conn_sqlite, "m2")["expire_le"]) > datetime.now(timezone.utc)

    selection = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m3", "absent"], acteur="alice")

    assert [element["garder"] for element in selection["groupes"]] == ["m3"]
    assert selection["gardees"] == ["m3"] and selection["archivees"] == ["m4"]
    assert selection["ignorees"] == ["absent"]
    assert _ligne(conn_sqlite, "m1")["provenance"] == "test"


def test_acteur_et_tenant_sont_exiges_sans_ecriture(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    _inserer(conn_sqlite, "m2")
    prop = proposition([groupe("m1", ("m2",))])

    with pytest.raises(application_memoire.ConsolidationInvalide):
        application_memoire.appliquer_consolidation(
            conn_sqlite, TENANT, prop, ids=["m1"], acteur="   ")

    with pytest.raises(application_memoire.ConsolidationInvalide):
        application_memoire.appliquer_consolidation(
            conn_sqlite, "Banque !", prop, ids=["m1"], acteur="alice")

    assert _ligne(conn_sqlite, "m1")["provenance"] == "test"
    assert datetime.fromisoformat(_ligne(conn_sqlite, "m2")["expire_le"]) > datetime.now(timezone.utc)


def test_reapplication_ignore_les_archives_et_ne_duplique_rien(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    _inserer(conn_sqlite, "m2")
    prop = proposition([groupe("m1", ("m2",))])

    premier = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m1"], acteur="alice")
    expiration = _ligne(conn_sqlite, "m2")["expire_le"]

    second = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m1"], acteur="alice")

    assert premier["archivees"] == ["m2"]
    assert second["groupes"] == [] and second["gardees"] == [] and second["archivees"] == []
    assert set(second["ignorees"]) == {"m1", "m2"}
    assert _ligne(conn_sqlite, "m2")["expire_le"] == expiration
    assert _ligne(conn_sqlite, "m1")["provenance"].count("consolidation: alice") == 1


def test_archive_existante_est_ignoree_sans_etre_reecrite(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    ancienne = datetime.now(timezone.utc) - timedelta(days=1)
    _inserer(
        conn_sqlite,
        "m2",
        expire_le=ancienne,
        donnees={"archive": {"raison": "ancienne", "fusionne_dans": "m0", "acteur": "bob"}},
    )
    prop = proposition([groupe("m1", ("m2",))])

    resultat = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m1"], acteur="alice")

    assert resultat["groupes"] == [] and resultat["archivees"] == []
    assert set(resultat["ignorees"]) == {"m1", "m2"}
    assert _ligne(conn_sqlite, "m2")["donnees"]["archive"]["acteur"] == "bob"
    assert _ligne(conn_sqlite, "m1")["provenance"] == "test"


def test_frontiere_tenant_et_garde_absente(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    _inserer(conn_sqlite, "m2")
    _inserer(conn_sqlite, "m2", tenant=AUTRE_TENANT, provenance="autre")
    prop = proposition([groupe("m1", ("m2",))])

    resultat = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, prop, ids=["m1"], acteur="alice")

    assert resultat["archivees"] == ["m2"]
    assert _ligne(conn_sqlite, "m2", tenant=AUTRE_TENANT)["provenance"] == "autre"
    assert datetime.fromisoformat(
        _ligne(conn_sqlite, "m2", tenant=AUTRE_TENANT)["expire_le"]
    ) > datetime.now(timezone.utc)

    absente = proposition([groupe("inconnue", ("m1",))])
    ignoree = application_memoire.appliquer_consolidation(
        conn_sqlite, TENANT, absente, ids=["inconnue"], acteur="alice")

    assert ignoree["groupes"] == [] and ignoree["archivees"] == []
    assert ignoree["ignorees"] == ["inconnue"]
    assert datetime.fromisoformat(_ligne(conn_sqlite, "m1")["expire_le"]) > datetime.now(timezone.utc)


def test_proposition_dict_et_alias_garder_retirer(conn_sqlite):
    _inserer(conn_sqlite, "m1")
    _inserer(conn_sqlite, "m2")

    resultat = application_memoire.appliquer_consolidation(
        conn_sqlite,
        TENANT,
        {"groupes": [{"garder": "m1", "retirer": ["m2"], "raison": "dict"}]},
        ids=["m1"],
        acteur="alice",
    )

    assert resultat["gardees"] == ["m1"] and resultat["archivees"] == ["m2"]
    assert _ligne(conn_sqlite, "m2")["donnees"]["archive"]["raison"] == "dict"


@besoin_pg
def test_application_postgres_jsonb_et_calibration_du_tenant(conn):
    conn.execute(SCHEMA_MEMOIRE)
    for identifiant in ("m1", "m2"):
        memoire_durable.creer(
            conn, TENANT, id=identifiant, scope="session", scope_id="s-1",
            classe="contexte", contenu=f"contenu {identifiant}", provenance="test",
            donnees={"canal": identifiant},
        )
    prop = proposition([groupe("m1", ("m2",), raison="doublon postgres")])

    resultat = application_memoire.appliquer_consolidation(
        conn, TENANT, prop, ids=["m1"], acteur="alice")

    assert resultat["gardees"] == ["m1"] and resultat["archivees"] == ["m2"]
    garde = memoire_durable.lire(conn, TENANT, "m1")
    archivee = memoire_durable.lire(conn, TENANT, "m2")
    assert "consolidation: alice" in garde["provenance"]
    assert garde["donnees"]["consolidation"]["acteur"] == "alice"
    assert archivee["donnees"]["archive"] == {
        "raison": "doublon postgres",
        "fusionne_dans": "m1",
        "acteur": "alice",
    }
