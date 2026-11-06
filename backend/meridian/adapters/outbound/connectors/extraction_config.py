"""Extraction de la configuration, de Kubernetes, Helm et des ingress.

Ce module ne lit que le texte fourni. Il produit des `Configuration`, des `Appel`
et des `Deploiement` ; aucune valeur secrète n'est conservée.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from meridian.adapters.outbound.connectors.extraction_commune import (
    chemin,
    est_secret,
    preuve,
    sans_identifiants,
)
from meridian.domain import chemins
from meridian.domain.liens_composants import (
    Appel,
    Configuration,
    Deploiement,
    RoutePasserelle,
    SourceDepot,
)

__all__ = [
    "EXTENSIONS_CONFIG",
    "EXTENSIONS_YAML",
    "KINDS_CHARGE",
    "charger_yaml",
    "est_document_charge",
    "est_helm_values",
    "extraire_configuration",
    "extraire_configuration_yaml",
    "extraire_infra",
]

EXTENSIONS_CONFIG = frozenset({".properties", ".env", ".conf", ".config"})
EXTENSIONS_YAML = frozenset({".yaml", ".yml"})
KINDS_DEPLOIEMENT = frozenset({
    "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout",
})
KINDS_CHARGE = frozenset({
    "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout",
    "Service", "Ingress", "ConfigMap",
})
_RE_CONFIG = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*[:=]\s*(.+?)\s*$")


def _configuration(fichier: str, cle: str, valeur, environment: str,
                   source_kind: str = "CONFIG") -> tuple[Configuration | None, Appel | None, str]:
    cle = str(cle or "").strip()
    valeur = str(valeur or "").strip().strip("\"'")
    if not cle or not valeur or est_secret(cle):
        return None, None, ""
    if valeur.startswith(("${", "{{")):
        return Configuration(
            cle=cle, valeur=valeur, fichier=fichier, environment=environment,
            source_kind=source_kind,
            preuves=(preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.75),),
        ), None, ""
    if not valeur.lower().startswith(("http://", "https://", "ws://", "wss://")):
        configuration = Configuration(
            cle=cle, valeur=valeur, fichier=fichier, environment=environment,
            source_kind=source_kind,
            preuves=(preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.8),),
        )
        return configuration, None, ""
    if not sans_identifiants(valeur):
        return None, None, f"{fichier} : URL avec identifiants ignorée pour {cle}"
    configuration = Configuration(
        cle=cle, valeur=valeur, fichier=fichier, environment=environment,
        source_kind=source_kind,
        preuves=(preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.8),),
    )
    route = chemin(urlsplit(valeur).path)
    soap = ".wsdl" in valeur.lower() or "wsdl" in cle.casefold()
    protocole = "SOAP" if soap else "HTTP"
    methode = "SOAP" if soap else "ANY"
    appel = Appel(
        composant_id="", application_id="", protocole=protocole,
        cible=valeur, cible_type="URL", methode=methode, chemin=route,
        operation=f"{methode} {route}".strip(), environment=environment,
        source_kind=source_kind, origine=cle,
        preuves=(preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.75),),
    )
    return configuration, appel, ""


def _aplatir(valeur, prefixe: str = "") -> Iterable[tuple[str, object]]:
    if isinstance(valeur, Mapping):
        for cle, item in valeur.items():
            nom = f"{prefixe}.{cle}" if prefixe else str(cle)
            yield from _aplatir(item, nom)
    elif isinstance(valeur, list):
        for item in valeur:
            if isinstance(item, Mapping) and "name" in item and "value" in item:
                nom = f"{prefixe}.{item['name']}" if prefixe else str(item["name"])
                yield nom, item["value"]
            else:
                yield from _aplatir(item, prefixe)
    else:
        yield prefixe, valeur


def charger_yaml(texte: str) -> tuple[list, str]:
    try:
        import yaml
    except ImportError:
        return [], "PyYAML absent : document YAML non lu"
    try:
        documents = [document for document in yaml.safe_load_all(texte) if document is not None]
    except Exception as exc:  # noqa: BLE001 - un document hostile ne doit pas faire tomber l'extraction
        return [], f"YAML illisible ({type(exc).__name__})"
    return documents, ""


def est_helm_values(fichier: str) -> bool:
    nom = fichier.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return nom in ("values.yaml", "values.yml")


def est_document_charge(document) -> bool:
    return isinstance(document, Mapping) and document.get("kind") in KINDS_CHARGE


def extraire_configuration(fichier: str, texte: str, environment: str,
                           source_kind: str = "CONFIG") -> tuple[list[Configuration],
                                                                 list[Appel], list[str]]:
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for ligne in texte.splitlines():
        contenu = ligne.strip()
        if not contenu or contenu.startswith(("#", "!", ";")):
            continue
        trouve = _RE_CONFIG.match(contenu)
        if not trouve:
            continue
        configuration, appel, probleme = _configuration(
            fichier, trouve.group(1), trouve.group(2), environment, source_kind)
        if probleme:
            diagnostics.append(probleme)
        if configuration is not None:
            configurations.append(configuration)
        if appel is not None:
            appels.append(appel)
    return configurations, appels, diagnostics


def extraire_configuration_yaml(fichier: str, texte: str, environment: str,
                                source_kind: str) -> tuple[list[Configuration],
                                                           list[Appel], list[str]]:
    documents, probleme = charger_yaml(texte)
    if probleme:
        return [], [], [f"{fichier} : {probleme}"]
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for document in documents:
        for cle, valeur in _aplatir(document):
            if not cle:
                continue
            configuration, appel, probleme = _configuration(
                fichier, cle, valeur, environment, source_kind)
            if probleme:
                diagnostics.append(probleme)
            if configuration is not None:
                configurations.append(configuration)
            if appel is not None:
                appels.append(appel)
    return configurations, appels, diagnostics


def _routes_ingress(document: Mapping, fichier: str, environment: str) -> list[RoutePasserelle]:
    routes: list[RoutePasserelle] = []
    metadata = document.get("metadata") or {}
    annotations = metadata.get("annotations") or {}
    reecriture = str(
        annotations.get("nginx.ingress.kubernetes.io/rewrite-target")
        or annotations.get("traefik.ingress.kubernetes.io/rewrite-path")
        or "").strip()
    # Un rewrite paramétré (`/$1`) ne donne pas un chemin backend statique :
    # on ne le devine pas, on garde seulement les cibles fixes.
    chemin_backend = (chemins.normaliser(reecriture)
                      if reecriture.startswith("/") and "$" not in reecriture else "")
    specification = document.get("spec") or {}
    for regle in specification.get("rules") or ():
        if not isinstance(regle, Mapping):
            continue
        host = str(regle.get("host") or "")
        http = regle.get("http") or {}
        for route_document in http.get("paths") or ():
            if not isinstance(route_document, Mapping):
                continue
            backend = route_document.get("backend") or {}
            service = backend.get("service") or {}
            nom = service.get("name") or backend.get("serviceName") or ""
            if not nom:
                continue
            route = str(route_document.get("path") or "/")
            detail = f"ingress {route} -> {nom}"
            if chemin_backend:
                detail += f" (rewrite {chemin_backend})"
            routes.append(RoutePasserelle(
                chemin=chemin(route), service=str(nom), host=host,
                environment=environment, chemin_backend=chemin_backend,
                preuves=(preuve("DEPLOIEMENT", fichier, detail, confidence=0.95),),
            ))
    return routes


def _env_appels(environnement, fichier: str, environment: str,
                source_kind: str = "HELM") -> tuple[list[Configuration],
                                                    list[Appel], list[str]]:
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for cle, valeur in _aplatir(environnement or {}):
        if not cle:
            continue
        configuration, appel, probleme = _configuration(
            fichier, cle, valeur, environment, source_kind)
        if probleme:
            diagnostics.append(probleme)
        if configuration is not None:
            configurations.append(configuration)
        if appel is not None:
            appels.append(appel)
    return configurations, appels, diagnostics


def extraire_infra(fichier: str, texte: str, depot: SourceDepot) -> tuple[list[Deploiement],
                                                                          list[Configuration],
                                                                          list[Appel],
                                                                          list[str]]:
    documents, probleme = charger_yaml(texte)
    if probleme:
        return [], [], [], [f"{fichier} : {probleme}"]
    deploiements: list[Deploiement] = []
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for document in documents:
        if not isinstance(document, Mapping):
            continue
        kind = str(document.get("kind") or "")
        metadata = document.get("metadata") or {}
        nom = str(metadata.get("name") or "")
        namespace = str(metadata.get("namespace") or "")
        labels = metadata.get("labels") or {}
        if kind in KINDS_DEPLOIEMENT:
            specification = document.get("spec") or {}
            modele = specification.get("template") or {}
            labels_modele = (modele.get("metadata") or {}).get("labels") or {}
            conteneurs = ((modele.get("spec") or {}).get("containers") or [])
            images = tuple(str(conteneur.get("image")) for conteneur in conteneurs
                           if isinstance(conteneur, Mapping) and conteneur.get("image"))
            service_name = nom or (conteneurs[0].get("name") if conteneurs else "") or depot.composant_id
            deploiements.append(Deploiement(
                composant_id=depot.composant_id, application_id=depot.application_id,
                environment=depot.environment, namespace=namespace,
                service_name=str(service_name),
                images=images, labels={**labels, **labels_modele},
                preuves=(preuve("DEPLOIEMENT", fichier, f"{kind} {service_name}",
                                confidence=0.95),),
            ))
            for conteneur in conteneurs:
                if not isinstance(conteneur, Mapping):
                    continue
                configurations_, appels_, diagnostics_ = _env_appels(
                    conteneur.get("env") or [], fichier, depot.environment, "DEPLOIEMENT")
                configurations.extend(configurations_)
                appels.extend(appels_)
                diagnostics.extend(diagnostics_)
        elif kind == "Service":
            specification = document.get("spec") or {}
            service_name = nom or depot.composant_id
            deploiements.append(Deploiement(
                composant_id=depot.composant_id, application_id=depot.application_id,
                environment=depot.environment, namespace=namespace,
                service_name=str(service_name),
                labels=specification.get("selector") or labels,
                preuves=(preuve("DEPLOIEMENT", fichier, f"Service {service_name}",
                                confidence=0.95),),
            ))
        elif kind == "Ingress":
            routes = _routes_ingress(document, fichier, depot.environment)
            if routes:
                hosts = tuple(route.host for route in routes if route.host)
                deploiements.append(Deploiement(
                    composant_id=depot.composant_id, application_id=depot.application_id,
                    environment=depot.environment, namespace=namespace,
                    service_name="", hosts=hosts,
                    routes=tuple(routes),
                    preuves=(preuve("DEPLOIEMENT", fichier, f"Ingress {nom}",
                                    confidence=0.95),),
                ))
        elif kind == "ConfigMap":
            donnees = document.get("data") or {}
            configurations_, appels_, diagnostics_ = _env_appels(
                donnees, fichier, depot.environment, "DEPLOIEMENT")
            configurations.extend(configurations_)
            appels.extend(appels_)
            diagnostics.extend(diagnostics_)

    if est_helm_values(fichier):
        for document in documents:
            if not isinstance(document, Mapping):
                continue
            image = document.get("image") or {}
            repository = str(image.get("repository") or "") if isinstance(image, Mapping) else ""
            tag = str(image.get("tag") or "") if isinstance(image, Mapping) else ""
            service = document.get("service") or {}
            nom_service = ""
            if isinstance(service, Mapping):
                nom_service = str(service.get("name") or "")
            nom_service = (str(document.get("fullnameOverride") or "")
                           or str(document.get("nameOverride") or "") or nom_service
                           or depot.composant_id)
            namespace = str((document.get("metadata") or {}).get("namespace") or "")
            routes: list[RoutePasserelle] = []
            ingress = document.get("ingress") or {}
            annotations = ingress.get("annotations") if isinstance(ingress, Mapping) else {}
            reecriture = str(
                (annotations or {}).get("nginx.ingress.kubernetes.io/rewrite-target")
                or (annotations or {}).get("traefik.ingress.kubernetes.io/rewrite-path")
                or "").strip()
            chemin_backend = (chemins.normaliser(reecriture)
                              if reecriture.startswith("/") and "$" not in reecriture else "")
            if isinstance(ingress, Mapping):
                for hote in ingress.get("hosts") or ():
                    if isinstance(hote, Mapping):
                        host = str(hote.get("host") or "")
                        for chemin_document in hote.get("paths") or ():
                            valeur = (chemin_document.get("path")
                                      if isinstance(chemin_document, Mapping)
                                      else chemin_document)
                            if valeur:
                                routes.append(RoutePasserelle(
                                    chemin=chemin(valeur), service=nom_service, host=host,
                                    environment=depot.environment,
                                    chemin_backend=chemin_backend,
                                    preuves=(preuve("HELM", fichier,
                                                    f"ingress {valeur} -> {nom_service}",
                                                    confidence=0.85),),
                                ))
            deploiements.append(Deploiement(
                composant_id=depot.composant_id, application_id=depot.application_id,
                environment=depot.environment, namespace=namespace,
                service_name=nom_service,
                images=((f"{repository}:{tag}" if repository and tag else repository),),
                routes=tuple(routes),
                labels={str(cle): str(valeur) for cle, valeur in document.items()
                        if isinstance(valeur, (str, int, float, bool))},
                preuves=(preuve("HELM", fichier, f"values {nom_service}", confidence=0.85),),
            ))
            configurations_, appels_, diagnostics_ = _env_appels(
                document.get("env") or {}, fichier, depot.environment)
            configurations.extend(configurations_)
            appels.extend(appels_)
            diagnostics.extend(diagnostics_)
    return deploiements, configurations, appels, diagnostics
