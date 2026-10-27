"""API GitHub de l'atelier (sans réseau : l'ouverture d'URL est simulée)."""
import io
import json
import urllib.error

import pytest

from jumeau import github


@pytest.fixture
def forge(monkeypatch):
    """Réponses simulées par chemin ; mémorise les requêtes envoyées."""
    reponses, envoyees = {}, []

    def ouvrir(requete, timeout):
        envoyees.append(requete)
        chemin = requete.full_url.split("api.github.com", 1)[1].split("?")[0]
        corps = reponses[chemin]
        if isinstance(corps, tuple):  # (code HTTP, en-têtes)
            raise urllib.error.HTTPError(requete.full_url, corps[0], "refus", corps[1], None)
        if isinstance(corps, int):
            raise urllib.error.HTTPError(requete.full_url, corps, "refus", {}, None)
        return io.BytesIO(json.dumps(corps).encode())

    monkeypatch.setattr(github, "_ouvrir", ouvrir)
    monkeypatch.setattr(github, "resoudre_secret", lambda ref: "ghp_x" if ref else None)
    return reponses, envoyees


def depot(nom, defaut="main"):
    return {"full_name": nom, "private": True, "default_branch": defaut, "pushed_at": "2026-10-01T00:00:00Z",
            "description": "Paie des employés", "language": "Python"}


def test_depots_filtres_avec_leur_branche_par_defaut(forge):
    reponses, envoyees = forge
    reponses["/user/repos"] = [depot("banque/paie-api"), depot("banque/paie-front", "develop"), depot("banque/crm")]
    assert github.depots("vault:meridian/x#jeton", "PAIE") == [
        {"nom": "banque/paie-api", "prive": True, "defaut": "main", "maj": "2026-10-01T00:00:00Z",
         "description": "Paie des employés", "langage": "Python"},
        {"nom": "banque/paie-front", "prive": True, "defaut": "develop", "maj": "2026-10-01T00:00:00Z",
         "description": "Paie des employés", "langage": "Python"}]
    assert envoyees[0].get_header("Authorization") == "Bearer ghp_x"


def test_branches_d_un_depot(forge):
    reponses, _ = forge
    reponses["/repos/banque/paie-front/branches"] = [{"name": "main"}, {"name": "release/2026-11"}]
    assert github.branches("vault:r", "banque/paie-front", "rel") == ["release/2026-11"]
    with pytest.raises(ValueError):
        github.branches("vault:r", "../etc", "")


def test_jeton_refuse_ou_absent(forge):
    reponses, _ = forge
    reponses["/user"] = 401
    with pytest.raises(github.JetonRefuse):
        github.compte("vault:r")
    with pytest.raises(github.Invalide):
        github.compte(None)
    with pytest.raises(github.Invalide):  # un retour à la ligne finirait cité dans une erreur d'en-tête HTTP
        github.compte_du_jeton("ghp_x\nInjecte: 1")


@pytest.fixture(autouse=True)
def memoire_vide():
    github._cache.clear()
    github._appels.clear()


def test_la_frappe_ne_rappelle_pas_github(forge):
    reponses, envoyees = forge
    reponses["/user/repos"] = [depot("banque/paie-api"), depot("banque/crm")]
    for saisie in ("p", "pa", "pai", "paie"):
        assert [d["nom"] for d in github.depots("vault:r", saisie)] == ["banque/paie-api"]
    assert len(envoyees) == 1  # une seule lecture de la liste, filtrée ensuite sur le serveur


def test_debit_limite_par_jeton(forge, monkeypatch):
    reponses, _ = forge
    reponses["/repos/banque/paie/branches"] = [{"name": "main"}]
    monkeypatch.setattr(github, "CACHE_SECONDES", 0)  # chaque appel va jusqu'à GitHub
    for _ in range(github.MAX_APPELS_MINUTE):
        github.branches("vault:r", "banque/paie")
    with pytest.raises(github.TropDeDemandes):
        github.branches("vault:r", "banque/paie")


def test_nouveau_jeton_oublie_les_reponses_de_l_ancien(forge):
    reponses, envoyees = forge
    reponses["/user/repos"] = [depot("banque/a")]
    github.depots("vault:r")
    github.oublier("vault:r")
    reponses["/user/repos"] = [depot("banque/b")]
    assert [d["nom"] for d in github.depots("vault:r")] == ["banque/b"]


def test_quota_github_epuise_annonce_l_attente(forge, monkeypatch):
    reponses, _ = forge
    monkeypatch.setattr(github.time, "time", lambda: 1000)
    reponses["/user"] = (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1600"})
    with pytest.raises(github.TropDeDemandes, match="10 min"):
        github.compte_du_jeton("ghp_x")


def test_compte_avec_son_avatar(forge):
    reponses, _ = forge
    reponses["/user"] = {"login": "mtl-ci", "name": "Intégration continue", "avatar_url": "https://avatars/x.png"}
    assert github.compte_du_jeton("ghp_x") == {"login": "mtl-ci", "nom": "Intégration continue",
                                                "avatar": "https://avatars/x.png"}
