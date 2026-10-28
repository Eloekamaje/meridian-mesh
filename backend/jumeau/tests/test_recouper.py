"""Recouper : la documentation du dépôt est un système à part, et l'agent ajoute une seconde source à une connaissance."""
import subprocess
from pathlib import Path

import pytest

from jumeau import agent, connaissance, depot, recoupement
from jumeau.lecteurs import LecteurMemoire
from jumeau.tests.conftest import JUMEAU, besoin_pg
from jumeau.tests.test_agent import CONTEXTE

CAS_SYSTEME = [("CODE", "README.md", "GIT"), ("CODE", "docs/a/Guide.MDX", "GIT"), ("CODE", "x.rst", "GIT"),
               ("CODE", "x.adoc", "GIT"), ("CODE", "requirements.txt", "GIT"), ("CODE", "app.py", "GIT"),
               ("CODE", "notes.md.bak", "GIT"), ("DOCUMENTATION", "12", "CONFLUENCE"),
               ("DOCUMENTATION", "page.md", "CONFLUENCE"), ("TICKET", "TBT-1", "JIRA")]


def test_systeme_de_preuve_python():
    assert [recoupement.systeme_de_preuve(*c) for c in CAS_SYSTEME] == [
        "documentation", "documentation", "documentation", "documentation", "git", "git", "git",
        "confluence", "confluence", "jira"]


@besoin_pg
def test_systeme_de_preuve_sql_aligne_sur_python(conn):
    for c in CAS_SYSTEME:
        assert conn.execute("SELECT systeme_de_preuve(%s, %s, %s)", c).fetchone()[0] == recoupement.systeme_de_preuve(*c)


# --- sans base ---------------------------------------------------------------------------------

def test_outil_present_seulement_avec_du_code_ou_des_lecteurs():
    def noms(ctx):
        return {t.tool_name for t in agent.outils(ctx, "dsn", "m", agent.Budget())}
    lecteur = LecteurMemoire("Wiki", "TBT", {})
    assert "recouper_connaissance" in noms(CONTEXTE)
    assert "recouper_connaissance" in noms({**CONTEXTE, "sources": [], "lecteurs": [lecteur]})
    assert "recouper_connaissance" not in noms({**CONTEXTE, "sources": [], "lecteurs": []})


def test_outil_recouper_refus_et_plafond(monkeypatch):
    def refus(*a):
        raise ValueError("ce n'est pas un recoupement")
    monkeypatch.setattr(agent, "recouper_code", refus)
    monkeypatch.setattr(agent.psycopg, "connect", lambda *a, **k: __import__("contextlib").nullcontext())
    o = {t.tool_name: t for t in agent.outils(CONTEXTE, "dsn", "m", agent.Budget(propositions=1))}
    assert "Recoupement refusé : ce n'est pas un recoupement" in o["recouper_connaissance"](
        connaissance=1, citation="README.md#L1", raison="r")
    assert "Plafond" in o["recouper_connaissance"](connaissance=1, citation="README.md#L1", raison="r")


def test_la_methode_enseigne_a_recouper():
    corps = (Path(__file__).parent.parent / "methodes" / "comprendre-application.md").read_text()
    assert "recouper_connaissance" in corps and "signaler_contradiction" in corps


# --- avec Postgres -----------------------------------------------------------------------------

@pytest.fixture
def monde(conn, depot_git):
    def git(*args):
        subprocess.run(["git", "-C", str(depot_git), *args], check=True, capture_output=True)
    (depot_git / "README.md").write_text("# TBT\nSeuls les conseillers valident.\n")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "doc")
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(depot_git), "curseur": sha})
    depot.declarer_source(conn, j, {"type": "CONFLUENCE", "nom": "Wiki", "emplacement": "TBT"})
    sources = depot.sources_du_jumeau(conn, "tbt")
    wiki_id = next(s["id"] for s in depot.toutes_les_sources(conn, "tbt") if s["nom"] == "Wiki")
    wiki = LecteurMemoire("Wiki", "TBT", {"12": {"titre": "Règles", "versions": {"3": ["Seuls les conseillers valident."]}}},
                          systeme="confluence")
    wiki.source_id = wiki_id
    cid = connaissance.proposer(conn, j, sources[0], "APPLIQUE_REGLE", "Seuls les conseillers valident", "BUSINESS_RULE",
                                "app.py", 10, 10, "j", "alice", "m")
    return {"conn": conn, "j": j, "sources": sources, "wiki": wiki, "cid": cid}


def recouper(m, citation, claim_id=None, jumeau=None):
    return connaissance.recouper(m["conn"], jumeau or m["j"], m["sources"], [m["wiki"]], claim_id or m["cid"],
                                 citation, "raison", "alice", "m")


def systemes(m):
    return sorted(p["systeme"] for p in recoupement.a_verifier(m["conn"], "tbt")[0]["preuves"])


@besoin_pg
def test_readme_et_code_font_deux_systemes_mais_m3_seulement_si_recoupe(monde):
    conn, cid = monde["conn"], monde["cid"]
    assert recouper(monde, "README.md#L2-L2") is True
    assert systemes(monde) == ["documentation", "git"]
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M2"  # pas encore recoupé
    c = recoupement.a_verifier(conn, "tbt")[0]
    recoupement._enregistrer(conn, c, "recoupe", "juge", {"git", "documentation"})
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M3"


@besoin_pg
def test_deux_fichiers_de_code_restent_un_seul_systeme(monde):
    with pytest.raises(ValueError, match="pas un recoupement"):
        recouper(monde, "requirements.txt#L1-L1")


@besoin_pg
def test_source_branchee_recoupe_et_est_idempotent(monde):
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is True
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is False
    assert systemes(monde) == ["confluence", "git"]


@besoin_pg
def test_deux_fois_la_meme_preuve_ne_change_rien(monde):
    assert recouper(monde, "README.md#L2") is True
    assert recouper(monde, "README.md#L2-L2") is False


@besoin_pg
def test_refus_meme_systeme_documentation(monde):
    recouper(monde, "README.md#L1-L1")
    # git + documentation : un second fichier de code est accepté, la connaissance a déjà deux systèmes
    assert recouper(monde, "requirements.txt#L1-L1") is True
    # une connaissance prouvée par la seule documentation refuse une autre documentation
    doc = connaissance.proposer(monde["conn"], monde["j"], monde["sources"][0], "DETIENT", "Un guide", "BEHAVIOR",
                                "README.md", 1, 1, "j", "alice", "m")
    with pytest.raises(ValueError, match="pas un recoupement"):
        recouper(monde, "README.md#L2-L2", claim_id=doc)


@besoin_pg
def test_refus_inconnue_autre_jumeau_ou_close(monde):
    conn = monde["conn"]
    with pytest.raises(ValueError, match="inconnue"):
        recouper(monde, "README.md#L1-L1", claim_id=99999)
    depot.creer_jumeau(conn, {**JUMEAU, "id": "autre", "nom": "Autre"})
    with pytest.raises(ValueError, match="inconnue"):
        recouper(monde, "README.md#L1-L1", jumeau=depot.jumeau_par_id(conn, "autre"))
    conn.execute("UPDATE claim SET valide_jusqua = now() WHERE id = %s", (monde["cid"],))
    with pytest.raises(ValueError, match="close"):
        recouper(monde, "README.md#L1-L1")


@besoin_pg
def test_recouper_ne_change_ni_statut_ni_objet(monde):
    avant = monde["conn"].execute("SELECT statut, objet FROM claim WHERE id = %s", (monde["cid"],)).fetchone()
    recouper(monde, "README.md#L2-L2")
    assert monde["conn"].execute("SELECT statut, objet FROM claim WHERE id = %s", (monde["cid"],)).fetchone() == avant


@besoin_pg
@pytest.mark.parametrize("citation", ["README.md#L50-L51", "ABSENT.md#L1", "confluence://TBT/12@3#L9", "n'importe quoi"])
def test_citation_fausse_refusee(monde, citation):
    with pytest.raises((ValueError, LookupError)):
        recouper(monde, citation)


@besoin_pg
def test_connaissances_expose_la_verification(monde):
    conn = monde["conn"]
    assert connaissance.connaissances(conn, "tbt")[0]["verification"] is None
    recoupement._enregistrer(conn, recoupement.a_verifier(conn, "tbt")[0], "selon", "juge", {"git"}, "une source")
    v = connaissance.connaissances(conn, "tbt")[0]["verification"]
    assert v == {"etat": "selon", "methode": "juge", "systemes": ["git"], "raison": "une source"}
