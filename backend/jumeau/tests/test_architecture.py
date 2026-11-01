"""Garde d'architecture : le domaine reste pur, les adapters restent optionnels."""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
DOMAINE = RACINE / "meridian" / "domain"
APPLICATION = RACINE / "meridian" / "application"
PORTS = RACINE / "meridian" / "ports"
SORTANTS = RACINE / "meridian" / "adapters" / "outbound"
INFRA = {
    "fastapi", "starlette", "psycopg", "psycopg2", "motor", "pymongo", "neo4j",
    "redis", "strands", "boto3", "botocore", "requests", "httpx", "jose", "openai",
}


def _imports(chemin: Path) -> set[str]:
    arbre = ast.parse(chemin.read_text())
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            trouves.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            trouves.add(noeud.module.split(".")[0])
    return trouves


def _modules(chemin: Path) -> set[str]:
    arbre = ast.parse(chemin.read_text())
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            trouves.update(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            trouves.add(noeud.module)
    return trouves


def _imports_de_premier_niveau(chemin: Path) -> set[str]:
    arbre = ast.parse(chemin.read_text())
    trouves = set()
    for noeud in arbre.body:
        if isinstance(noeud, ast.Import):
            trouves.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            trouves.add(noeud.module.split(".")[0])
    return trouves


def test_le_domaine_n_importe_aucune_infrastructure():
    for fichier in DOMAINE.rglob("*.py"):
        interdits = _imports(fichier) & INFRA
        assert not interdits, f"{fichier.name} importe {sorted(interdits)}"


def test_le_domaine_ne_depend_pas_du_reste_de_jumeau():
    for fichier in DOMAINE.rglob("*.py"):
        assert "jumeau" not in _imports(fichier), f"{fichier.name} dépend de jumeau"


def test_boto3_reste_un_import_paresseux():
    premier = _imports_de_premier_niveau(RACINE / "meridian" / "adapters" / "outbound" / "aws" / "adapters.py")
    assert "boto3" not in premier and "botocore" not in premier


def test_le_domaine_ne_depend_pas_des_autres_couches():
    for fichier in DOMAINE.rglob("*.py"):
        for module in _modules(fichier):
            assert not module.startswith(
                ("jumeau", "meridian.application", "meridian.ports", "meridian.adapters")
            ), f"{fichier.name} dépend de {module}"


# Dette assumée : ce service d'analyse est encore couplé à auth/boucle_routes/psycopg ; il doit
# recevoir des ports avant de satisfaire la règle. Il reste isolé du reste de l'application.
APPLICATION_EXCEPTIONS = {"analyse_service.py"}


def test_l_application_ne_depend_pas_des_adapters_ni_de_l_infrastructure():
    for fichier in APPLICATION.rglob("*.py"):
        if fichier.name in APPLICATION_EXCEPTIONS:
            continue
        for module in _modules(fichier):
            assert not module.startswith(("jumeau", "meridian.adapters")), (
                f"{fichier.name} dépend de {module}")
            assert module.split(".")[0] not in INFRA, f"{fichier.name} importe {module}"


def test_les_ports_ne_dependent_pas_des_adapters_ni_de_l_infrastructure():
    for fichier in PORTS.rglob("*.py"):
        for module in _modules(fichier):
            assert not module.startswith(("jumeau", "meridian.application", "meridian.adapters")), (
                f"{fichier.name} dépend de {module}")
            assert module.split(".")[0] not in INFRA, f"{fichier.name} importe {module}"


def test_les_adapters_sortants_ne_dependent_pas_de_l_inbound():
    for fichier in SORTANTS.rglob("*.py"):
        for module in _modules(fichier):
            assert not module.startswith("meridian.adapters.inbound"), (
                f"{fichier.name} dépend de {module}")
