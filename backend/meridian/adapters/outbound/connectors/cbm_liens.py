"""Mapper CBM → liens de composants.

CBM fournit déjà les routes, les appels HTTP et les variables d'environnement pour de
nombreux langages. Ce module ne parse aucun fichier : il transforme des `Observation`
CBM en `Interface`, `Appel` et `Configuration` pour le moteur de liens.
"""
from __future__ import annotations

import re

from meridian.adapters.outbound.connectors.extraction_commune import (
    chemin as _chemin,
    jndi_cible,
    preuve,
    sans_identifiants,
)
from meridian.domain.liens_composants import (
    Appel,
    Composant,
    Configuration,
    ExtractionDepot,
    Interface,
)

__all__ = ["extraire_observations"]

_ROUTES = frozenset({"cbm_route", "spring_route", "jaxrs_route"})
_METHODE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(.+)$", re.I)


def _route(observation) -> tuple[str, str]:
    attributes = observation.attributes or {}
    methode = str(attributes.get("method") or attributes.get("http_method") or "").upper()
    route = str(attributes.get("route") or attributes.get("path")
                 or attributes.get("name") or observation.symbol or "")
    trouve = _METHODE.match(route)
    if trouve:
        methode = methode or trouve.group(1).upper()
        route = trouve.group(2)
    return methode or "ANY", _chemin(route)


def _preuve(observation, detail: str):
    confiance = observation.confidence
    if observation.status == "conflict":
        confiance = min(confiance, 0.5)
        detail = f"{detail} (conflit de providers)"
    elif observation.status == "ambiguous":
        confiance = min(confiance, 0.6)
        detail = f"{detail} (ambigu)"
    return preuve("CODE", f"cbm:{observation.file}:{observation.start}",
                  detail, confidence=confiance)


def extraire_observations(observations, application_id: str, composant_id: str,
                          environment: str, *, service_name: str = "",
                          owner: str = "", type_composant: str = "SERVICE"
                          ) -> ExtractionDepot:
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    configurations: list[Configuration] = []
    for observation in observations or ():
        kind = str(observation.kind or "").casefold()
        if kind in _ROUTES:
            methode, route = _route(observation)
            if not route:
                continue
            interfaces_.append(Interface(
                composant_id=composant_id, application_id=application_id,
                protocole="HTTP", operation=f"{methode} {route}", methode=methode,
                chemin=route, nom=str(observation.symbol or route),
                environment=environment, source_kind="CODE",
                service_name=service_name,
                preuves=(_preuve(observation, f"{methode} {route}"),),
            ))
        elif kind == "cbm_relation_http_calls":
            attributes = observation.attributes or {}
            cible = str(attributes.get("target") or observation.symbol or "").strip()
            route = str(attributes.get("path") or attributes.get("route") or "").strip()
            methode = str(attributes.get("method") or "").upper()
            if " : " in cible:
                cible, _, route = cible.partition(" : ")
                cible, route = cible.strip(), route.strip()
            # Une relation HTTP_CALLS peut ne porter que l'opération cible
            # (« GET /accounts/{id} ») : elle reste exploitable par le matching de chemins.
            operation_cible = _METHODE.match(cible)
            if operation_cible:
                methode = methode or operation_cible.group(1).upper()
                cible = operation_cible.group(2).strip()
                route = route or cible
            if not cible:
                continue
            cible_type = ("URL" if "://" in cible
                          else "CHEMIN" if cible.startswith("/") else "SERVICE")
            methode = methode or "ANY"
            appels.append(Appel(
                composant_id=composant_id, application_id=application_id,
                protocole="HTTP", cible=cible, cible_type=cible_type,
                methode=methode, chemin=_chemin(route),
                operation=f"{methode} {route}".strip() if route else methode,
                environment=environment, source_kind="CODE",
                preuves=(_preuve(observation, f"{methode} {cible} {route}".strip()),),
            ))
        elif kind == "jee_injection":
            cible = jndi_cible(observation.attributes or {})
            if not cible:
                continue
            appels.append(Appel(
                composant_id=composant_id, application_id=application_id,
                protocole="JNDI", cible=cible, cible_type="JNDI", methode="ANY",
                chemin=cible, operation=cible, environment=environment,
                source_kind="CODE", preuves=(_preuve(observation, f"JNDI {cible}"),),
            ))
        elif kind == "web_servlet":
            attributes = observation.attributes or {}
            motifs = (attributes.get("url_patterns") or attributes.get("urlPatterns")
                      or attributes.get("value") or ())
            if isinstance(motifs, str):
                motifs = [motifs]
            for motif in motifs:
                route = _chemin(motif)
                if not route:
                    continue
                interfaces_.append(Interface(
                    composant_id=composant_id, application_id=application_id,
                    protocole="HTTP", operation=f"ANY {route}", methode="ANY",
                    chemin=route, nom=str(attributes.get("name") or route),
                    environment=environment, source_kind="CODE",
                    service_name=service_name,
                    preuves=(_preuve(observation, f"Servlet {route}"),),
                ))
        elif kind == "cbm_env":
            attributes = observation.attributes or {}
            nom = str(attributes.get("name") or observation.symbol or "").strip()
            valeur = str(attributes.get("value") or "").strip()
            if not nom or not valeur or not sans_identifiants(valeur):
                continue
            if not valeur.lower().startswith(("http://", "https://")):
                continue
            preuve_env = _preuve(observation, f"{nom}={valeur}")
            configurations.append(Configuration(
                cle=nom, valeur=valeur, fichier=observation.file,
                environment=environment, source_kind="CONFIG",
                preuves=(preuve_env,)))
            appels.append(Appel(
                composant_id=composant_id, application_id=application_id,
                protocole="HTTP", cible=valeur, cible_type="URL", methode="ANY",
                chemin=_chemin(valeur), operation=f"ANY {_chemin(valeur)}".strip(),
                environment=environment, source_kind="CONFIG", origine=nom,
                preuves=(preuve_env,)))
    return ExtractionDepot(
        composant=Composant(application_id=application_id, nom=composant_id,
                            type=type_composant, owner=owner),
        interfaces=tuple(interfaces_), appels=tuple(appels),
        configurations=tuple(configurations),
    )
