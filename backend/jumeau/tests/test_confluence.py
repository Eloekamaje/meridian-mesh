"""Lecteur Confluence (sans réseau : l'ouverture d'URL est simulée)."""
import base64
import io
import json
import urllib.error
from urllib.parse import parse_qs, urlsplit

import pytest

from jumeau import confluence, github, lecteurs

STOCKAGE = ("<h1>Parcours</h1><p>Seuls les <b>conseillers</b> valident&nbsp;l'ouverture.</p>"
            "<ul><li>Délai : 24 h</li><li>Annexe</li></ul>"
            "<table><tr><th>Canal</th><th>Délai</th></tr><tr><td>Agence</td><td>1 j</td></tr></table>"
            "<script>alert(1)</script><p>Fin</p>")
LIGNES = ["# Parcours", "Seuls les conseillers valident l'ouverture.", "- Délai : 24 h", "- Annexe",
          "Canal | Délai", "Agence | 1 j", "Fin"]


def page(version=7, corps=STOCKAGE, espace="42"):
    return {"id": "123", "title": "Parcours d'ouverture", "spaceId": espace, "version": {"number": version},
            "body": {"storage": {"value": corps}}}


@pytest.fixture
def wiki(monkeypatch):
    """Réponses simulées par chemin (avec ?version= si présent) ; mémorise les requêtes envoyées."""
    reponses, envoyees = {"/wiki/api/v2/spaces": {"results": [{"id": "42", "key": "TBT", "name": "Tableau de bord"}]}}, []

    def ouvrir(requete, timeout):
        envoyees.append(requete)
        u = urlsplit(requete.full_url)
        assert u.scheme == "https" and u.netloc == "banque.atlassian.net"
        corps = reponses[u.path + (f"?version={parse_qs(u.query)['version'][0]}" if "version=" in u.query else "")]
        if isinstance(corps, int):
            raise urllib.error.HTTPError(requete.full_url, corps, "refus", {}, None)
        return io.BytesIO(json.dumps(corps).encode())

    monkeypatch.setenv("JUMEAU_CONFLUENCE_HOTE", "banque.atlassian.net")
    monkeypatch.setattr(confluence, "_ouvrir", ouvrir)
    monkeypatch.setattr(confluence, "resoudre_secret", lambda ref: "ana@banque.fr:tok" if ref else None)
    return reponses, envoyees


@pytest.fixture(autouse=True)
def memoire_vide():
    github._cache.clear()
    github._appels.clear()


def lecteur():
    return confluence.LecteurConfluence("Wiki TBT", "TBT", "vault:r")


def test_html_de_stockage_en_lignes_jamais_execute():
    assert confluence.en_lignes(STOCKAGE) == LIGNES
    assert confluence.en_lignes("") == []


def test_lecture_a_la_derniere_version_puis_a_une_version_ancienne(wiki):
    reponses, envoyees = wiki
    reponses["/wiki/api/v2/pages/123"] = page(7)
    reponses["/wiki/api/v2/pages/123?version=6"] = page(6, "<p>Délai : 48 h</p>")
    lu = lecteur().lire("123", 1, 3)
    assert lu["lignes"] == LIGNES[:3] and lu["version"] == "7"
    assert lu["locator"] == "confluence://TBT/123@7#L1-L3"
    assert lecteur().lire("123", version="6")["lignes"] == ["Délai : 48 h"]
    assert envoyees[0].get_header("Authorization") == "Basic " + base64.b64encode(b"ana@banque.fr:tok").decode()
    assert any("body-format=storage" in r.full_url for r in envoyees)


def test_verifier_une_citation(wiki):
    reponses, _ = wiki
    reponses["/wiki/api/v2/pages/123"] = page(7)
    reponses["/wiki/api/v2/pages/123?version=7"] = page(7)
    reponses["/wiki/api/v2/pages/123?version=6"] = page(6, "<p>Une ligne</p>")
    reponses["/wiki/api/v2/pages/123?version=8"] = 404
    reponses["/wiki/api/v2/pages/999?version=7"] = 404
    reponses["/wiki/api/v2/pages/999"] = 404
    l = lecteur()
    assert l.verifier("confluence://TBT/123@7#L2-L3")
    assert not l.verifier("confluence://TBT/123@7#L2-L30")  # lignes hors page
    assert not l.verifier("confluence://TBT/123@8#L1")  # version que la page n'a pas
    assert not l.verifier("confluence://TBT/123@6#L2")
    assert not l.verifier("confluence://TBT/999@7#L1")  # page absente
    assert not l.verifier("confluence://AUTRE/123@7#L1")  # autre espace


def test_une_page_d_un_autre_espace_est_introuvable(wiki):
    reponses, _ = wiki
    reponses["/wiki/api/v2/pages/123"] = page(7, espace="77")
    with pytest.raises(LookupError):
        lecteur().lire("123")


def test_recherche_bornee_a_l_espace(wiki):
    reponses, envoyees = wiki
    reponses["/wiki/rest/api/search"] = {"results": [
        {"title": "Parcours", "excerpt": "le <b>délai</b>", "content": {"id": "123"}}, {"title": "sans contenu"}]}
    assert lecteur().chercher('délai" or space = "RH') == [{"ref": "123", "titre": "Parcours", "extrait": "le délai"}]
    cql = parse_qs(urlsplit(envoyees[-1].full_url).query)["cql"][0]
    assert cql == 'space="TBT" and text ~ "délai or space = RH"'  # le guillemet injecté est retiré


def test_version_courante_de_l_espace(wiki):
    reponses, _ = wiki
    reponses["/wiki/api/v2/spaces/42/pages"] = {"results": [{"id": "123", "version": {
        "number": 7, "createdAt": "2026-10-01T09:00:00Z"}}]}
    assert lecteur().version_courante() == "123@7:2026-10-01T09:00:00Z"


def test_hote_non_autorise_ou_absent(wiki, monkeypatch):
    monkeypatch.setenv("JUMEAU_CONFLUENCE_HOTE", "evil.example.com/x")
    with pytest.raises(github.Invalide):
        lecteur().chercher("a")
    monkeypatch.delenv("JUMEAU_CONFLUENCE_HOTE")
    with pytest.raises(github.Invalide):
        lecteur().chercher("a")


def test_pas_de_redirection():
    assert confluence._SansRedirection().redirect_request(None, None, 302, "", {}, "https://ailleurs") is None


def test_jeton_refuse_sans_fuite_et_identifiants_mal_formes(wiki):
    reponses, _ = wiki
    reponses["/wiki/rest/api/user/current"] = 401
    with pytest.raises(github.JetonRefuse) as e:
        confluence.compte_du_jeton("ana@banque.fr:secret-tok")
    assert "secret-tok" not in str(e.value)
    for mauvais in ("sans-deux-points", "ana@banque.fr:t\nInjecte: 1", ""):
        with pytest.raises(github.Invalide):
            confluence.compte_du_jeton(mauvais)
    with pytest.raises(github.Invalide):
        confluence.identifiants("ana@banque.fr:x", "tok")


def test_debit_limite_par_jeton(wiki):
    reponses, envoyees = wiki
    reponses["/wiki/rest/api/search"] = {"results": []}
    for _ in range(github.MAX_APPELS_MINUTE):
        lecteur().chercher("a")
    with pytest.raises(github.TropDeDemandes):
        lecteur().chercher("a")
    assert len(envoyees) == github.MAX_APPELS_MINUTE


def test_espaces_filtres_et_connexion_declaree(wiki):
    reponses, _ = wiki
    reponses["/wiki/rest/api/user/current"] = {"displayName": "Ana"}
    assert confluence.espaces("vault:r", "tableau") == [{"cle": "TBT", "nom": "Tableau de bord"}]
    assert confluence.espaces("vault:r", "zzz") == []
    assert confluence.compte_du_jeton("ana@banque.fr:tok") == {"login": "ana@banque.fr", "nom": "Ana"}


def test_fabrique_depuis_une_ligne_de_source():
    ligne = {"type": "CONFLUENCE", "nom": "Wiki TBT", "emplacement": "TBT", "secret_ref": "vault:r"}
    [l] = lecteurs.lecteurs_de([ligne, {"type": "GIT"}])
    assert (l.systeme, l.espace, l.nature) == ("confluence", "TBT", "documentation")


def test_test_de_connexion(wiki):
    reponses, _ = wiki
    assert confluence.tester({"secret": "vault:r", "espace": "TBT"})["statut"] == "prete"
    assert confluence.tester({"secret": "vault:r", "espace": "NOPE"})["statut"] == "perimetre_vide"
    assert confluence.tester({"secret": "vault:r"})["statut"] == "configuration_incomplete"
    assert confluence.tester({"espace": "TBT"})["statut"] == "autorisation_insuffisante"
    reponses["/wiki/api/v2/spaces"] = 401
    github._cache.clear()
    assert confluence.tester({"secret": "vault:r", "espace": "TBT"})["statut"] == "autorisation_insuffisante"
