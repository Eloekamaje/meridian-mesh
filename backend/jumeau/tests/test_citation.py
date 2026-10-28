"""Un verdict vérifiable (Harness v3 §2) : citation contrôlée, départage par la preuve, température 0 du juge."""
import asyncio
import subprocess

import pytest

from jumeau import agent, depot, recoupement
from jumeau.juge import Appui
from jumeau.tests.conftest import JUMEAU, besoin_pg

EXTRAITS = [{"systeme": "git", "citation": "c1", "lignes": ["if solde < 0:", "    raise  ValueError('x')"]},
            {"systeme": "confluence", "citation": "c2", "lignes": ["Seuls les conseillers valident."]}]


@pytest.mark.parametrize("citation, valide", [
    ("raise ValueError('x')", True),                 # espaces normalisés
    ("SEULS LES CONSEILLERS", True),                 # insensible à la casse
    ("if solde < 0: raise", True),                   # d'une ligne à la suivante
    ("solde", False),                                # trop courte
    ("Les agents valident tout", False),             # introuvable
    ("x" * 301, False),                              # trop longue
])
def test_citation_controlee(citation, valide):
    assert (recoupement.citations_valides([citation], EXTRAITS) == [" ".join(citation.split())]) is valide


def test_citation_d_un_autre_dossier_est_introuvable():
    autre = [{"systeme": "git", "lignes": ["def autre_chose(): pass"]}]
    assert recoupement.citations_valides(["Seuls les conseillers valident."], autre) == []


def test_au_plus_trois_citations_sans_doublon():
    cites = ["Seuls les conseillers", "SEULS LES CONSEILLERS", "if solde < 0:", "valident.", "raise  ValueError",
             "if solde < 0: raise"]
    assert len(recoupement.citations_valides(cites, EXTRAITS)) == 3


def _appui(verdict="oui", citations=()):
    return Appui(id=1, appui=verdict, concordance="une_seule_source", copie=False, raison="r",
                 citations=list(citations))


def test_oui_sans_citation_valide_devient_partiel():
    for citations in ([], ["introuvable dans le dossier"], ["court"]):
        a, valides = recoupement.appui_ancre(_appui("oui", citations), EXTRAITS)
        assert a.appui == "partiel" and a.raison.startswith("[citation absente ou introuvable]") and valides == []
        assert recoupement.etat_du_jugement(a, {"git"}) == "en_partie"


def test_oui_avec_citation_valide_et_partiel_restent():
    a, valides = recoupement.appui_ancre(_appui("oui", ["Seuls les conseillers valident."]), EXTRAITS)
    assert a.appui == "oui" and valides == ["Seuls les conseillers valident."]
    a, _ = recoupement.appui_ancre(_appui("partiel", ["if solde < 0:"]), EXTRAITS)
    assert a.appui == "partiel" and a.raison == "r"
    a, valides = recoupement.appui_ancre(_appui("non"), EXTRAITS)
    assert a.appui == "non" and valides == []


# --- départage -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("avant, apres, preuves_changees, attendu", [
    ("selon", "en_partie", False, "incertain"),
    ("recoupe", "non_appuye", False, "incertain"),
    ("non_appuye", "selon", False, "incertain"),
    ("selon", "en_partie", True, "en_partie"),       # preuves changées : le nouveau verdict s'applique
    ("selon", "recoupe", False, "recoupe"),          # même camp
    ("en_partie", "non_appuye", False, "non_appuye"),
])
def test_depart_par_la_preuve(avant, apres, preuves_changees, attendu):
    ancien = {"etat": avant, "empreinte": "forme1:1,2"}
    c = {"empreinte": "forme2:1,3" if preuves_changees else "forme2:1,2"}
    etat, raison = recoupement.departager(ancien, c, apres, "r")
    assert etat == attendu
    assert raison.startswith("[verdicts divergents sur les mêmes preuves]") == (attendu == "incertain")


def test_depart_sans_verdict_precedent():
    assert recoupement.departager(None, {"empreinte": "1"}, "selon", "r") == ("selon", "r")


# --- température ---------------------------------------------------------------------------------------------------
def test_juge_a_temperature_zero_pas_l_auteur(monkeypatch):
    monkeypatch.setenv("JUMEAU_MODELE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.delenv("JUMEAU_MODELE_JUGE", raising=False)
    assert agent.modele_juge().config["params"] == {"temperature": 0}
    assert not agent.modele().config.get("params")


# --- SQL -----------------------------------------------------------------------------------------------------------
def _passe(conn, j, verdicts, citer=True):
    async def juger(modele, dossiers):
        return {d["id"]: Appui(id=d["id"], appui=verdicts, concordance="une_seule_source", copie=False, raison="r",
                               citations=[" ".join(d["extraits"][0]["lignes"])] if citer else [])
                for d in dossiers}
    return asyncio.run(recoupement.verifier(conn, j, juger=juger))


@besoin_pg
def test_incertain_reste_hypothese_et_citations_enregistrees(conn, depot_git):
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    depot.creer_jumeau(conn, JUMEAU)
    j = depot.jumeau_par_id(conn, "tbt")
    depot.declarer_source(conn, j, {"type": "GIT", "nom": "tbt", "emplacement": str(depot_git), "curseur": sha})
    sid = depot.toutes_les_sources(conn, "tbt")[0]["id"]
    p = {"locator": f"git://tbt@{sha[:12]}:app.py#L10-L10", "chemin": "app.py", "sha": sha, "ligne_debut": 10,
         "ligne_fin": 10, "hash": "h"}
    cid = depot.enregistrer_proposition(conn, j, sid, {"sujet": "TBT", "predicat": "SERT_ACTEUR", "objet": "les conseillers",
                                                       "type": "T", "confiance": 0.5}, p, {"extracteur": "test"})
    assert _passe(conn, j, "oui")["selon"] == 1
    e = recoupement.etats(conn, "tbt")[cid]
    assert e["etat"] == "selon" and len(e["citations"]) == 1
    # Même preuve, nouvelle règle (l'empreinte change de préfixe), verdict de l'autre camp : incertain.
    conn.execute("UPDATE verification SET empreinte = 'forme1:' || empreinte WHERE claim_id = %s", (cid,))
    assert _passe(conn, j, "non")["incertain"] == 1
    e = recoupement.etats(conn, "tbt")[cid]
    assert e["etat"] == "incertain" and e["raison"].startswith("[verdicts divergents")
    assert conn.execute("SELECT maturite FROM claim WHERE id = %s", (cid,)).fetchone()[0] == "M1"
