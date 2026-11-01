"""Croiser les sources : maturité calculée par les systèmes distincts, contradictions vérifiées, revue."""
import pytest

from meridian.adapters.outbound.postgres import croisement
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import examen
from meridian.adapters.outbound.connectors.lecteurs import LecteurMemoire
from meridian.adapters.outbound.connectors.source_git import sha_courant
from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim

DOC = LecteurMemoire("wiki", "ESP", {"PRD": {"titre": "PRD", "versions": {"3": ["Le seuil est de 500.", "Fin."]}}},
                     systeme="confluence")
CITATION_DOC = "confluence://ESP/PRD@3#L1-L1"


def sources_git(depot_git):
    return [{"id": None, "nom": "tbt-repo", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}]


def signaler(depot_git, a, b, lecteurs=(DOC,)):
    return croisement.signaler(None, JUMEAU, "Le seuil diffère", a, b, sources_git(depot_git), list(lecteurs), "flore")


# --- contradictions : refus avant toute écriture ---------------------------------------------------

def test_citation_fausse_refusee(depot_git):
    with pytest.raises(ValueError, match="introuvable"):
        signaler(depot_git, "app.py#L9999-L9999", CITATION_DOC)
    with pytest.raises(ValueError, match="introuvable"):
        signaler(depot_git, "app.py#L1-L2", "confluence://ESP/PRD@3#L1-L9")
    with pytest.raises(ValueError, match="introuvable"):
        signaler(depot_git, "app.py#L1-L2", "confluence://ESP/PRD@2#L1-L1")


def test_source_non_branchee_refusee(depot_git):
    with pytest.raises(ValueError, match="non branchée"):
        signaler(depot_git, "app.py#L1-L2", CITATION_DOC, lecteurs=())


def test_meme_systeme_refuse(depot_git):
    with pytest.raises(ValueError, match="même système"):
        signaler(depot_git, "app.py#L1-L2", "requirements.txt#L1-L1")
    with pytest.raises(ValueError, match="même système"):
        signaler(depot_git, CITATION_DOC, "confluence://ESP/PRD@3#L2-L2")


def test_enonce_vide_refuse(depot_git):
    with pytest.raises(ValueError, match="vide"):
        croisement.signaler(None, JUMEAU, "  ", "app.py#L1", CITATION_DOC, sources_git(depot_git), [DOC], "flore")


def test_contradiction_acceptee_code_contre_documentation(depot_git, monkeypatch):
    vus = []
    monkeypatch.setattr(depot, "enregistrer_contradiction", lambda *a: vus.append(a) or 7)
    assert signaler(depot_git, "`app.py#L1-L2`", CITATION_DOC) == 7
    _, _, enonce, a, b, acteur = vus[0]
    assert (a, b, acteur) == (("app.py#L1-L2", "git"), (CITATION_DOC, "confluence"), "flore")


# --- revue ------------------------------------------------------------------------------------------

def test_revue_expose_maturite_et_contradictions_ouvertes():
    claims = [{**claim_revue, "maturite": m} for claim_revue, m in zip(
        [{"predicat": "DEPEND_DE", "objet": o, "statut": "PROPOSED", "preuves": []} for o in "abcd"],
        ["M2", "M3", "M4", "M4"])]
    ouverte = {"enonce": "Le seuil diffère", "systeme_a": "git", "systeme_b": "confluence"}
    p = examen.depuis_connaissances({"nom": "X"}, claims, None, [ouverte])["presentation"]
    assert p["maturite"] == {"croisees": 1, "validees": 2, "hypotheses": 0}
    assert {"nom": "Contradictions", "etat": "1 ouverte(s)", "ok": False} in p["sources"]
    assert "Contradiction à trancher : Le seuil diffère (git contre confluence)" in p["ignore"]


def test_revue_sans_contradiction_n_ajoute_pas_de_pastille():
    p = examen.depuis_connaissances({"nom": "X"}, [], None)["presentation"]
    assert all(s["nom"] != "Contradictions" for s in p["sources"]) and p["maturite"] == {"croisees": 0, "validees": 0, "hypotheses": 0}


# --- maturité calculée (Postgres) -------------------------------------------------------------------

def ajouter_preuve(conn, jumeau, nom, type_source, claim_id, locator):
    sid = conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) VALUES (%s, %s, %s, %s, 'x') "
        "ON CONFLICT (jumeau_id, nom) DO UPDATE SET nom = EXCLUDED.nom RETURNING id",
        (jumeau["tenant_id"], jumeau["id"], type_source, nom)).fetchone()[0]
    depot._lier_preuve(conn, jumeau["tenant_id"], sid, claim_id,
                       {"locator": locator, "chemin": "PRD", "sha": "3", "ligne_debut": 1, "ligne_fin": 1, "hash": "h"},
                       ACTIVITE)


def maturite(conn, cid):
    return next(c for c in depot.lister_claims(conn, "tbt") if c["id"] == cid)["maturite"]


@besoin_pg
def test_une_source_m2_deux_systemes_recoupes_m3_validee_m4(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    assert maturite(conn, cid) == "M2"
    ajouter_preuve(conn, JUMEAU, "wiki", "DOCUMENTATION", cid, CITATION_DOC)
    assert maturite(conn, cid) == "M2"  # deux systèmes comptés ne suffisent pas : encore faut-il qu'ils concordent
    conn.execute("INSERT INTO verification (claim_id, etat, methode, systemes, empreinte) "
                 "VALUES (%s, 'recoupe', 'juge', ARRAY['documentation', 'git'], 'e')", (cid,))
    assert maturite(conn, cid) == "M3"
    depot.reviser(conn, cid, "alice", "ACCEPTED", "vu")
    assert maturite(conn, cid) == "M4"
    depot.reviser(conn, cid, "alice", "CONTESTED", "finalement non")
    assert maturite(conn, cid) == "M3"


@besoin_pg
def test_deux_depots_git_restent_m2(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    ajouter_preuve(conn, JUMEAU, "autre-repo", "GIT", cid, "git://autre@sha:requirements.txt#L1-L1")
    assert maturite(conn, cid) == "M2"


@besoin_pg
def test_acceptation_sans_revue_toujours_interdite(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("motor")], ACTIVITE)
    cid = depot.lister_claims(conn, "tbt")[0]["id"]
    with pytest.raises(Exception, match="sans revue"):
        conn.execute("UPDATE claim SET statut = 'ACCEPTED' WHERE id = %s", (cid,))


@besoin_pg
def test_contradiction_enregistree_listee_puis_tranchee(conn, depot_git):
    depot.enregistrer(conn, JUMEAU, {**SOURCE, "emplacement": str(depot_git), "curseur": sha_courant(depot_git)},
                      [claim("motor")], ACTIVITE)
    ajouter_preuve(conn, JUMEAU, "wiki", "DOCUMENTATION", depot.lister_claims(conn, "tbt")[0]["id"], CITATION_DOC)
    src = depot.sources_du_jumeau(conn, "tbt")
    cid = croisement.signaler(conn, JUMEAU, "Le seuil diffère", "app.py#L1-L2", CITATION_DOC, src, [DOC], "flore")
    ouvertes = depot.contradictions_ouvertes(conn, "tbt")
    assert [(o["id"], o["systeme_a"], o["systeme_b"]) for o in ouvertes] == [(cid, "git", "confluence")]
    assert "Contradiction à trancher" in str(examen.examiner(conn, "tbt", {"nom": "TBT"})["presentation"]["ignore"])
    structure = examen.examiner(conn, "tbt", {"nom": "TBT"})["presentation"]["contradictions"]
    assert structure == [{"id": cid, "enonce": "Le seuil diffère", "preuve_a": "app.py#L1-L2", "systeme_a": "git",
                          "preuve_b": CITATION_DOC, "systeme_b": "confluence"}]
    depot.trancher_contradiction(conn, "tbt", cid, "alice", "a", "le code fait foi")
    assert depot.contradictions_ouvertes(conn, "tbt") == []
    row = conn.execute("SELECT verdict, tranchee_par, motif FROM contradiction WHERE id = %s", (cid,)).fetchone()
    assert row == ("a", "alice", "le code fait foi")
    with pytest.raises(LookupError):
        depot.trancher_contradiction(conn, "tbt", cid, "bob", "b", "deux fois")


@besoin_pg
def test_trancher_refuse_verdict_invalide_et_autre_jumeau(conn, depot_git):
    depot.enregistrer(conn, JUMEAU, {**SOURCE, "emplacement": str(depot_git), "curseur": sha_courant(depot_git)},
                      [claim("motor")], ACTIVITE)
    cid = depot.enregistrer_contradiction(conn, JUMEAU, "x", ("app.py#L1-L2", "git"), (CITATION_DOC, "confluence"), "flore")
    with pytest.raises(ValueError):
        depot.trancher_contradiction(conn, "tbt", cid, "alice", "les deux")
    with pytest.raises(LookupError):
        depot.trancher_contradiction(conn, "autre", cid, "alice", "a")
    assert len(depot.contradictions_ouvertes(conn, "tbt")) == 1


def test_route_trancher_refuse_verdict_invalide_sans_toucher_la_base():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from meridian.adapters.inbound.http import interfaces as routes
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.connexion] = lambda: None
    assert TestClient(app).post("/v2/contradictions/1/revue", json={"verdict": "c"}).status_code == 422


@besoin_pg
def test_une_contradiction_tranchee_est_immuable_dans_la_base(conn):
    import psycopg as pg
    from meridian.adapters.outbound.postgres import depot
    from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, claim
    depot.enregistrer(conn, JUMEAU, SOURCE, [claim("x")], ACTIVITE)
    cid = depot.enregistrer_contradiction(conn, JUMEAU, "doc ≠ code", ("a", "GIT"), ("b", "CONFLUENCE"), "agent")
    depot.trancher_contradiction(conn, "tbt", cid, "alice", "a", "vu")
    with pytest.raises(pg.errors.RaiseException):
        conn.execute("UPDATE contradiction SET verdict = 'b' WHERE id = %s", (cid,))
    with pytest.raises(pg.errors.RaiseException):
        conn.execute("DELETE FROM contradiction WHERE id = %s", (cid,))
