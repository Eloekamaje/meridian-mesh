"""État des dépendances runtime et outillage, sans exposer aucun secret.

Le but est de rendre les absences visibles au démarrage et dans `/api/health`, plutôt que de
découvrir un binaire manquant au milieu d'une ingestion.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[3]
COMPILATEUR_DIAGRAMME = RACINE / "backend/meridian/adapters/outbound/diagram_export.py"


def _env(*noms: str) -> str | None:
    for nom in noms:
        valeur = str(os.environ.get(nom) or "").strip()
        if valeur:
            return valeur
    return None


def _binaire(nom_env: str, defaut: str) -> str | None:
    nom = _env(nom_env)
    return shutil.which(nom or defaut)


def _module(nom: str) -> bool:
    try:
        return importlib.util.find_spec(nom) is not None
    except (ImportError, ValueError):
        return False


def etat() -> dict[str, Any]:
    """Vue stable : `ok`, `degraded` ou `down`, avec la raison de chaque absence."""
    mongo = bool(_env("MONGO_URL")) and bool(_env("DB_NAME"))
    postgres = bool(_env("JUMEAU_PG_DSN", "JUMEAU_WORKER_PG_DSN"))
    git = _binaire("GIT_BIN", "git")
    cbm = _binaire("CBM_BIN", "codebase-memory-mcp")
    modele = (_env("JUMEAU_MODELE") or "deepseek").lower()
    cle_modele = bool(_env("DEEPSEEK_API_KEY")) if modele == "deepseek" else True
    anydoc = _module("anydoc")
    redis = bool(_env("REDIS_URL"))
    neo4j = bool(_env("NEO4J_URI", "NEO4J_URL")) or (_env("GRAPH_STORE") or "").lower() == "neo4j"
    composeur = COMPILATEUR_DIAGRAMME.is_file()

    dependances = [
        {"nom": "postgres", "statut": "ok" if postgres else "indisponible", "requis": True,
         "detail": "JUMEAU_PG_DSN ou JUMEAU_WORKER_PG_DSN"},
        {"nom": "mongo", "statut": "ok" if mongo else "indisponible", "requis": True,
         "detail": "MONGO_URL et DB_NAME"},
        {"nom": "git", "statut": "ok" if git else "indisponible", "requis": True,
         "detail": "binaire git dans PATH ou GIT_BIN"},
        {"nom": "codebase-memory-mcp", "statut": "ok" if cbm else "indisponible",
         "requis": False, "requis_pour": ["ingestion de code", "outils de code"],
         "detail": "CBM_BIN ou binaire codebase-memory-mcp dans PATH"},
        {"nom": "modele", "statut": "ok" if cle_modele else "indisponible", "requis": False,
         "requis_pour": ["Flore", "Gardien"], "detail": f"mode={modele}"},
        {"nom": "anydoc", "statut": "ok" if anydoc else "absent", "requis": False,
         "requis_pour": ["extraction bureautique"], "detail": "module Python firecrawl-anydoc"},
        {"nom": "redis", "statut": "ok" if redis else "absent", "requis": False,
         "requis_pour": ["SSE/notifications"], "detail": "REDIS_URL"},
        {"nom": "neo4j", "statut": "ok" if neo4j else "absent", "requis": False,
         "requis_pour": ["projection graphe"], "detail": "NEO4J_URI/NEO4J_URL ou GRAPH_STORE=neo4j"},
        {"nom": "design-diagram", "statut": "ok" if composeur else "absent", "requis": False,
         "requis_pour": ["compilation de diagrammes"], "detail": "copie vendored du compilateur SVG"},
    ]
    manquantes = [d["nom"] for d in dependances if d["statut"] != "ok"]
    if not postgres or not mongo:
        statut = "down"
    elif not git:
        statut = "down"
    elif not cbm or not cle_modele:
        statut = "degraded"
    else:
        statut = "degraded" if anydoc is False or not composeur else "ok"
    return {"status": statut, "dependances": dependances, "manquantes": manquantes}


def exiger(*noms: str) -> None:
    """Échoue clairement si une dépendance nommée est absente ; utilisable par un CLI."""
    index = {d["nom"]: d for d in etat()["dependances"]}
    absentes = [nom for nom in noms if nom not in index or index[nom]["statut"] != "ok"]
    if absentes:
        details = "; ".join(f"{nom}: {index.get(nom, {}).get('detail', 'inconnue')}" for nom in absentes)
        raise RuntimeError(f"dépendances indisponibles : {details}")
