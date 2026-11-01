"""Contrat Claim P0-B : ACCEPTED exige une preuve SUPPORT, en plus de la revue humaine."""
import pytest

from meridian.adapters.outbound.postgres import depot
from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim

psycopg = pytest.importorskip("psycopg")
pytestmark = besoin_pg


def preparer(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    return depot.lister_claims(conn, "tbt")[0]["id"]


def claim_sans_preuve(conn, objet="sans-preuve", statut="PROPOSED", mode="INFERRED"):
    return conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, statut, mode, confiance) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        ("banque", "tbt", "TBT", "X", objet, "DEPENDENCY", statut, mode, 0.4)).fetchone()[0]


def revue_acceptee(conn, cid):
    conn.execute(
        "INSERT INTO revue (tenant_id, claim_id, acteur, decision, motif) "
        "VALUES ('banque', %s, 'alice', 'ACCEPTED', 'revue faite')", (cid,))


def test_acceptation_sans_preuve_support_refusee_meme_avec_revue(conn):
    preparer(conn)
    cid = claim_sans_preuve(conn)
    revue_acceptee(conn, cid)

    with pytest.raises(psycopg.errors.RaiseException, match="preuve SUPPORT"):
        conn.execute("UPDATE claim SET statut = 'ACCEPTED' WHERE id = %s", (cid,))
    assert conn.execute("SELECT statut FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "PROPOSED"


def test_acceptation_avec_revue_et_preuve_support_acceptee(conn):
    cid = preparer(conn)
    depot.reviser(conn, cid, "alice", "ACCEPTED", "vu dans le code")

    assert conn.execute("SELECT statut FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "ACCEPTED"


def test_preuve_contre_ne_suffit_pas(conn):
    preparer(conn)
    cid = claim_sans_preuve(conn, objet="contre-seulement")
    preuve_id = conn.execute("SELECT id FROM preuve LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO claim_preuve (claim_id, preuve_id, role) VALUES (%s, %s, 'CONTRE')",
                 (cid, preuve_id))
    revue_acceptee(conn, cid)

    with pytest.raises(psycopg.errors.RaiseException, match="preuve SUPPORT"):
        conn.execute("UPDATE claim SET statut = 'ACCEPTED' WHERE id = %s", (cid,))
    assert conn.execute("SELECT statut FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "PROPOSED"


def test_revue_restee_obligatoire_pour_un_claim_prouve(conn):
    cid = preparer(conn)

    with pytest.raises(psycopg.errors.RaiseException, match="sans revue"):
        conn.execute("UPDATE claim SET statut = 'ACCEPTED' WHERE id = %s", (cid,))
    assert conn.execute("SELECT statut FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "PROPOSED"


def test_claim_sans_preuve_reste_propose_ou_infere(conn):
    preparer(conn)
    cid = claim_sans_preuve(conn, objet="hypothese", statut="PROPOSED", mode="INFERRED")

    assert conn.execute(
        "SELECT statut, mode, version, remplace_id FROM claim WHERE id = %s", (cid,)).fetchone() == (
            "PROPOSED", "INFERRED", 1, None)
    conn.execute("UPDATE claim SET statut = 'PROPOSED' WHERE id = %s", (cid,))
    conn.execute("UPDATE claim SET mode = 'INFERRED' WHERE id = %s", (cid,))
    assert conn.execute("SELECT statut, mode FROM claim WHERE id = %s", (cid,)).fetchone() == (
        "PROPOSED", "INFERRED")


def test_colonnes_version_et_remplace_id_et_schema_idempotent(conn):
    depot.appliquer_schema(conn)
    depot.appliquer_schema(conn)

    cid = preparer(conn)
    assert conn.execute("SELECT version, remplace_id FROM claim WHERE id = %s", (cid,)).fetchone() == (1, None)
    conn.execute("UPDATE claim SET version = 2, remplace_id = %s WHERE id = %s", (cid, cid))
    assert conn.execute("SELECT version, remplace_id FROM claim WHERE id = %s", (cid,)).fetchone() == (2, cid)

    triggers = {ligne[0] for ligne in conn.execute(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'claim'::regclass AND NOT tgisinternal")}
    assert {"claim_accepte_exige_preuve", "claim_accepte_exige_revue"} <= triggers
