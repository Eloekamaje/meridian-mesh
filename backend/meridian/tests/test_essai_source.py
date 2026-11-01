"""Essai de source pilote : jamais d'appel sans de quoi le faire, jamais le jeton à l'écran (sans réseau)."""
import argparse

import pytest

from meridian.adapters.outbound.connectors import essai_source
from meridian.tests.test_confluence import STOCKAGE, memoire_vide, page, wiki
from meridian.tests.test_jira import jira_cloud, ticket


@pytest.fixture(autouse=True)
def jeton(monkeypatch):
    monkeypatch.setattr(essai_source, "resoudre_secret", lambda ref: "ana@banque.fr:tok")


def args(**kw):
    return argparse.Namespace(**{"systeme": "confluence", "hote": "banque.atlassian.net", "perimetre": "TBT",
                                 "secret": "vault:r", "terme": None, **kw})


def test_sans_compte_s_arrete_en_disant_ce_qui_manque(monkeypatch):
    monkeypatch.delenv("JUMEAU_JIRA_HOTE", raising=False)
    lignes = []
    code = essai_source.executer(args(systeme="jira", hote=None, perimetre=None, secret=None), lignes.append)
    assert code == 2 and len(lignes) == 1
    assert all(m in lignes[0] for m in ("hôte", "projet Jira", "jeton")) and "Aucun appel" in lignes[0]


def test_confluence_les_six_etapes_passent(wiki):
    reponses, _ = wiki
    reponses["/wiki/rest/api/user/current"] = {"displayName": "Ana", "accountId": "5f1a", "email": "ana@banque.fr"}
    reponses["/wiki/rest/api/search"] = {"results": [{"title": "Parcours", "excerpt": "", "content": {"id": "123"}}]}
    reponses["/wiki/api/v2/pages/123"] = page()
    reponses["/wiki/api/v2/pages/123?version=7"] = page()
    reponses["/wiki/api/v2/spaces/42/pages"] = {"results": [{"id": "123", "version": {"number": 7, "createdAt": "x"}}]}
    lignes = []
    assert essai_source.executer(args(), lignes.append) == 0
    assert [l.split()[0] for l in lignes] == ["OK"] * 6 and "tok" not in " ".join(lignes).replace("Tableau", "")


def test_jira_echec_nomme_l_etape_et_ne_montre_pas_le_jeton(jira_cloud):
    reponses, _ = jira_cloud
    reponses["/rest/api/3/myself"] = 401
    lignes = []
    code = essai_source.executer(args(systeme="jira", perimetre="PAY"), lignes.append)
    assert code == 1 and len(lignes) == 1 and lignes[0].startswith("ÉCHEC  authentification")
    assert "JetonRefuse" in lignes[0] and "tok" not in lignes[0].replace("authentification", "")


def test_jira_les_six_etapes_passent(jira_cloud):
    reponses, _ = jira_cloud
    reponses["/rest/api/3/myself"] = {"accountId": "5f1a", "displayName": "Ana", "emailAddress": "ana@banque.fr"}
    reponses["/rest/api/3/project/search"] = {"values": [{"key": "PAY", "name": "Paiements"}]}
    reponses["/rest/api/3/search/jql"] = {"issues": [ticket()], "isLast": True}
    reponses["/rest/api/3/issue/PAY-12"] = ticket()
    lignes = []
    assert essai_source.executer(args(systeme="jira", perimetre="PAY"), lignes.append) == 0, lignes
    assert [l.split()[0] for l in lignes] == ["OK"] * 6
