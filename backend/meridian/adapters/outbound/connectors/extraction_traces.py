"""Extraction des traces d'appels en `Appel` de composant.

Une trace est une observation, pas une déclaration : la preuve est marquée
`OBSERVE`. Ce module ne lit que le texte fourni, sans disque ni réseau.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

from meridian.adapters.outbound.connectors.extraction_commune import (
    appel_http,
    chemin,
    preuve,
)
from meridian.domain.liens_composants import Appel, SourceDepot

__all__ = ["extraire_traces"]


def extraire_traces(fichier: str, texte: str, depot: SourceDepot
                    ) -> tuple[list[Appel], list[str]]:
    """Transforme un export JSON de traces en appels observés."""
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError:
        return [], [f"{fichier} : JSON de traces illisible"]
    if isinstance(donnees, Mapping):
        donnees = donnees.get("traces") or donnees.get("appels") or []
    if not isinstance(donnees, list):
        return [], [f"{fichier} : liste de traces attendue"]
    appels: list[Appel] = []
    for index, trace in enumerate(donnees):
        if not isinstance(trace, Mapping):
            continue
        cible = str(trace.get("url") or trace.get("target") or trace.get("cible") or "")
        if not cible:
            continue
        methode = str(trace.get("method") or trace.get("methode") or "ANY").upper()
        route = str(trace.get("path") or trace.get("chemin") or "")
        if not route and "://" in cible:
            route = chemin(urlsplit(cible).path)
        operation = str(trace.get("operation") or f"{methode} {route}".strip())
        appel = appel_http(
            str(trace.get("component") or trace.get("composant") or depot.composant_id),
            str(trace.get("application_id") or depot.application_id),
            fichier, index + 1, methode, cible, "TRACE", depot.environment,
            detail=operation)
        if appel is None:
            continue
        appels.append(Appel(
            composant_id=appel.composant_id, application_id=appel.application_id,
            protocole=appel.protocole, cible=appel.cible, cible_type=appel.cible_type,
            methode=appel.methode, chemin=appel.chemin or route, operation=operation,
            environment=depot.environment, source_kind="TRACE",
            preuves=(preuve("TRACE", f"{fichier}#{index + 1}", operation,
                            mode="OBSERVE", confidence=0.95),),
        ))
    return appels, []
