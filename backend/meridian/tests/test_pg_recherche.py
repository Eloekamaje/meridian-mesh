"""Recherche canonique dans Postgres : tsvector, repli ILIKE, tenant, types d'objets."""
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import pg_recherche
from meridian.tests.conftest import besoin_pg


def _jumeau(conn, jid, nom, mission="", type_="APPLICATION", tenant="banque"):
    conn.execute("INSERT INTO jumeau (id, tenant_id, nom, equipe, mission, type) VALUES (%s, %s, %s, 'e', %s, %s)",
                 (jid, tenant, nom, mission, type_))


def _claim(conn, jid, objet, tenant="banque"):
    return conn.execute("INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, confiance, mode) "
                        "VALUES (%s, %s, 'sujet', 'REALISE_CAPACITE', %s, 'CAPABILITY', 0.8, 'DECLARED') "
                        "RETURNING id", (tenant, jid, objet)).fetchone()[0]


@besoin_pg
def test_recherche_jumeaux_par_nom_et_mission_avec_type(conn):
    _jumeau(conn, "paiements", "Paiements", "Encaisse les paiements clients")
    _jumeau(conn, "process-paiement", "Processus de paiement", "Traite un paiement de bout en bout", "PROCESS")
    resultats = pg_recherche.rechercher_jumeaux(conn, "banque", "paiement")
    assert [r["id"] for r in resultats] == ["paiements", "process-paiement"]
    assert resultats[1]["type"] == "PROCESS"


@besoin_pg
def test_recherche_claims_et_isolation_tenant(conn):
    _jumeau(conn, "paiements", "Paiements", "Encaisse les paiements")
    c1 = _claim(conn, "paiements", "Gère les paiements par carte")
    _jumeau(conn, "secret", "Paiement secret", "Autre tenant", tenant="autre")
    _claim(conn, "secret", "Paiement secret", tenant="autre")
    resultats = pg_recherche.rechercher_claims(conn, "banque", "paiement")
    assert [r["id"] for r in resultats] == [c1]
    assert pg_recherche.rechercher_jumeaux(conn, "banque", "secret") == []


@besoin_pg
def test_recherche_vide_ou_limitee(conn):
    _jumeau(conn, "a", "Alpha", "Paiement")
    _jumeau(conn, "b", "Beta", "Paiement")
    assert pg_recherche.rechercher_jumeaux(conn, "banque", "") == []
    assert len(pg_recherche.rechercher_jumeaux(conn, "banque", "paiement", limite=1)) == 1
