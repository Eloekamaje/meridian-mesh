"""Dépendances déclarées dans les manifestes, lues au commit ingéré (complète codebase-memory-mcp).

codebase-memory-mcp relie les dépendances de `requirements.txt` ou `go.mod`, pas celles de `pyproject.toml` ni de
`package.json`. On les lit ici ; l'adaptateur les vérifie ensuite à leur ligne, comme toute autre preuve.
Seules les dépendances d'exécution comptent (pas les outils de développement).
"""
import json
import re
import subprocess

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

MANIFESTES = ("pyproject.toml", "package.json")
MAX_MANIFESTES = 50
NOM_PAQUET = re.compile(r"\s*([A-Za-z0-9_.@/-]+?)\s*(?:\[|[<>=!~;\s]|$)")


def lister(depot, sha):
    r = subprocess.run(["git", "-C", str(depot), "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True,
                       timeout=30)
    chemins = [c for c in r.stdout.splitlines()
               if c.rsplit("/", 1)[-1] in MANIFESTES and "node_modules" not in c.split("/")]
    return sorted(chemins)[:MAX_MANIFESTES]


def _pyproject(texte):
    donnees = tomllib.loads(texte)
    specs = list(donnees.get("project", {}).get("dependencies", []))
    poetry = donnees.get("tool", {}).get("poetry", {}).get("dependencies", {})
    noms = [m.group(1) for m in map(NOM_PAQUET.match, specs) if m]
    return noms + [nom for nom in poetry if nom.lower() != "python"]


def _package_json(texte):
    return list(json.loads(texte).get("dependencies", {}))


def dependances(lire, chemins):
    """Lignes {chemin, paquet} pour l'adaptateur ; un manifeste illisible est ignoré."""
    lignes = []
    for chemin in chemins:
        contenu = lire(chemin)
        if not contenu:
            continue
        try:
            noms = (_pyproject if chemin.endswith(".toml") else _package_json)("\n".join(contenu))
        except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
            continue
        lignes += [{"chemin": chemin, "paquet": nom} for nom in dict.fromkeys(noms)]
    return lignes
