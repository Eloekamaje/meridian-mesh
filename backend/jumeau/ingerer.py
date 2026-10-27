"""Ingestion d'un dépôt Git dans un jumeau : index local → Claims vérifiés → Postgres.

    python -m jumeau.ingerer --jumeau tbt --nom TBT --equipe equipe-tbt --depot /chemin/vers/depot
"""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import psycopg

from jumeau import cbm, depot
from jumeau.adaptateur import adapter
from jumeau.source_git import lire_au_sha, sha_courant

ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "phase0-1"}


def indexer_au_sha(chemin_depot, sha):
    """Indexe exactement le SHA (worktree détaché et temporaire) : les numéros de ligne collent aux preuves."""
    git = ["git", "-C", str(chemin_depot), "worktree"]
    with tempfile.TemporaryDirectory(prefix="jumeau-") as tmp:
        arbre = Path(tmp) / Path(chemin_depot).name
        subprocess.run([*git, "add", "--detach", str(arbre), sha], check=True, capture_output=True, timeout=120)
        try:
            projet = cbm.indexer(arbre)
            try:
                return cbm.interroger(projet)
            finally:
                cbm.oublier(projet)
        finally:
            subprocess.run([*git, "remove", "--force", str(arbre)], capture_output=True, timeout=120)


def ingerer(conn, jumeau, chemin_depot):
    sha = sha_courant(chemin_depot)
    if not sha:
        raise ValueError(f"{chemin_depot} n'est pas un dépôt Git")
    resultats = indexer_au_sha(chemin_depot, sha)
    claims = adapter(resultats, lire_au_sha(chemin_depot, sha), Path(chemin_depot).name, sha[:12], jumeau["nom"])
    bruts = sum(len(v) for v in resultats.values())
    source = {"nom": Path(chemin_depot).name, "type": "GIT", "emplacement": str(chemin_depot), "curseur": sha}
    depot.appliquer_schema(conn)
    depot.enregistrer(conn, jumeau, source, claims, {**ACTIVITE, "sha": sha})
    return {"sha": sha, "observations": bruts, "claims": len(claims)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    p.add_argument("--nom", required=True)
    p.add_argument("--equipe", required=True)
    p.add_argument("--tenant", default="local")
    p.add_argument("--depot", required=True, type=Path)
    a = p.parse_args()
    jumeau = {"id": a.jumeau, "tenant_id": a.tenant, "nom": a.nom, "equipe": a.equipe}
    try:
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            print(ingerer(conn, jumeau, a.depot.resolve()))
    except (ValueError, PermissionError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"ingestion interrompue : {e}")


if __name__ == "__main__":
    main()
