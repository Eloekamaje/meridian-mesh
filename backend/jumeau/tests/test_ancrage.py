"""Ancrer les connaissances de source au code : refus, idempotence, ancrage Jira par l'historique, maturité intacte."""
import subprocess

import pytest

from jumeau import agent, connaissance, depot, temps
from jumeau.source_git import sha_courant
from jumeau.tests.conftest import ACTIVITE, JUMEAU, besoin_pg, claim
from jumeau.tests.test_agent import CONTEXTE, modele_factice
from jumeau.tests.test_temps import commit

JIRA = {"nom": "Jira TBT", "type": "JIRA", "emplacement": "jira://TBT", "curseur": "v1"}


def source_code(depot_git, id_=1):
    return {"id": id_, "nom": "tbt", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}


def preuve_jira(cle="TBT-12"):
    return {"locator": f"jira://TBT/{cle}@v1#L1-L2", "chemin": cle, "sha": "v1", "ligne_debut": 1, "ligne_fin": 2,
            "citation": "plafond", "hash": "h", "type": "JIRA"}


def claim_jira(cle="TBT-12"):
    c = claim("Plafond relevé")
    return {**c, "predicat": "APPLIQUE_REGLE", "preuves": [preuve_jira(cle)]}


# --- sans base ---------------------------------------------------------------------------------

def test_citation_fausse_ou_mal_formee_refusee_avant_toute_ecriture(depot_git):
    sources = [source_code(depot_git)]
    for mauvaise in ("app.py#L900-L910", "absent.py#L1-L2", "pas une citation", "app.py#L5-L2"):
        with pytest.raises((ValueError, LookupError)):
            connaissance.ancrer(None, JUMEAU, sources, 1, mauvaise, "raison")


def test_commits_citant_un_ticket_sans_confondre_les_cles(depot_git):
    commit(depot_git, "regles.py", "P = 1\n", "TBT-12 plafond de virement", "2026-09-01T10:00:00")
    commit(depot_git, "autre.py", "x = 1\n", "TBT-123 autre sujet", "2026-09-02T10:00:00")
    source = source_code(depot_git)
    assert [c["fichiers"] for c in temps.commits_citant(source, "TBT-12")] == [["regles.py"]]
    with pytest.raises(ValueError):
        temps.commits_citant(source, "--all")


def test_outil_refus_en_texte_et_plafond(monkeypatch):
    def refus(*_):
        raise LookupError("introuvable")
    monkeypatch.setattr(agent, "ancrer_code", refus)
    monkeypatch.setattr(agent.psycopg, "connect", lambda *a, **k: __import__("contextlib").nullcontext())
    o = {t.tool_name: t for t in agent.outils(CONTEXTE, "dsn", "m", agent.Budget(propositions=1))}
    assert "Ancrage refusé : introuvable" in o["ancrer_connaissance"](connaissance=1, citation_code="a.py#L1", raison="r")
    assert "Plafond" in o["ancrer_connaissance"](connaissance=1, citation_code="a.py#L1", raison="r")


def test_outil_present_seulement_avec_du_code():
    avec = {t.tool_name for t in agent.outils(CONTEXTE, "dsn", "m", agent.Budget())}
    sans = {t.tool_name for t in agent.outils({**CONTEXTE, "sources": []}, "dsn", "m", agent.Budget())}
    assert "ancrer_connaissance" in avec and "ancrer_connaissance" not in sans


# --- avec Postgres -----------------------------------------------------------------------------

@pytest.fixture
def monde(conn, depot_git):
    """Un dépôt de code ingéré (claim de code) et une source Jira dont un claim est prouvé par TBT-12."""
    commit(depot_git, "regles.py", "PLAFOND = 500\n", "TBT-12 plafond de virement", "2026-09-01T10:00:00")
    code = {"nom": "tbt", "type": "GIT", "emplacement": str(depot_git), "curseur": sha_courant(depot_git)}
    depot.enregistrer(conn, JUMEAU, code, [claim("motor")], ACTIVITE)
    depot.enregistrer(conn, JUMEAU, JIRA, [claim_jira()], ACTIVITE)
    ids = {c["objet"]: c["id"] for c in depot.lister_claims(conn, "tbt")}
    sources = [{**code, "id": depot.source_du_jumeau(conn, "tbt", "tbt")["id"]}]
    return sources, ids


@besoin_pg
def test_ancrage_agent_idempotent_et_maturite_inchangee(conn, monde):
    sources, ids = monde
    avant = next(c for c in depot.lister_claims(conn, "tbt") if c["id"] == ids["Plafond relevé"])
    assert connaissance.ancrer(conn, JUMEAU, sources, ids["Plafond relevé"], "regles.py#L1-L1", "règle de plafond")
    assert not connaissance.ancrer(conn, JUMEAU, sources, ids["Plafond relevé"], "tbt:regles.py#L1", "encore")
    apres = next(c for c in depot.lister_claims(conn, "tbt") if c["id"] == ids["Plafond relevé"])
    assert (apres["maturite"], len(apres["preuves"])) == (avant["maturite"], len(avant["preuves"])) == ("M2", 1)
    [a] = apres["ancres"]
    assert (a["chemin"], a["ligne_debut"], a["ligne_fin"], a["origine"]) == ("regles.py", 1, 1, "AGENT")


@besoin_pg
def test_ancrage_refuse_connaissance_de_code_inconnue_ou_etrangere(conn, monde):
    sources, ids = monde
    with pytest.raises(ValueError):
        connaissance.ancrer(conn, JUMEAU, sources, ids["motor"], "regles.py#L1", "r")  # prouvée par le code seul
    with pytest.raises(ValueError):
        connaissance.ancrer(conn, JUMEAU, sources, 9999, "regles.py#L1", "r")
    with pytest.raises(ValueError):
        connaissance.ancrer(conn, {**JUMEAU, "id": "autre"}, sources, ids["Plafond relevé"], "regles.py#L1", "r")


@besoin_pg
def test_ancrage_jira_par_l_historique_git(conn, monde):
    sources, ids = monde
    assert connaissance.ancrer_jira(conn, JUMEAU, sources) == 1
    assert connaissance.ancrer_jira(conn, JUMEAU, sources) == 0  # rejouable
    claims = {c["id"]: c for c in depot.lister_claims(conn, "tbt")}
    [a] = claims[ids["Plafond relevé"]]["ancres"]
    assert (a["chemin"], a["origine"]) == ("regles.py", "HARNESS") and "TBT-12" in a["raison"]
    assert claims[ids["Plafond relevé"]]["maturite"] == "M2" and claims[ids["motor"]]["ancres"] == []


@besoin_pg
def test_une_ancre_ne_fait_pas_une_preuve_croisee(conn, monde):
    sources, ids = monde
    connaissance.ancrer_jira(conn, JUMEAU, sources)
    n = conn.execute("SELECT count(*) FROM claim_preuve WHERE claim_id = %s", (ids["Plafond relevé"],)).fetchone()[0]
    assert n == 1  # le fichier ancré n'est pas devenu une preuve : pas de M3 (deux systèmes)
