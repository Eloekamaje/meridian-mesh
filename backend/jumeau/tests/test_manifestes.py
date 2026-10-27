"""Dépendances lues dans les manifestes (pyproject.toml, package.json), au commit ingéré."""
import json
import subprocess

from jumeau import manifestes
from jumeau.adaptateur import adapter
from jumeau.source_git import lire_au_sha, sha_courant

PYPROJECT = '''[project]
name = "app"
dependencies = [
    "fastapi[standard]>=0.141.1,<1.0.0",
    "sqlmodel<1.0.0,>=0.0.21",
]

[project.optional-dependencies]
dev = ["pytest"]
'''
PACKAGE = {"name": "front", "dependencies": {"@tanstack/react-query": "^5", "axios": "^1"},
           "devDependencies": {"vitest": "^1"}}


def deposer(depot_git):
    (depot_git / "backend").mkdir()
    (depot_git / "backend" / "pyproject.toml").write_text(PYPROJECT)
    (depot_git / "frontend").mkdir()
    (depot_git / "frontend" / "package.json").write_text(json.dumps(PACKAGE, indent=2))
    (depot_git / "frontend" / "node_modules").mkdir()
    (depot_git / "frontend" / "node_modules" / "package.json").write_text('{"dependencies": {"ignore": "1"}}')
    subprocess.run(["git", "-C", str(depot_git), "add", "-f", "."], check=True)
    subprocess.run(["git", "-C", str(depot_git), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "m"],
                   check=True)
    return sha_courant(depot_git)


def test_lister_les_manifestes_sans_node_modules(depot_git):
    sha = deposer(depot_git)
    assert manifestes.lister(depot_git, sha) == ["backend/pyproject.toml", "frontend/package.json"]


def test_dependances_d_execution_seulement(depot_git):
    sha = deposer(depot_git)
    lignes = manifestes.dependances(lire_au_sha(depot_git, sha), manifestes.lister(depot_git, sha))
    assert {(l["chemin"], l["paquet"]) for l in lignes} == {
        ("backend/pyproject.toml", "fastapi"), ("backend/pyproject.toml", "sqlmodel"),
        ("frontend/package.json", "@tanstack/react-query"), ("frontend/package.json", "axios")}


def test_manifeste_illisible_ignore():
    fichiers = {"pyproject.toml": ["[project", "dependencies = ["], "package.json": ["{pas du json"]}
    assert manifestes.dependances(fichiers.get, ["pyproject.toml", "package.json"]) == []


def test_chaque_dependance_devient_un_claim_prouve_a_sa_ligne(depot_git):
    sha = deposer(depot_git)
    lire = lire_au_sha(depot_git, sha)
    claims = adapter({"paquets": manifestes.dependances(lire, manifestes.lister(depot_git, sha))}, lire, "app",
                     sha[:12], "App")
    par_objet = {c["objet"]: c["preuves"][0] for c in claims}
    assert par_objet["fastapi"]["ligne_debut"] == 4 and "fastapi[standard]" in par_objet["fastapi"]["citation"]
    assert '"@tanstack/react-query"' in par_objet["@tanstack/react-query"]["citation"]
