"""Persistance des Claims dans Postgres (tests d'intégration ; ignorés sans JUMEAU_PG_DSN)."""
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("JUMEAU_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")

from jumeau import depot  # noqa: E402

JUMEAU = {"id": "tbt", "tenant_id": "banque", "nom": "TBT", "equipe": "equipe-tbt"}
SOURCE = {"nom": "tbt-repo", "type": "GIT", "emplacement": "/depots/tbt", "curseur": "sha1"}
ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "test"}


def claim(objet, sha="sha1", ligne=3):
    return {
        "sujet": "TBT", "predicat": "DEPEND_DE", "objet": objet, "type": "DEPENDENCY", "confiance": 0.85,
        "preuves": [{
            "locator": f"git://tbt@{sha}:requirements.txt#L{ligne}-L{ligne}", "chemin": "requirements.txt",
            "sha": sha, "ligne_debut": ligne, "ligne_fin": ligne, "citation": objet, "hash": "h",
        }],
    }


@pytest.fixture
def conn():
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}")
        depot.appliquer_schema(c)
        yield c
        c.execute(f"DROP SCHEMA {schema} CASCADE")


def objets_valides(conn):
    return {c["objet"] for c in depot.lister_claims(conn, "tbt")}


def test_ingestion_idempotente(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    claims = depot.lister_claims(conn, "tbt")
    assert len(claims) == 1 and len(claims[0]["preuves"]) == 1
    assert claims[0]["statut"] == "PROPOSED" and claims[0]["maturite"] == "M2"


def test_claim_disparu_est_cloture_puis_rouvert(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    depot.enregistrer(conn, JUMEAU, {**SOURCE, "curseur": "sha2"}, [claim("motor", "sha2")], ACTIVITE)
    assert objets_valides(conn) == {"motor"}
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    assert objets_valides(conn) == {"motor", "fastapi"}


def test_nouveau_sha_ajoute_une_preuve_sans_effacer_l_ancienne(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor", "sha2")], ACTIVITE)
    assert len(depot.lister_claims(conn, "tbt")[0]["preuves"]) == 2


def test_preuve_immuable(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE preuve SET hash = 'x'")


def test_acceptation_exige_une_revue_humaine(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE claim SET statut = 'ACCEPTED' WHERE id = %s", (cid,))
    depot.reviser(conn, cid, "alice", "ACCEPTED", "vu dans le code")
    c = depot.lister_claims(conn, "tbt")[0]
    assert (c["statut"], c["maturite"]) == ("ACCEPTED", "M3")
    assert c["revues"][0]["acteur"] == "alice"


def test_contestation_garde_la_maturite(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    depot.reviser(conn, cid, "bob", "CONTESTED", "plus utilisé")
    c = depot.lister_claims(conn, "tbt")[0]
    assert (c["statut"], c["maturite"]) == ("CONTESTED", "M2")


def test_ingestion_vide_refusee_sans_rien_cloturer(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    with pytest.raises(ValueError):
        depot.enregistrer(conn, JUMEAU, SOURCE, [], ACTIVITE)
    assert objets_valides(conn) == {"motor"}


def test_claim_rouvert_repart_en_proposition(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    cid = next(c["id"] for c in depot.lister_claims(conn, "tbt") if c["objet"] == "fastapi")
    depot.reviser(conn, cid, "alice", "ACCEPTED", None)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor"), claim("fastapi", ligne=1)], ACTIVITE)
    c = next(c for c in depot.lister_claims(conn, "tbt") if c["objet"] == "fastapi")
    assert (c["statut"], c["maturite"]) == ("PROPOSED", "M2")


def test_claim_toujours_observe_garde_sa_validation(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    depot.reviser(conn, cid, "alice", "ACCEPTED", None)
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor", "sha2")], ACTIVITE)
    assert depot.lister_claims(conn, "tbt")[0]["statut"] == "ACCEPTED"


def test_autre_tenant_ne_peut_pas_reprendre_un_jumeau(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    with pytest.raises(PermissionError):
        depot.enregistrer(conn, {**JUMEAU, "tenant_id": "autre"}, SOURCE, [claim("motor")], ACTIVITE)


def test_meme_locator_dans_deux_sources_donne_deux_preuves(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    autre = {**JUMEAU, "id": "tbt2"}
    depot.enregistrer(conn, autre, {**SOURCE, "emplacement": "/clone"}, [claim("motor")], ACTIVITE)
    pid = depot.lister_claims(conn, "tbt2")[0]["preuves"][0]["id"]
    assert depot.preuve_par_id(conn, pid)["emplacement"] == "/clone"


def test_insertion_directe_acceptee_refusee(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, statut, confiance) "
                     "VALUES ('banque', 'tbt', 'TBT', 'X', 'y', 'DEPENDENCY', 'ACCEPTED', 0.5)")


def test_revue_immuable(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    depot.reviser(conn, depot.lister_claims(conn, "tbt")[0]["id"], "alice", "ACCEPTED", None)
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM revue")


def test_preuve_par_id_donne_l_emplacement_du_depot(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    pid = depot.lister_claims(conn, "tbt")[0]["preuves"][0]["id"]
    p = depot.preuve_par_id(conn, pid)
    assert (p["emplacement"], p["sha"], p["chemin"]) == ("/depots/tbt", "sha1", "requirements.txt")
