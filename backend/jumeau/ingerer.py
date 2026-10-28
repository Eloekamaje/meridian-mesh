"""Ingestion d'un dépôt Git dans un jumeau : index local → Claims vérifiés → Postgres.

    python -m jumeau.ingerer --jumeau tbt --nom TBT --equipe equipe-tbt --domaine Paiement \\
        --mission "Traite les virements" --depot /chemin/vers/depot
"""
import argparse
import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import psycopg

from jumeau import cbm, depot, manifestes, registre
from jumeau.adaptateur import adapter
from jumeau.source_git import lire_au_sha, sha_courant

ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "phase0-1"}


COPIES = Path(os.environ.get("JUMEAU_COPIES", Path.home() / ".local/share/meridian/copies"))


def branche_courante(chemin_depot):
    """Branche extraite du dépôt (None si tête détachée)."""
    r = subprocess.run(["git", "-C", str(chemin_depot), "symbolic-ref", "--short", "-q", "HEAD"],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip() or None


def copie_au_sha(chemin_depot, sha, jumeau_id, nom=None):
    """Copie de travail du jumeau, détachée au SHA ingéré ; elle reste pour la conversation (index de code).

    Recréée si elle n'appartient pas (ou plus) à ce dépôt. Les liens symboliques versionnés sont retirés :
    l'index ne doit lire que des fichiers du dépôt, jamais une cible hors dépôt.
    """
    copie = COPIES / jumeau_id / (nom or Path(chemin_depot).name)  # une copie par dépôt du jumeau
    git = ["git", "-C", str(chemin_depot)]
    copie.parent.mkdir(parents=True, exist_ok=True)
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


def indexer_au_sha(jumeau_id, chemin_depot, sha):
    """Copie détachée au SHA puis index nommé d'après (jumeau, dépôt, SHA) : refait à l'identique sur toute machine."""
    nom = Path(chemin_depot).name
    copie = copie_au_sha(chemin_depot, sha, jumeau_id, nom)
    return copie, cbm.indexer(copie, cbm.nom_index(jumeau_id, nom, sha))


def ingerer(conn, jumeau, chemin_depot, origine=None):
    """Ingère un dépôt du jumeau. `origine` : branche, url, secret_ref (pour que le gardien sache le relire)."""
    sha = sha_courant(chemin_depot)
    if not sha:
        raise ValueError(f"{chemin_depot} n'est pas un dépôt Git")
    copie, projet = indexer_au_sha(jumeau["id"], chemin_depot, sha)
    try:
        resultats, troncature = cbm.interroger(projet)
    except RuntimeError as e:
        # L'index vit dans le cache du binaire, nommé d'après le commit : l'ingestion le refait, mais si sa
        # relecture échoue il faut le dire clairement (plan de remédiation L0bis.3).
        raise RuntimeError(f"index de code illisible pour {chemin_depot} (projet {projet}) : {e}. "
                           "Relancer l'ingestion reconstruit l'index depuis la copie au SHA.") from e
    lire = lire_au_sha(chemin_depot, sha)
    # Dépendances de pyproject.toml / package.json, que codebase-memory-mcp ne relie pas (dédoublonnées).
    vus = {(r["chemin"], r["paquet"]) for r in resultats["paquets"]}
    resultats["paquets"] += [r for r in manifestes.dependances(lire, manifestes.lister(chemin_depot, sha))
                             if (r["chemin"], r["paquet"]) not in vus]
    claims = adapter(resultats, lire, Path(chemin_depot).name, sha[:12], jumeau["nom"])
    bruts = sum(len(v) for v in resultats.values())
    source = {"nom": Path(chemin_depot).name, "type": "GIT", "emplacement": str(chemin_depot), "curseur": sha,
              "copie": str(copie), "index_code": projet, "branche": branche_courante(chemin_depot), "troncature": troncature or None, **(origine or {})}
    depot.appliquer_schema(conn)
    depot.enregistrer(conn, jumeau, source, claims, {**ACTIVITE, "sha": sha})
    return {"sha": sha, "observations": bruts, "claims": len(claims), "troncature": troncature}


def projeter_au_registre(conn):
    """Rend le jumeau visible dans l'application (Atlas, registre, Flore, Travaux) sans attendre un redémarrage."""
    if not os.environ.get("MONGO_URL"):
        return "registre non mis à jour (MONGO_URL absent)"
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        return f"{asyncio.run(registre.projeter(client[os.environ['DB_NAME']], conn))} jumeau(x) réel(s) au registre"
    finally:
        client.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumeau", required=True)
    p.add_argument("--nom", required=True)
    p.add_argument("--equipe", required=True)
    p.add_argument("--domaine", help="domaine de l'Atlas (défaut : À confirmer)")
    p.add_argument("--mission", help="mission en une phrase")
    p.add_argument("--tenant", default="local")
    p.add_argument("--depot", required=True, type=Path)
    a = p.parse_args()
    jumeau = {"id": a.jumeau, "tenant_id": a.tenant, "nom": a.nom, "equipe": a.equipe,
              "domaine": a.domaine, "mission": a.mission}
    try:
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            print(ingerer(conn, jumeau, a.depot.resolve()))
            print(projeter_au_registre(conn))
    except (ValueError, PermissionError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"ingestion interrompue : {e}")


if __name__ == "__main__":
    main()
