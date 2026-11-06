"""Chargement des sources réelles pour l'enquête : registre des Twins et copies Git.

Le registre des Twins fournit une CMDB minimale (id, nom, équipe, preuve). Le code
n'est lu que si `JUMEAU_ENQUETE_CODE=1`, depuis une copie locale de source Git, et
sous une racine autorisée si `JUMEAU_ENQUETE_CODE_ROOT` est définie.
"""
from __future__ import annotations

import os
from pathlib import Path

from psycopg.rows import dict_row

from urllib.parse import urlsplit

from meridian.adapters.outbound.connectors import github, source_git
from meridian.adapters.outbound.connectors.decouverte_composants import lire_fichiers
from meridian.adapters.outbound.postgres import depot

__all__ = ["lire_code_jumeau", "lire_code_preuves", "lister_cmdb"]

SOURCES_CODE = frozenset({"code", "config", "contrats", "helm"})


def lister_cmdb(conn, tenant_id: str, *, limite: int = 1000) -> list[dict]:
    """Registre minimal des Twins du tenant, utilisable comme annuaire CMDB."""
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT id, nom, equipe FROM jumeau
               WHERE tenant_id = %s ORDER BY id LIMIT %s""",
            (tenant_id, max(1, int(limite))),
        ).fetchall()
    return [{
        "service": ligne["nom"], "twin_id": ligne["id"],
        "application_id": ligne["id"], "owner": ligne["equipe"],
        "evidence_id": f"jumeau:{ligne['id']}",
    } for ligne in lignes]


def _depot_github(url: str) -> str:
    try:
        parties = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if (parties.hostname or "").lower() not in ("github.com", "www.github.com"):
        return ""
    morceaux = [morceau for morceau in parties.path.strip("/").split("/") if morceau]
    if len(morceaux) < 2:
        return ""
    return f"{morceaux[0]}/{morceaux[1].removesuffix('.git')}"


def lire_code_preuves(conn, tenant_id: str, twin_id: str, *,
                      max_fichiers: int = 50) -> tuple[dict[str, str], list[str]]:
    """Lit les fichiers cités par les preuves du Twin, au SHA indexé, via `source_git`.

    C'est le chemin normal : on ne relit pas tout le dépôt, seulement ce qui a déjà
    servi de preuve. Aucun accès réseau, aucune exécution.
    """
    if os.environ.get("JUMEAU_ENQUETE_CODE", "").strip() != "1":
        return {}, ["code non activé (JUMEAU_ENQUETE_CODE=1 requis)"]
    if not twin_id:
        return {}, ["Twin absent pour la lecture du code"]
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            """SELECT DISTINCT s.nom, s.emplacement, s.url, s.secret_ref, p.sha, p.chemin
               FROM preuve p
               JOIN source s ON s.id = p.source_id
               JOIN claim_source cs ON cs.source_id = s.id
               JOIN claim c ON c.id = cs.claim_id
               WHERE c.tenant_id = %s AND c.jumeau_id = %s
                 AND p.type = 'CODE' AND c.statut <> 'INVALIDATED'
               ORDER BY s.nom, p.chemin LIMIT %s""",
            (tenant_id, twin_id, max(1, int(max_fichiers))),
        ).fetchall()
    fichiers: dict[str, str] = {}
    diagnostics: list[str] = []
    lecteurs = {}
    for ligne in lignes:
        emplacement = str(ligne["emplacement"] or "")
        url = str(ligne["url"] or "")
        nom, chemin, sha = ligne["nom"], ligne["chemin"], ligne["sha"]
        if emplacement and "://" not in emplacement and Path(emplacement).is_dir():
            cle = (emplacement, sha)
            if cle not in lecteurs:
                try:
                    lecteurs[cle] = source_git.lire_au_sha(emplacement, sha)
                except (OSError, ValueError) as exc:
                    diagnostics.append(f"source {nom} : preuve illisible ({type(exc).__name__})")
                    lecteurs[cle] = None
            lire = lecteurs[cle]
            if lire is None:
                continue
            try:
                contenu = lire(chemin)
            except (OSError, ValueError) as exc:
                diagnostics.append(f"{nom}/{chemin} : {type(exc).__name__}")
                continue
            if contenu is None:
                diagnostics.append(f"{nom}/{chemin} : contenu absent au SHA")
                continue
            fichiers[f"{nom}/{chemin}"] = "\n".join(contenu)
            continue
        depot = _depot_github(url)
        if not depot or not ligne["secret_ref"]:
            diagnostics.append(f"source {nom} : dépôt distant non lisible")
            continue
        try:
            fichiers[f"{nom}/{chemin}"] = github.lire_fichier(
                ligne["secret_ref"], depot, chemin, ref=sha)
        except (github.Invalide, github.JetonRefuse, github.TropDeDemandes) as exc:
            diagnostics.append(f"{nom}/{chemin} : {type(exc).__name__}")
        except OSError as exc:
            diagnostics.append(f"{nom}/{chemin} : {type(exc).__name__}")
    return fichiers, diagnostics


def _racine_autorisee(chemin: Path) -> bool:
    racine = str(os.environ.get("JUMEAU_ENQUETE_CODE_ROOT") or "").strip()
    if not racine:
        return True
    try:
        return chemin.resolve().is_relative_to(Path(racine).expanduser().resolve())
    except (OSError, ValueError):
        return False


def lire_code_jumeau(conn, tenant_id: str, twin_id: str, *,
                     sources_autorisees=SOURCES_CODE,
                     max_fichiers: int = 200,
                     max_octets: int = 1_000_000) -> tuple[dict[str, str], list[str]]:
    """Lit les copies locales des sources Git du Twin, jamais un dépôt distant."""
    if os.environ.get("JUMEAU_ENQUETE_CODE", "").strip() != "1":
        return {}, ["code non activé (JUMEAU_ENQUETE_CODE=1 requis)"]
    if not twin_id:
        return {}, ["Twin absent pour la lecture du code"]
    sources = depot.sources_du_jumeau(conn, twin_id)
    fichiers: dict[str, str] = {}
    diagnostics: list[str] = []
    for source in sources:
        emplacement = source.get("copie") or source.get("emplacement")
        if not emplacement or "://" in str(emplacement):
            continue
        racine = Path(str(emplacement)).expanduser()
        if not racine.is_dir():
            diagnostics.append(f"source {source.get('nom')} : copie locale introuvable")
            continue
        if not _racine_autorisee(racine):
            diagnostics.append(f"source {source.get('nom')} : hors racine autorisée")
            continue
        lus, problemes = lire_fichiers(
            racine, sources_autorisees=frozenset(sources_autorisees),
            max_fichiers=max_fichiers, max_octets=max_octets)
        diagnostics.extend(problemes)
        prefixe = f"{source['nom']}/" if len(sources) > 1 else ""
        for chemin, texte in lus.items():
            fichiers[f"{prefixe}{chemin}"] = texte
    return fichiers, diagnostics
