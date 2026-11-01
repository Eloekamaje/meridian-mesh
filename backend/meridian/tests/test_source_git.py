"""Lecture d'un dépôt Git au SHA et extrait vérifié d'une preuve."""
import hashlib
import subprocess

import pytest

from meridian.adapters.outbound.connectors.source_git import extrait, lire_au_sha, sha_courant


@pytest.fixture
def depot(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "requirements.txt").write_text("fastapi==1\nmotor==3\nuvicorn==1\n")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return tmp_path


def test_lire_au_sha_ignore_les_modifications_non_commitees(depot):
    sha = sha_courant(depot)
    (depot / "requirements.txt").write_text("autre\n")
    assert lire_au_sha(depot, sha)("requirements.txt") == ["fastapi==1", "motor==3", "uvicorn==1"]


def test_lire_au_sha_fichier_absent(depot):
    assert lire_au_sha(depot, sha_courant(depot))("absent.txt") is None


def test_extrait_marque_les_lignes_citees_et_verifie_le_hash(depot):
    preuve = {"emplacement": str(depot), "sha": sha_courant(depot), "chemin": "requirements.txt",
              "ligne_debut": 2, "ligne_fin": 2, "hash": hashlib.sha256(b"motor==3").hexdigest()}
    e = extrait(preuve, contexte=1)
    assert e["integre"] is True
    assert [(l["n"], l["citee"]) for l in e["lignes"]] == [(1, False), (2, True), (3, False)]


def test_extrait_signale_une_preuve_alteree(depot):
    preuve = {"emplacement": str(depot), "sha": sha_courant(depot), "chemin": "requirements.txt",
              "ligne_debut": 2, "ligne_fin": 2, "hash": "autre"}
    assert extrait(preuve)["integre"] is False


def commiter(depot, nom, contenu):
    (depot / nom).write_bytes(contenu)
    subprocess.run(["git", "-C", str(depot), "add", "."], check=True)
    subprocess.run(["git", "-C", str(depot), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", nom], check=True)


def test_fichier_non_utf8_lisible(depot):
    commiter(depot, "latin1.txt", "café\n".encode("latin-1"))
    assert len(lire_au_sha(depot, sha_courant(depot))("latin1.txt")) == 1


def test_numerotation_comme_git_malgre_un_saut_de_page(depot):
    commiter(depot, "ff.c", b"a\n\x0c\nb\n")
    assert lire_au_sha(depot, sha_courant(depot))("ff.c") == ["a", "\x0c", "b"]


def test_fichier_trop_gros_non_lu(depot, monkeypatch):
    monkeypatch.setattr("meridian.adapters.outbound.connectors.source_git.TAILLE_MAX", 5)
    assert lire_au_sha(depot, sha_courant(depot))("requirements.txt") is None


def test_sha_avec_retour_ligne_refuse(depot):
    with pytest.raises(ValueError):
        lire_au_sha(depot, sha_courant(depot) + "\n")("requirements.txt")


@pytest.mark.parametrize("sha,chemin", [("--output=/tmp/x", "a"), ("abc123", "-x"), ("abc123", "../hors")])
def test_extrait_refuse_les_arguments_dangereux(depot, sha, chemin):
    preuve = {"emplacement": str(depot), "sha": sha, "chemin": chemin, "ligne_debut": 1, "ligne_fin": 1, "hash": ""}
    with pytest.raises(ValueError):
        extrait(preuve)


def test_copie_sans_liens_symboliques(depot_git, tmp_path, monkeypatch):
    import os
    from meridian.adapters.outbound.connectors import ingerer
    os.symlink("/etc/hostname", depot_git / "lien")
    commiter(depot_git, "rien.txt", b"x\n")
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    copie = ingerer.copie_au_sha(depot_git, sha_courant(depot_git), "tbt")
    assert (copie / "requirements.txt").exists() and not (copie / "lien").is_symlink()


def test_copie_recreee_si_le_depot_change(depot_git, tmp_path, monkeypatch):
    import shutil
    import subprocess
    from meridian.adapters.outbound.connectors import ingerer
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    ingerer.copie_au_sha(depot_git, sha_courant(depot_git), "tbt")
    autre = tmp_path / "autre"
    shutil.copytree(depot_git, autre)
    subprocess.run(["git", "-C", str(autre), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "nouveau"], check=True)
    sha = sha_courant(autre)
    copie = ingerer.copie_au_sha(autre, sha, "tbt")
    assert sha_courant(copie) == sha


def test_une_copie_par_depot_du_meme_jumeau(depot_git, tmp_path, monkeypatch):
    from meridian.adapters.outbound.connectors import ingerer
    monkeypatch.setattr(ingerer, "COPIES", tmp_path / "copies")
    a = ingerer.copie_au_sha(depot_git, sha_courant(depot_git), "tbt", "api")
    b = ingerer.copie_au_sha(depot_git, sha_courant(depot_git), "tbt", "front")
    assert a != b and a.parent == b.parent == tmp_path / "copies" / "tbt"


def test_branche_courante_du_depot(depot_git):
    from meridian.adapters.outbound.connectors import ingerer
    import subprocess as sp
    attendu = sp.run(["git", "-C", str(depot_git), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
    assert ingerer.branche_courante(depot_git) == attendu
