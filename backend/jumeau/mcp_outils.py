"""Découverte déclarative d'outils MCP, sans exécution ni chargement de code.

Le résultat de `tools/list` est une donnée : chaque outil devient un `ManifesteOutil` du registre
capacitaire. Les annotations MCP `readOnlyHint` décident de la capacité ; sans annotation, l'outil est
traité comme une écriture prudente (`agir`, effet de bord déclaré). Aucun appel `tools/call` n'est fait
ici : l'exécution reste dans l'adaptateur autorisé par le harness.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from jumeau.capacites import ManifesteOutil, RegistreCapacites

__all__ = [
    "ErreurMCP",
    "importer_outils",
    "manifests_depuis_outils",
    "outils_depuis_session",
]

_RE_NON_NOM = re.compile(r"[^a-z0-9_]+")
_RE_SEPARATEURS = re.compile(r"[-_]{2,}")
_BORNES = 80


class ErreurMCP(ValueError):
    """Le résultat MCP ne contient pas d'outil exploitable."""


def _segment(valeur) -> str:
    brut = unicodedata.normalize("NFKD", str(valeur or ""))
    brut = "".join(c for c in brut if not unicodedata.combining(c)).lower()
    brut = _RE_NON_NOM.sub("-", brut)
    brut = _RE_SEPARATEURS.sub("-", brut).strip("_-")
    return brut or "outil"


def _nom_unique(base: str, utilises: set[str]) -> str:
    if base not in utilises and len(base) <= _BORNES:
        return base
    racine = base[: _BORNES - 9].rstrip("._-")
    compteur = 1
    candidat = f"{racine}-{compteur}"
    while candidat in utilises:
        compteur += 1
        candidat = f"{racine}-{compteur}"
    return candidat


def _outil_dict(outil) -> dict:
    if isinstance(outil, Mapping):
        return dict(outil)
    for methode in ("model_dump", "dict"):
        fonction = getattr(outil, methode, None)
        if callable(fonction):
            valeur = fonction()
            if isinstance(valeur, Mapping):
                return dict(valeur)
    return {}


def _lecture_seule(outil: Mapping) -> bool:
    annotations = outil.get("annotations")
    dump = getattr(annotations, "model_dump", None)
    if callable(dump):
        annotations = dump()
    if isinstance(annotations, Mapping):
        valeur = annotations.get("readOnlyHint")
        if isinstance(valeur, bool):
            return valeur
    valeur = outil.get("read_only_hint")
    return valeur is True


def manifests_depuis_outils(
    application_id,
    outils,
    version="1.0.0",
    tenant=None,
    persona=None,
    perimetre=None,
) -> list[ManifesteOutil]:
    """Traduit une liste de descripteurs MCP en manifestes ; lève `ErreurMCP` si la forme est invalide."""
    if not isinstance(application_id, str) or not application_id.strip():
        raise ErreurMCP("application_id : chaîne non vide attendue")
    if isinstance(outils, Mapping):
        outils = outils.get("tools")
    if not isinstance(outils, (list, tuple)):
        raise ErreurMCP("tools : liste attendue")
    prefixe = _segment(application_id)
    noms: set[str] = set()
    manifestes: list[ManifesteOutil] = []
    for rang, brut in enumerate(outils):
        outil = _outil_dict(brut)
        nom_outil = outil.get("name")
        if not isinstance(nom_outil, str) or not nom_outil.strip():
            raise ErreurMCP(f"outil {rang} : name obligatoire")
        nom = _nom_unique(f"{prefixe}.{_segment(nom_outil)}", noms)
        noms.add(nom)
        description = outil.get("description")
        if not isinstance(description, str) or not description.strip():
            description = f"Outil MCP {nom_outil.strip()}"
        seul = _lecture_seule(outil)
        schema = outil.get("inputSchema")
        if not isinstance(schema, Mapping):
            schema = outil.get("input_schema")
        manifestes.append(ManifesteOutil(
            nom=nom,
            version=version,
            description=description.strip(),
            capacite="observer" if seul else "agir",
            schema_entree=dict(schema) if isinstance(schema, Mapping) else {},
            schema_sortie={},
            tenant=tenant,
            persona=persona,
            perimetre=perimetre,
            lecture_seule=seul,
            cout=0.0,
            timeout_ms=5000,
            mode_preuve="OBSERVED" if seul else "AUCUNE",
            effets_de_bord=() if seul else (f"mcp:{_segment(nom_outil)}",),
            source="mcp",
        ))
    return manifestes


def importer_outils(
    registre: RegistreCapacites,
    application_id,
    outils,
    version="1.0.0",
    tenant=None,
    persona=None,
    perimetre=None,
) -> list[str]:
    """Génère et inscrit les manifestes MCP ; rend leurs noms."""
    enregistrer = getattr(registre, "enregistrer", None)
    if not callable(enregistrer):
        raise TypeError("registre capacitaire attendu")
    noms = []
    for manifeste in manifests_depuis_outils(
        application_id, outils, version, tenant, persona, perimetre
    ):
        enregistrer(manifeste)
        noms.append(manifeste.nom)
    return noms


async def outils_depuis_session(session) -> list:
    """Lit `tools/list` sur une session MCP déjà ouverte ; aucun outil n'est exécuté."""
    lister = getattr(session, "list_tools", None)
    if not callable(lister):
        raise ErreurMCP("session MCP sans list_tools")
    resultat = lister()
    if hasattr(resultat, "__await__"):
        resultat = await resultat
    outils = getattr(resultat, "tools", None)
    if outils is None and isinstance(resultat, Mapping):
        outils = resultat.get("tools")
    if outils is None:
        raise ErreurMCP("réponse MCP sans tools")
    return list(outils)
