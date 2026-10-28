"""L'index de code se nomme d'après (jumeau, dépôt, commit), jamais d'après un chemin absolu."""
import os
import shutil
import subprocess

import pytest

from jumeau import cbm, depot, ingerer, reindexer
from jumeau.tests.conftest import JUMEAU, besoin_pg

SHA = "0123456789abcdef0123456789abcdef01234567"
SONDE_OK = lambda *a, **k: "{}"  # noqa: E731


def test_le_nom_derive_du_jumeau_du_depot_et_du_commit():
    assert cbm.nom_index("tbt", "api", SHA) == cbm.nom_index("tbt", "api", SHA)  # machine neuve : même nom
    assert cbm.nom_index("tbt", "api", SHA) != cbm.nom_index("tbt", "api", "f" * 40)
    assert cbm.nom_index("tbt", "api", SHA) != cbm.nom_index("autre", "api", SHA)
    assert cbm.nom_index("tbt", "api", SHA) != cbm.nom_index("tbt", "front", SHA)


def test_le_nom_est_sur_et_ne_contient_aucun_chemin():
    nom = cbm.nom_index("Équipe/TBT", "../mon dépôt.v2", SHA)
    assert "/" not in nom and " " not in nom and ".." not in nom and nom.endswith(SHA[:12])


def test_un_index_du_bon_commit_est_lisible():
    source = {"index_code": cbm.nom_index("tbt", "api", SHA), "curseur": SHA}
    assert cbm.indexe(source, appeler=SONDE_OK) is True
    assert cbm.perime(source) is False


def test_un_index_d_un_autre_commit_est_perime_et_jamais_utilise():
    appels = []
    source = {"index_code": cbm.nom_index("tbt", "api", "a" * 40), "curseur": SHA}
    assert cbm.perime(source) is True
    assert cbm.indexe(source, appeler=lambda *a, **k: appels.append(a) or "{}") is False
    assert appels == []  # on ne l'interroge même pas


def test_un_index_au_format_ancien_reste_lisible_jusqu_a_sa_reindexation():
    source = {"index_code": "home-majella-.local-share-meridian-copies-tbt-api", "curseur": SHA}
    assert cbm.perime(source) is False
    assert cbm.indexe(source, appeler=SONDE_OK) is True


def test_indexer_nomme_l_index_et_range_la_base_dans_le_dossier_demande(monkeypatch, tmp_path):
    vu = {}
    monkeypatch.setattr(cbm, "_cli", lambda *a: vu.update(args=a) or {"project": "x"})
    cbm.indexer(tmp_path / "copie", "jum-tbt-api-0123")
    assert vu["args"][-2:] == ("--name", "jum-tbt-api-0123")


def test_le_cache_est_configurable_sans_toucher_celui_de_l_utilisateur(monkeypatch, tmp_path):
    vu = {}
    monkeypatch.setenv("JUMEAU_CBM_CACHE", str(tmp_path / "idx"))
    monkeypatch.setattr(cbm.subprocess, "run", lambda *a, **k: vu.update(env=k.get("env")) or
                        subprocess.CompletedProcess(a, 0, "{}", ""))
    cbm._cli("list_projects")
    assert vu["env"]["CBM_CACHE_DIR"] == str(tmp_path / "idx")


@pytest.fixture
def jumeau_ingere(conn, depot_git, tmp_path, monkeypatch):
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    appels = []
    monkeypatch.setattr(cbm, "indexer", lambda copie, nom: appels.append(nom) or nom)
    monkeypatch.setattr(cbm, "interroger", lambda p: {**{k: [] for k in cbm.REQUETES},
                                                    "paquets": [{"chemin": "requirements.txt", "paquet": "fastapi"}]})
    depot.appliquer_schema(conn)
    ingerer.ingerer(conn, JUMEAU, depot_git)
    return conn, depot_git, appels


@besoin_pg
def test_l_ingestion_enregistre_le_nom_derive_du_commit(jumeau_ingere):
    conn, depot_git, appels = jumeau_ingere
    s = depot.source_du_jumeau(conn, "tbt")
    assert s["index_code"] == cbm.nom_index("tbt", depot_git.name, s["curseur"]) == appels[0]


@besoin_pg
def test_reindexer_est_idempotent_quand_l_index_est_a_jour(jumeau_ingere, monkeypatch):
    conn, _, appels = jumeau_ingere
    monkeypatch.setattr(cbm, "indexe", lambda source, appeler=None: True)
    assert reindexer.reindexer(conn, "tbt") == []
    assert len(appels) == 1  # rien de réindexé


@besoin_pg
def test_reindexer_reconstruit_un_index_perime_ou_ancien(jumeau_ingere, monkeypatch):
    conn, depot_git, appels = jumeau_ingere
    conn.execute("UPDATE source SET index_code = 'home-majella-ancien' WHERE jumeau_id = 'tbt'")
    monkeypatch.setattr(cbm, "indexe", lambda source, appeler=None: False)
    refaits = reindexer.reindexer(conn, "tbt")
    s = depot.source_du_jumeau(conn, "tbt")
    assert refaits == [s["nom"]] and s["index_code"] == cbm.nom_index("tbt", depot_git.name, s["curseur"])


@besoin_pg
def test_reindexer_un_jumeau_sans_depot_le_dit(conn):
    with pytest.raises(ValueError):
        reindexer.reindexer(conn, "inconnu")


@pytest.mark.skipif(not os.environ.get("CBM_BIN"), reason="CBM_BIN non défini")
def test_binaire_reel_deux_caches_neufs_donnent_le_meme_nom(depot_git, tmp_path, monkeypatch):
    sha = subprocess.run(["git", "-C", str(depot_git), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    noms = []
    for cache in ("a", "b"):  # deux « machines neuves »
        monkeypatch.setenv("JUMEAU_CBM_CACHE", str(tmp_path / cache))
        copie = tmp_path / f"copie-{cache}"  # chemins absolus différents
        shutil.copytree(depot_git, copie)
        noms.append(cbm.indexer(copie, cbm.nom_index("tbt", "depot", sha)))
        assert (tmp_path / cache / f"{noms[-1]}.db").exists()
        assert cbm.perime({"index_code": noms[-1], "curseur": sha}) is False
    assert noms[0] == noms[1]
