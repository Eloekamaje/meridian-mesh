"""Fixtures partagées : une base Postgres jetable (un schéma par test) et un dépôt Git jetable."""
import json
import os
import subprocess
import uuid

import pytest

from jumeau import depot

# Les tests gardent l'extraction locale : les extracteurs sont monkeypatchés dans le processus de test.
os.environ.setdefault("PIECES_EXTRACTION_PROCESSUS", "0")

DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")

JUMEAU = {"id": "tbt", "tenant_id": "banque", "nom": "TBT", "equipe": "equipe-tbt"}
SOURCE = {"nom": "tbt-repo", "type": "GIT", "emplacement": "/depots/tbt", "curseur": "sha1"}
ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "test"}


def claim(objet, sha="sha1", ligne=3):
    return {
        "sujet": "TBT", "predicat": "DEPEND_DE", "objet": objet, "type": "DEPENDENCY", "confiance": 0.85,
        "preuves": [{
            "locator": f"git://tbt@{sha}:requirements.txt#L{ligne}-L{ligne}", "chemin": "requirements.txt",
            "sha": sha, "ligne_debut": ligne, "ligne_fin": ligne, "citation": objet, "hash": "h",
        }],
    }


@pytest.fixture
def conn():
    import psycopg
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}")
        depot.appliquer_schema(c)
        yield c
        c.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def depot_git(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "requirements.txt").write_text("fastapi==1\nmotor==3\nuvicorn==1\n")
    (tmp_path / "app.py").write_text("".join(f"ligne {n}\n" for n in range(1, 401)))
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return tmp_path


@pytest.fixture
def index_jetables(monkeypatch):
    """Un test qui indexe avec le vrai binaire supprime ses index à la fin : ils vivent dans le cache réel de
    codebase-memory, celui que Flore interroge (constaté : 16 index de test accumulés)."""
    from jumeau import cbm
    crees, vrai = [], cbm.indexer
    monkeypatch.setattr(cbm, "indexer", lambda depot, nom: crees.append(vrai(depot, nom)) or crees[-1])
    yield crees
    for projet in crees:
        subprocess.run([os.environ.get("CBM_BIN", "codebase-memory-mcp"), "cli", "--quiet", "delete_project",
                        json.dumps({"project": projet})], capture_output=True, text=True, timeout=120)
