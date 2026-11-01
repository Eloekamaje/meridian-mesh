"""Recouper : un fichier du dépôt n'est **pas** un second système ; l'agent ajoute une source d'un autre système.

Le plan de remédiation (L1.3) a inversé la règle : un README vivant dans le même commit, écrit par la même équipe,
décrit le code qu'il accompagne — le compter comme indépendant permettait d'atteindre M3 sans avoir jamais mis
deux systèmes en présence."""
import subprocess
from pathlib import Path

import pytest

from meridian.adapters.outbound.llm import agent
from meridian.adapters.outbound.postgres import connaissance
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import recoupement
from meridian.adapters.outbound.connectors.lecteurs import LecteurMemoire
from meridian.tests.conftest import JUMEAU, besoin_pg
from meridian.tests.test_agent import CONTEXTE

CAS_SYSTEME = [("CODE", "README.md", "GIT"), ("CODE", "docs/a/Guide.MDX", "GIT"), ("CODE", "x.rst", "GIT"),
               ("CODE", "x.adoc", "GIT"), ("CODE", "requirements.txt", "GIT"), ("CODE", "app.py", "GIT"),
               ("CODE", "notes.md.bak", "GIT"), ("DOCUMENTATION", "12", "CONFLUENCE"),
               ("DOCUMENTATION", "page.md", "CONFLUENCE"), ("TICKET", "TBT-1", "JIRA")]


def test_systeme_de_preuve_python():
    # Le système est celui de la source, jamais celui du chemin : README.md, Guide.MDX ou x.rst du dépôt sont « git ».
    assert [recoupement.systeme_de_preuve(*c) for c in CAS_SYSTEME] == [
        "git", "git", "git", "git", "git", "git", "git",
        "confluence", "confluence", "jira"]


def test_un_fichier_du_depot_ne_compte_pas_comme_un_second_systeme():
    # Ce cas atteignait M3 avant L1.3 : une ligne de code + le README du même dépôt.
    systemes = {recoupement.systeme_de_preuve("CODE", "backend/server.py", "GIT"),
                recoupement.systeme_de_preuve("CODE", "README.md", "GIT")}
    assert systemes == {"git"}


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
    corps = (Path(__file__).resolve().parents[2] / "meridian" / "application" / "methodes" / "comprendre-application.md").read_text()
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
def test_un_readme_du_depot_ne_donne_pas_un_second_systeme_ni_m3(monde):
    """L1.3 : ce cas donnait M3 (code + README du même commit) ; il n'en donne plus aucune."""
    conn, cid = monde["conn"], monde["cid"]
    with pytest.raises(ValueError, match="pas un recoupement"):
        recouper(monde, "README.md#L2-L2")
    assert systemes(monde) == ["git"]
    # Le seul chemin vers M3 reste une source d'un autre système (ici Confluence), et il faut qu'elle concorde.
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is True
    assert systemes(monde) == ["confluence", "git"]
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M2"  # pas encore recoupé
    recoupement._enregistrer(conn, recoupement.a_verifier(conn, "tbt")[0], "recoupe", "juge", {"confluence", "git"})
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
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is True
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is False


@besoin_pg
def test_un_second_fichier_du_meme_depot_n_est_pas_un_recoupement(monde):
    # Un fichier de plus dans le même dépôt n'est pas une source indépendante : refusé, quel que soit le nombre de
    # systèmes déjà présents (avant L1.5, une connaissance à deux systèmes acceptait tout).
    with pytest.raises(ValueError, match="pas un recoupement"):
        recouper(monde, "requirements.txt#L1-L1")
    assert recouper(monde, "confluence://TBT/12@3#L1-L1") is True
    with pytest.raises(ValueError, match="pas un recoupement"):
        recouper(monde, "requirements.txt#L1-L1")  # toujours refusé, même avec deux systèmes


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
    recouper(monde, "confluence://TBT/12@3#L1-L1")
    assert monde["conn"].execute("SELECT statut, objet FROM claim WHERE id = %s", (monde["cid"],)).fetchone() == avant


@besoin_pg
@pytest.mark.parametrize("citation", ["README.md#L50-L51", "ABSENT.md#L1", "confluence://TBT/12@3#L9", "n'importe quoi"])
def test_citation_fausse_refusee(monde, citation):
    with pytest.raises((ValueError, LookupError)):
        recouper(monde, citation)


@besoin_pg
def test_connaissances_expose_la_verification(monde):
    conn = monde["conn"]
    # Toute connaissance naît avec son état (L1.6) : « en_attente », jamais rien du tout.
    assert connaissance.connaissances(conn, "tbt")[0]["verification"] == {
        "etat": "en_attente", "methode": "aucune", "systemes": [], "raison": None, "forme": None, "citations": []}
    recoupement._enregistrer(conn, recoupement.a_verifier(conn, "tbt")[0], "selon", "juge", {"git"}, "une source")
    v = connaissance.connaissances(conn, "tbt")[0]["verification"]
    assert v == {"etat": "selon", "methode": "juge", "systemes": ["git"], "raison": "une source", "forme": None, "citations": []}
