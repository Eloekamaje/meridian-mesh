"""Serveur MCP read-only du plugin Méridian.

Les tools appellent l'API Méridian déjà authentifiée et bornée au tenant. Aucun tool n'écrit, ne
promeut, ne décide ni n'exécute une action. Les erreurs sont rendues sans secret ni URL sensible.
"""
from __future__ import annotations

import os

import requests
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

API = os.environ.get("MERIDIAN_API_URL", "http://127.0.0.1:8001/api").rstrip("/")
TENANT = os.environ.get("MERIDIAN_TENANT", "local")
PERSONA = os.environ.get("MERIDIAN_PERSONA", "architecte")

server = MCPServer(
    name="meridian",
    title="Méridian",
    description="Lecture du Mesh, des Claims, des impacts et des réponses situées Méridian.",
    version="0.1.0",
)
_LECTURE = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _entetes() -> dict[str, str]:
    entetes = {"Accept": "application/json", "X-Persona": PERSONA}
    if TENANT:
        entetes["X-Tenant"] = TENANT
    return entetes


def _appel(methode: str, chemin: str, *, params=None, corps=None) -> dict:
    try:
        reponse = requests.request(
            methode, f"{API}{chemin}", headers=_entetes(), params=params, json=corps, timeout=20)
        reponse.raise_for_status()
        donnees = reponse.json()
        return donnees if isinstance(donnees, dict) else {"donnees": donnees}
    except requests.RequestException as exc:
        return {"erreur": type(exc).__name__, "message": "API Méridian indisponible",
                "suggestion": "Vérifier MERIDIAN_API_URL et que le backend écoute."}
    except ValueError:
        return {"erreur": "ReponseInvalide", "message": "Réponse Méridian non JSON"}


@server.tool(annotations=_LECTURE)
def meridian_profils() -> dict:
    """Liste les profils composés disponibles (lecture seule)."""
    return _appel("GET", "/boucle/profils")


@server.tool(annotations=_LECTURE)
def meridian_composition(
    profil: str,
    question: str = "",
    application_id: str | None = None,
    situation_id: str | None = None,
    twin_ids: list[str] | None = None,
) -> dict:
    """Prévisualise la composition méthode/compétence/spécialiste pour un profil."""
    return _appel("POST", "/boucle/composition", corps={
        "profil": profil, "question": question, "application_id": application_id,
        "situation_id": situation_id, "twin_ids": twin_ids or [],
    })


@server.tool(annotations=_LECTURE)
def meridian_analyser(
    question: str,
    profil: str | None = None,
    situation_id: str | None = None,
    twin_ids: list[str] | None = None,
    application_id: str | None = None,
    profondeur: int = 2,
    scope: str | None = None,
    domaine: str | None = None,
) -> dict:
    """Analyse une question : même socle de faits, lentille du profil, aucune écriture."""
    return _appel("POST", "/boucle/analyser", corps={
        "question": question, "profil": profil, "situation_id": situation_id,
        "twin_ids": twin_ids or [], "application_id": application_id, "profondeur": profondeur,
        "scope": scope, "domaine": domaine,
    })


@server.tool(annotations=_LECTURE)
def meridian_impact(twin_id: str, profondeur: int = 2) -> dict:
    """Impact amont/aval d'un Twin dans le graphe (lecture seule)."""
    return _appel("GET", f"/boucle/graphe/{twin_id}/impact", params={"profondeur": profondeur})


@server.tool(annotations=_LECTURE)
def meridian_claims(twin_id: str, limite: int = 100) -> dict:
    """Claims d'un Twin, avec leurs preuves et leur état (lecture seule)."""
    return _appel("GET", f"/boucle/twins/{twin_id}/claims", params={"limite": limite})


@server.tool(annotations=_LECTURE)
def meridian_learnings(situation_id: str | None = None, twin_ids: list[str] | None = None,
                       limite: int = 20) -> dict:
    """Learnings réutilisables pour une situation ou des Twins (lecture seule)."""
    params = {"limite": limite}
    if situation_id:
        params["situation_id"] = situation_id
    if twin_ids:
        params["twin_ids"] = ",".join(twin_ids)
    return _appel("GET", "/boucle/learnings", params=params)


@server.tool(annotations=_LECTURE)
def meridian_portefeuille(domaine: str | None = None, limite: int = 50) -> dict:
    """Agrège le portefeuille : situations, décisions, initiatives, outcomes, learnings et valeur."""
    params = {"limite": limite}
    if domaine:
        params["domaine"] = domaine
    return _appel("GET", "/boucle/portefeuille", params=params)


@server.tool(annotations=_LECTURE)
def meridian_valeurs(statut: str | None = None, domaine: str | None = None,
                     type_: str | None = None, limite: int = 200) -> dict:
    """Value Ledger : valeurs attendues, observées, statuts et écarts (lecture seule)."""
    params = {"limite": limite}
    if statut:
        params["statut"] = statut
    if domaine:
        params["domaine"] = domaine
    if type_:
        params["type"] = type_
    return _appel("GET", "/boucle/valeurs", params=params)


@server.tool(annotations=_LECTURE)
def meridian_valeur_resume(domaine: str | None = None) -> dict:
    """Résumé du Value Ledger, séparé par devise et unité (lecture seule)."""
    params = {"domaine": domaine} if domaine else {}
    return _appel("GET", "/boucle/valeurs/resume", params=params)


@server.tool(annotations=_LECTURE)
def meridian_attention(type_: str = "SITUATION", limite: int = 20) -> dict:
    """Objets classés par l'attention Méridian, avec score et raisons (lecture seule)."""
    return _appel("GET", "/boucle/attention", params={"type": type_, "limite": limite})


if __name__ == "__main__":
    server.run("stdio")
