"""Fixtures partagées : une base Postgres jetable (un schéma par test) et un dépôt Git jetable."""
import os
import subprocess
import uuid

import pytest

from jumeau import depot

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
