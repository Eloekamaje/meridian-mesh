"""L'adresse du site est une donnée de la connexion : validée par éditeur, portée jusqu'au lecteur (sans réseau)."""
import argparse
import asyncio
import io
import json
import os
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException

from meridian.adapters.outbound.connectors import atlassian
from meridian.adapters.outbound.connectors import confluence
from meridian.adapters.outbound.connectors import datadog
from meridian.adapters.outbound.connectors import essai_source
from meridian.adapters.outbound.connectors import jira
from meridian.adapters.outbound.connectors import lecteurs
from meridian.adapters.outbound.connectors import servicenow
from meridian.adapters.outbound.connectors.github import Invalide

VARIABLES = {"confluence": "JUMEAU_CONFLUENCE_HOTE", "jira": "JUMEAU_JIRA_HOTE",
             "servicenow": "JUMEAU_SERVICENOW_HOTE", "datadog": "JUMEAU_DATADOG_HOTE"}
MODULES = {"confluence": confluence, "jira": jira, "servicenow": servicenow, "datadog": datadog}
VALIDES = {"confluence": "banque.atlassian.net", "jira": "banque.atlassian.net",
           "servicenow": "banque.service-now.com", "datadog": "api.datadoghq.eu"}


@pytest.fixture(autouse=True)
def sans_politique(monkeypatch):
    for v in VARIABLES.values():
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("systeme", VALIDES)
def test_hote_du_site_accepte_et_normalise(systeme):
    hote = VALIDES[systeme]
    f = MODULES[systeme].hote_autorise
    assert f(hote) == hote
    assert f(f"  HTTPS://{hote.upper()}:443/wiki/spaces/X?a=1 ") == hote


@pytest.mark.parametrize("systeme,mauvais", [
    ("confluence", "evil.example.com"), ("confluence", "atlassian.net"), ("confluence", "x.atlassian.net.evil.com"),
    ("jira", "banque.service-now.com"), ("jira", "127.0.0.1"), ("jira", "localhost"),
    ("servicenow", "banque.atlassian.net"), ("servicenow", "service-now.com.evil.fr"),
    ("datadog", "api.datadoghq.com.evil.fr"), ("datadog", "app.datadoghq.eu"), ("datadog", "banque.atlassian.net"),
    ("confluence", "http://banque.atlassian.net"), ("confluence", "user@banque.atlassian.net"), ("jira", "")])
def test_hote_hors_de_l_editeur_refuse(systeme, mauvais):
    with pytest.raises(Invalide):
        MODULES[systeme].hote_autorise(mauvais)


def test_datadog_sites_officiels():
    for site in ("api.datadoghq.com", "api.datadoghq.eu", "api.us3.datadoghq.com", "api.us5.datadoghq.com",
                 "api.ap1.datadoghq.com", "api.ddog-gov.com"):
        assert datadog.hote_autorise(site) == site


@pytest.mark.parametrize("systeme", VALIDES)
def test_la_politique_de_l_organisation_reste_prioritaire(systeme, monkeypatch):
    m = MODULES[systeme]
    monkeypatch.setenv(VARIABLES[systeme], "interne.banque.fr")
    assert m.hote_autorise("interne.banque.fr") == "interne.banque.fr"
    assert m.hote_autorise(None) == "interne.banque.fr"
    with pytest.raises(Invalide):
        m.hote_autorise(VALIDES[systeme])  # valide chez l'éditeur, mais pas celui de l'organisation


@pytest.mark.parametrize("systeme", VALIDES)
def test_connexion_ancienne_sans_hote_retombe_sur_l_environnement(systeme, monkeypatch):
    m = MODULES[systeme]
    with pytest.raises(Invalide):
        m.hote_autorise(None)
    monkeypatch.setenv(VARIABLES[systeme], VALIDES[systeme])
    assert m.hote_autorise(None) == m.hote_autorise("") == VALIDES[systeme]


class Reseau:
    """Ouverture d'URL simulée : consigne les hôtes interrogés."""
    def __init__(self, reponses):
        self.reponses, self.hotes = reponses, []

    def __call__(self, requete, timeout):
        u = urlsplit(requete.full_url)
        assert u.scheme == "https"
        self.hotes.append(u.netloc)
        return io.BytesIO(json.dumps(self.reponses[u.path]).encode())


def test_confluence_le_compte_et_les_perimetres_passent_par_l_hote_de_la_connexion(monkeypatch):
    reseau = Reseau({"/wiki/rest/api/user/current": {"accountId": "5f1a", "displayName": "Ana", "email": "ana@banque.fr"},
                     "/wiki/api/v2/spaces": {"results": [{"id": "42", "key": "TBT", "name": "Tableau"}]}})
    monkeypatch.setattr(confluence, "_ouvrir", reseau)
    monkeypatch.setattr(confluence, "resoudre_secret", lambda ref: "ana@banque.fr:tok")
    assert confluence.compte_du_jeton("ana@banque.fr:tok", "banque.atlassian.net")["compte"] == "5f1a"
    assert confluence.perimetres("vault:r1", "", "banque.atlassian.net") == [{"cle": "TBT", "nom": "Tableau"}]
    assert set(reseau.hotes) == {"banque.atlassian.net"}


def test_confluence_hote_refuse_avant_tout_appel(monkeypatch):
    reseau = Reseau({})
    monkeypatch.setattr(confluence, "_ouvrir", reseau)
    with pytest.raises(Invalide):
        confluence.compte_du_jeton("ana@banque.fr:tok", "evil.example.com")
    assert reseau.hotes == []


def test_jira_hote_porte_de_la_source_declaree_au_lecteur_et_au_test(monkeypatch):
    reseau = Reseau({"/rest/api/3/project/PAY": {"key": "PAY"},
                     "/rest/api/3/search/jql": {"issues": []}})
    monkeypatch.setattr(jira, "_ouvrir", reseau)
    monkeypatch.setattr(jira, "resoudre_secret", lambda ref: "ana@banque.fr:tok")
    config = {"projet": "PAY", "secret": "vault:j", "hote": "Banque.Atlassian.NET"}
    ligne = jira.source_de(config)
    assert ligne["url"] == "https://banque.atlassian.net/projects/PAY"
    lecteur = lecteurs.lecteurs_de([{**ligne, "id": "s1"}])[0]
    assert lecteur.version_courante() == ""
    assert jira.tester(config)["statut"] == "prete"
    assert set(reseau.hotes) == {"banque.atlassian.net"}


def test_servicenow_source_portee_jusqu_au_lecteur(monkeypatch):
    reseau = Reseau({"/api/now/table/incident": {"result": []}, "/api/now/table/problem": {"result": []},
                     "/api/now/table/change_request": {"result": []}})
    monkeypatch.setattr(servicenow, "_ouvrir", reseau)
    monkeypatch.setattr(servicenow, "resoudre_secret", lambda ref: "ana:mdp")
    ligne = servicenow.source_de({"ci": "TBT", "secret": "vault:s", "hote": "banque.service-now.com"})
    assert ligne["url"] == "https://banque.service-now.com/"
    lecteurs.lecteurs_de([ligne])[0].version_courante()
    assert set(reseau.hotes) == {"banque.service-now.com"}


def test_datadog_source_portee_jusqu_au_lecteur(monkeypatch):
    reseau = Reseau({"/api/v1/service_dependencies": {"tbt": {"calls": []}}})
    monkeypatch.setattr(datadog, "_ouvrir", reseau)
    monkeypatch.setattr(datadog, "resoudre_secret", lambda ref: "a" * 32 + ":" + "b" * 40)
    ligne = datadog.source_de({"service": "tbt", "secret": "vault:d", "hote": "api.datadoghq.eu"})
    assert ligne["url"] == "https://app.datadoghq.eu/apm/services/tbt"
    lecteur = lecteurs.lecteurs_de([ligne])[0]
    assert lecteur._lire("dependances", None) is not None
    assert set(reseau.hotes) == {"api.datadoghq.eu"}


def test_source_de_ancienne_connexion_sans_hote_utilise_l_environnement(monkeypatch):
    monkeypatch.setenv("JUMEAU_JIRA_HOTE", "banque.atlassian.net")
    assert jira.source_de({"projet": "PAY", "secret": "vault:j"})["url"] == "https://banque.atlassian.net/projects/PAY"


def test_source_de_hote_invalide_refuse():
    with pytest.raises(Invalide):
        jira.source_de({"projet": "PAY", "secret": "vault:j", "hote": "evil.example.com"})


# --- serveur -------------------------------------------------------------------------------------------------------
from meridian.tests.test_connexions import monde, server, systeme_factice
import types  # noqa: E402


def zed(**en_plus):
    appels = {}
    def hote_autorise(hote=None):
        if hote and "evil" in hote:
            raise Invalide("hôte refusé")
        return (hote or "").strip().lower() or "env.banque.fr"
    def compte(secret, hote=None):
        appels["compte"] = hote
        return {"login": "Ana@Banque.fr", "compte": "5f1a", "nom": "Ana"}
    def perimetres(reference, q, hote=None):
        appels["perimetres"] = hote
        return [{"cle": "P", "nom": "x"}]
    return types.SimpleNamespace(**{**vars(systeme_factice()), "hote_autorise": hote_autorise, "compte_du_jeton": compte,
                                    "perimetres": perimetres, **en_plus}), appels


def test_la_declaration_conserve_l_hote_a_cote_du_jeton_pas_dans_vault(monde, monkeypatch):
    base, deposes = monde
    module, appels = zed()
    monkeypatch.setitem(server.SYSTEMES, "zed", module)
    doc = asyncio.run(server.declarer_connexion(
        "zed", server.JetonAtlassian(hote=" Banque.Zed.NET ", email="ana@banque.fr", jeton="t")))
    assert doc["hote"] == "banque.zed.net" and appels["compte"] == "banque.zed.net"
    assert base["connexions_zed"].docs[doc["id"]]["hote"] == "banque.zed.net"
    assert list(deposes) == [f"connexions/zed/{doc['id']}"]
    asyncio.run(server.perimetres_connexion("zed", doc["id"], ""))
    assert appels["perimetres"] == "banque.zed.net"


def test_hote_refuse_ne_conserve_rien_et_ne_depose_rien(monde, monkeypatch):
    base, deposes = monde
    monkeypatch.setitem(server.SYSTEMES, "zed", zed()[0])
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.declarer_connexion("zed", server.JetonAtlassian(hote="evil.example.com", email="a@b.fr", jeton="t")))
    assert e.value.status_code == 400 and not deposes and not base["connexions_zed"].docs


def test_connexion_ancienne_sans_hote_perimetres_sans_hote(monde, monkeypatch):
    base, _ = monde
    module, appels = zed()
    monkeypatch.setitem(server.SYSTEMES, "zed", module)
    base["connexions_zed"].docs["zz-vieille"] = {"id": "zz-vieille", "reference": "vault:v"}
    asyncio.run(server.perimetres_connexion("zed", "zz-vieille", ""))
    assert appels["perimetres"] is None


def test_la_source_recoit_l_hote_de_sa_connexion_jamais_celui_du_client():
    s = {"connecteur": "jira", "config": {"connexion": "jr-ana", "hote": "evil.example.com"}}
    protegee = server._proteger_source(s, {"jr-ana": "vault:j"}, {"jr-ana": "banque.atlassian.net"})
    assert protegee["config"]["hote"] == "banque.atlassian.net"
    sans = server._proteger_source(s, {"jr-ana": "vault:j"}, {})
    assert sans["config"]["hote"] == ""
    autre = server._proteger_source({**s, "config": {"connexion": "cf-x"}}, {"cf-x": "vault:c"}, {"cf-x": "h.atlassian.net"})
    assert autre["config"]["hote"] == ""  # préfixe d'un autre connecteur


# --- essai_source --connexion --------------------------------------------------------------------------------------
def test_essai_source_lit_hote_et_jeton_de_la_connexion(monkeypatch):
    lu = []
    monkeypatch.setattr(essai_source, "lire_connexion", lambda systeme, cxid: (
        lu.append((systeme, cxid)), {"hote": "banque.atlassian.net", "reference": "vault:meridian/x"})[1])
    monkeypatch.setattr(essai_source, "resoudre_secret", lambda ref: "ana@banque.fr:tok")
    reseau = Reseau({"/rest/api/3/myself": {"accountId": "5f1a", "displayName": "Ana", "emailAddress": "ana@banque.fr"},
                     "/rest/api/3/project/search": {"values": []}})
    monkeypatch.setattr(jira, "_ouvrir", reseau)
    monkeypatch.setattr(jira, "resoudre_secret", lambda ref: "ana@banque.fr:tok")
    lignes = []
    code = essai_source.executer(argparse.Namespace(systeme="jira", hote=None, perimetre="PAY", secret=None,
                                                    terme=None, connexion="jr-ana"), lignes.append)
    assert lu == [("jira", "jr-ana")] and lignes[0].startswith("OK     authentification")
    assert code == 1 and set(reseau.hotes) == {"banque.atlassian.net"}  # l'étape suivante échoue : projet absent


def test_essai_source_connexion_inconnue_n_appelle_rien(monkeypatch):
    monkeypatch.setattr(essai_source, "lire_connexion", lambda systeme, cxid: None)
    lignes = []
    code = essai_source.executer(argparse.Namespace(systeme="jira", hote=None, perimetre="PAY", secret=None,
                                                    terme=None, connexion="jr-x"), lignes.append)
    assert code == 2 and "jr-x" in lignes[0] and "Aucun appel" in lignes[0]


def test_declaration_sur_un_site_inexistant_dit_d_abord_l_adresse(monkeypatch):
    # Constaté : « Élément introuvable dans Confluence » pour une adresse de site qui n'existe pas.
    import asyncio
    import server
    from fastapi import HTTPException

    async def introuvable(*a):
        raise HTTPException(404, "Élément introuvable dans Confluence")
    monkeypatch.setattr(server, "_appel_service", introuvable)
    try:
        asyncio.run(server.declarer_connexion("confluence", server.JetonAtlassian(
            hote="banque-inexistante.atlassian.net", email="a@b.fr", jeton="x")))
    except HTTPException as e:
        assert e.status_code == 404 and "Aucun site Confluence à l'adresse banque-inexistante.atlassian.net" in e.detail
    else:
        raise AssertionError("une erreur était attendue")
