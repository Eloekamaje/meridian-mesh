"""Ingestion d'un dépôt Git dans un jumeau : index local → Claims vérifiés → Postgres.

    python -m meridian.adapters.outbound.connectors.ingerer --jumeau tbt --nom TBT --equipe equipe-tbt --domaine Paiement \\
        --mission "Traite les virements" --depot /chemin/vers/depot
"""
import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

import psycopg

from meridian.adapters.outbound.connectors import cbm
from meridian.adapters.outbound.postgres import code_index_store, depot
from meridian.adapters.outbound.connectors import index_store
from meridian.adapters.outbound.connectors import legacy_index
from meridian.adapters.outbound.connectors import manifestes
from meridian.adapters.outbound.mongo import registre
from meridian.adapters.outbound.connectors.adaptateur import adapter
from meridian.adapters.outbound.connectors.source_git import lire_au_sha, sha_courant
from meridian.application.exploration_agent import (
    ExplorationHarness, RepoSnapshot, claims_depuis_rapport,
)

ACTIVITE = {"extracteur": "cbm-adaptateur", "version": "phase0-1"}
journal = logging.getLogger(__name__)


COPIES = index_store.copies_dir()
ENQUETES = Path(os.environ.get("JUMEAU_ENQUETE_STATE", Path.home() / ".local/share/meridian/enquetes"))


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


def _fichiers_au_sha(depot, sha):
    resultat = subprocess.run(
        ["git", "-C", str(depot), "ls-tree", "-r", "--name-only", sha],
        capture_output=True, text=True, timeout=30,
    )
    return [ligne for ligne in resultat.stdout.splitlines() if ligne]


def indexer_au_sha(jumeau_id, chemin_depot, sha):
    """Copie détachée au SHA puis index nommé d'après (jumeau, dépôt, SHA) : refait à l'identique sur toute machine."""
    nom = Path(chemin_depot).name
    copie = copie_au_sha(chemin_depot, sha, jumeau_id, nom)
    return copie, cbm.indexer(copie, cbm.nom_index(jumeau_id, nom, sha))


def _magasin():
    """Magasin d'index de la configuration ; construit à chaque ingestion (l'environnement peut changer en test)."""
    return index_store.depuis_env()


def _indexer_avec_artefact(store, tenant, nom, jumeau_id, chemin_depot, sha):
    """(copie, projet, artefact) : restauré depuis le magasin si possible, sinon copie Git + index.

    L'artefact est une copie source au SHA (sans ``.git``). S'il existe, l'index binaire local est réutilisé
    quand il est déjà à ce commit ; sinon la copie restaurée est réindexée. Une copie restaurée n'est pas un
    dépôt Git : ``copie`` vaut alors None et les lecteurs retombent sur `emplacement` (clone du dépôt).
    """
    projet = cbm.nom_index(jumeau_id, nom, sha)
    destination = COPIES / jumeau_id / nom
    if store.has(tenant, nom, sha):
        try:
            if cbm.indexe({"index_code": projet, "curseur": sha}):
                return None, projet, True  # le cache binaire local est déjà à ce commit
            copie = store.restore(tenant, nom, sha, destination, remplacer=True)
            if copie is not None:
                return copie, cbm.indexer(copie, projet), True
        except Exception as e:
            journal.warning("artefact d'index %s/%s/%s illisible, réindexation depuis le dépôt : %s",
                            tenant, nom, sha, e)
    copie, projet = indexer_au_sha(jumeau_id, chemin_depot, sha)
    return copie, projet, False


def _retirer_copie(copie):
    """Zéro-rétention : la copie de travail ne survit pas à l'ingestion (l'index binaire reste, lui, local)."""
    shutil.rmtree(copie, ignore_errors=True)


def _enquete_active(valeur):
    if valeur is not None:
        return bool(valeur)
    return os.environ.get("JUMEAU_ENQUETE", "").strip().lower() in {"1", "true", "oui", "yes"}


def _route_de(claim):
    if str(claim.get("predicat") or "").upper() != "EXPOSE":
        return None
    objet = str(claim.get("objet") or "").strip()
    methode, _, chemin = objet.partition(" ")
    return (methode.upper(), chemin) if methode and chemin.startswith("/") else None


def _filtrer_routes_couvertes(claims, claims_enquete):
    """Une route trouvée par l'enquête (préfixe réel) remplace la même route CBM sans préfixe."""
    routes_enquete = [_route_de(c) for c in claims_enquete]
    routes_enquete = [r for r in routes_enquete if r]
    if not routes_enquete:
        return claims
    gardees = []
    for claim in claims:
        route = _route_de(claim)
        if route and any(route[0] == m and chemin.endswith(route[1])
                         for m, chemin in routes_enquete):
            continue
        gardees.append(claim)
    return gardees


def _enqueter(jumeau, chemin_depot, sha, nom):
    """Lance l'enquête du harness sur le dépôt figé au SHA, sans bloquer l'ingestion en cas de panne."""
    etat = ENQUETES / (jumeau.get("tenant_id") or "local") / jumeau["id"] / nom / sha[:12]
    try:
        from meridian.adapters.outbound.llm.exploration_adapter import ExplorationAdapter
        adaptateur = ExplorationAdapter()
        snapshot = RepoSnapshot.depuis_git(nom, chemin_depot, sha=sha, role="source")
        harness = ExplorationHarness([snapshot], etat)
        objectif = (f"Comprends le dépôt {nom} de l'application {jumeau.get('nom') or jumeau['id']} "
                    "et produis un inventaire sourcé : stacks, points d'entrée, routes, dépendances et inconnues. "
                    "Cite toujours le dépôt, le SHA, le fichier et les lignes.")
        rapport = harness.run(objectif, adaptateur, max_steps=30)
        for claim in claims_depuis_rapport(rapport, jumeau.get("nom") or jumeau["id"], nom):
            harness.executer("record_claim", claim)
        claims = []
        chemin_claims = etat / "claims.json"
        if chemin_claims.exists():
            try:
                valeur = json.loads(chemin_claims.read_text(encoding="utf-8"))
                if isinstance(valeur, list):
                    claims = valeur
            except (OSError, json.JSONDecodeError):
                claims = []
        return {"statut": "terminee", "rapport": str(etat / "report.md"),
                "trace": str(etat / "trace.json"), "claims_path": str(chemin_claims),
                "claims": claims, "resume": rapport[:2000]}
    except Exception as erreur:
        journal.warning("enquête harness impossible pour %s/%s : %s — sortie: %s",
                        jumeau["id"], nom, erreur,
                        getattr(locals().get("adaptateur"), "derniere_sortie", "")[:1000])
        return {"statut": "echec", "erreur": str(erreur)[:500]}


def ingerer(conn, jumeau, chemin_depot, origine=None, *, enquete=None):
    """Ingère un dépôt du jumeau. `origine` : branche, url, secret_ref (pour que le gardien sache le relire)."""
    sha = sha_courant(chemin_depot)
    if not sha:
        raise ValueError(f"{chemin_depot} n'est pas un dépôt Git")
    nom = Path(chemin_depot).name
    tenant = jumeau.get("tenant_id") or "local"
    store = _magasin()
    precedent = (depot.source_du_jumeau(conn, jumeau["id"], nom) or {}).get("index_code")
    copie = None
    try:
        copie, projet, restauree = _indexer_avec_artefact(store, tenant, nom, jumeau["id"], chemin_depot, sha)
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
        routes_cbm = len(resultats.get("routes") or [])
        fichiers = _fichiers_au_sha(chemin_depot, sha)
        claims = adapter(resultats, lire, nom, sha[:12], jumeau["nom"])
        bruts = sum(len(v) for v in resultats.values())
        # L'adaptateur historique garde les quatre Claims structurels compatibles. L'index fédéré, lui,
        # conserve toutes les observations, la couverture explicite et les liens prouvés : il devient le
        # socle d'enquête sans promouvoir aveuglément chaque motif syntaxique en connaissance.
        rapport_code = legacy_index.indexer_legacy(
            copie or chemin_depot, projet_cbm=projet, commit=sha)
        conservee = copie if (copie is not None and not restauree and store.mode != "none") else None
        if store.mode != "none" and copie is not None:
            try:
                store.save(tenant, nom, sha, copie, index_code=projet)
            except Exception as e:  # le stockage ne doit pas empêcher l'ingestion
                journal.warning("artefact d'index non sauvegardé pour %s/%s/%s : %s", tenant, nom, sha, e)
        enquete_resultat = _enqueter(jumeau, chemin_depot, sha, nom) if _enquete_active(enquete) else None
        claims_enquete = enquete_resultat.pop("claims", []) if enquete_resultat else []
        claims = [*_filtrer_routes_couvertes(claims, claims_enquete), *claims_enquete]
        exploration = {
            "providers": rapport_code["providers"],
            "fichiers": len(rapport_code["fichiers_decouverts"]),
            "fichiers_git": len(fichiers),
            "couverture": rapport_code["compteurs"],
            "observations": len(rapport_code["observations"]),
            "liens": len(rapport_code["liens"]),
            "erreurs_providers": sorted({e.get("provider", "inconnu") for e in rapport_code["erreurs"]}),
            "routes": {"cbm": routes_cbm},
            "claims": len(claims),
            **({"enquete": enquete_resultat} if enquete_resultat else {}),
        }
        source = {"nom": nom, "type": "GIT", "emplacement": str(chemin_depot), "curseur": sha,
                  "copie": str(conservee) if conservee else None, "index_code": projet,
                  "branche": branche_courante(chemin_depot), "troncature": troncature or None,
                  "exploration": exploration, **(origine or {})}
        depot.appliquer_schema(conn)
        # Claims et index de preuve deviennent visibles ensemble. Le remplacement est borné à ce dépôt :
        # réingérer ``api`` ne supprime jamais les observations déjà publiées pour ``front``.
        with conn.transaction():
            depot.enregistrer(conn, jumeau, source, claims, {**ACTIVITE, "sha": sha})
            liens_code = rapport_code.get("liens") or {}
            if isinstance(liens_code, dict):
                liens_code = liens_code.get("liens", [])
            code_index_store.remplacer_source(
                conn, tenant, jumeau["id"], nom,
                rapport_code["observations"], rapport_code["couvertures"], liens_code)
        if store.mode != "none":
            try:
                store.delete_source(tenant, nom, sauf=sha)  # un seul artefact par source, au commit courant
            except Exception as e:
                journal.warning("ancien artefact d'index non nettoyé pour %s/%s : %s", tenant, nom, e)
        cbm.retirer_ancien(precedent, projet)  # une fois le nouvel index enregistré, et seulement alors
    finally:
        if store.mode == "none" and copie is not None:
            _retirer_copie(copie)
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
    p.add_argument("--enquete", action="store_true", help="force l'enquête du harness")
    p.add_argument("--sans-enquete", action="store_true", help="désactive l'enquête du harness")
    a = p.parse_args()
    jumeau = {"id": a.jumeau, "tenant_id": a.tenant, "nom": a.nom, "equipe": a.equipe,
              "domaine": a.domaine, "mission": a.mission}
    try:
        with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True) as conn:
            enquete = True if a.enquete else False if a.sans_enquete else None
            print(ingerer(conn, jumeau, a.depot.resolve(), enquete=enquete))
            print(projeter_au_registre(conn))
    except (ValueError, PermissionError, RuntimeError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"ingestion interrompue : {e}")


if __name__ == "__main__":
    main()
