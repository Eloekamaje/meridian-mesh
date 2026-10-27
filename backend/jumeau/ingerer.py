"""Ingestion d'un dépôt Git dans un jumeau : index local → Claims vérifiés → Postgres.

    python -m jumeau.ingerer --jumeau tbt --nom TBT --equipe equipe-tbt --depot /chemin/vers/depot
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

import psycopg

from jumeau import cbm, depot
from jumeau.adaptateur import adapter
from jumeau.source_git import lire_au_sha, sha_courant

ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "phase0-1"}


COPIES = Path(os.environ.get("JUMEAU_COPIES", Path.home() / ".local/share/meridian/copies"))


def copie_au_sha(chemin_depot, sha, jumeau_id):
    """Copie de travail du jumeau, détachée au SHA ingéré ; elle reste pour la conversation (index de code).

    Recréée si elle n'appartient pas (ou plus) à ce dépôt. Les liens symboliques versionnés sont retirés :
    l'index ne doit lire que des fichiers du dépôt, jamais une cible hors dépôt.
    """
    copie = COPIES / jumeau_id
    git = ["git", "-C", str(chemin_depot)]
    COPIES.mkdir(parents=True, exist_ok=True)
    maj = subprocess.run(["git", "-C", str(copie), "checkout", "--detach", "--force", "-q", sha],
                         capture_output=True, text=True) if (copie / ".git").exists() else None
    if maj is None or maj.returncode != 0 or _depot_de(copie) != _depot_de(chemin_depot):
        shutil.rmtree(copie, ignore_errors=True)
        subprocess.run([*git, "worktree", "prune"], capture_output=True)
        r = subprocess.run([*git, "worktree", "add", "--detach", "--force", str(copie), sha],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"copie au SHA impossible : {r.stderr.strip()}")
    for lien in [p for p in copie.rglob("*") if p.is_symlink() and ".git" not in p.parts]:
        lien.unlink()
    return copie


def _depot_de(chemin):
    r = subprocess.run(["git", "-C", str(chemin), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def ingerer(conn, jumeau, chemin_depot):
    sha = sha_courant(chemin_depot)
    if not sha:
        raise ValueError(f"{chemin_depot} n'est pas un dépôt Git")
    copie = copie_au_sha(chemin_depot, sha, jumeau["id"])
    projet = cbm.indexer(copie)
    resultats = cbm.interroger(projet)
    claims = adapter(resultats, lire_au_sha(chemin_depot, sha), Path(chemin_depot).name, sha[:12], jumeau["nom"])
    bruts = sum(len(v) for v in resultats.values())
    source = {"nom": Path(chemin_depot).name, "type": "GIT", "emplacement": str(chemin_depot), "curseur": sha,
              "copie": str(copie), "index_code": projet}
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
