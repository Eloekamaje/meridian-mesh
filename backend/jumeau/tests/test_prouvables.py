"""Ce que le code peut établir, et ce qu'il ne peut pas (plan de remédiation L1bis.2).

Sur les 546 connaissances courantes de la base, 148 ont un prédicat sémantique (`APPLIQUE_REGLE`, `REALISE_CAPACITE`,
`DETIENT`, `SERT_ACTEUR`, `ECHANGE_AVEC`) et **toutes** ont `origine = 'CONVERSATION'` : elles sont écrites par le
modèle et citent une ligne qui ne les établit pas. Elles restent des hypothèses et ne reçoivent aucun diplôme.
"""
import pytest

from jumeau import connaissance
from jumeau.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim

psycopg = pytest.importorskip("psycopg")

SEMANTIQUES = ["APPLIQUE_REGLE", "REALISE_CAPACITE", "DETIENT", "SERT_ACTEUR", "ECHANGE_AVEC"]


def test_les_predicats_prouvables_sont_ceux_de_l_ingestion():
    assert connaissance.prouvable("DEPEND_DE") and connaissance.prouvable("expose")
    assert connaissance.prouvable("LIT_VARIABLE") and connaissance.prouvable("EXECUTE_IMAGE")
    assert not any(connaissance.prouvable(p) for p in SEMANTIQUES)
    assert not connaissance.prouvable("") and not connaissance.prouvable(None)


@besoin_pg
def test_sql_et_python_disent_la_meme_chose(conn):
    for predicat in ["DEPEND_DE", "EXPOSE", "LIT_VARIABLE", "EXECUTE_IMAGE", *SEMANTIQUES, "", None]:
        assert conn.execute("SELECT predicat_prouvable(%s)", (predicat,)).fetchone()[0] is connaissance.prouvable(predicat)


@besoin_pg
def test_une_hypothese_ne_recoit_pas_de_diplome_malgre_sa_preuve(conn):
    """Une preuve existe, elle est citée au commit — et pourtant elle n'établit pas la phrase. M2 est refusé."""
    depot_claim = {**claim("Seuls les conseillers valident"), "predicat": "APPLIQUE_REGLE", "type": "BUSINESS_RULE"}
    from jumeau import depot
    depot.enregistrer(conn, JUMEAU, SOURCE, [depot_claim], ACTIVITE)
    assert depot.lister_claims(conn, "tbt")[0]["maturite"] == "M1"
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)  # un fait, lui, garde M2
    assert {c["objet"]: c["maturite"] for c in depot.lister_claims(conn, "tbt")}["motor"] == "M2"


@besoin_pg
def test_une_hypothese_qui_devient_prouvable_change_de_diplome(conn):
    """Le jour où une source établit la phrase, le diplôme revient : la règle porte sur le prédicat, pas sur l'âge."""
    from jumeau import depot
    depot.enregistrer(conn, JUMEAU, SOURCE, [{**claim("x"), "predicat": "APPLIQUE_REGLE"}], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M1"
    conn.execute("UPDATE claim SET predicat = 'DEPEND_DE' WHERE id = %s", (cid,))  # prédicat prouvable
    conn.execute("SELECT recalculer_maturite(%s)", (cid,))
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M2"
