"""Orchestration de l'extraction déterministe d'un dépôt.

Ce module lit les fichiers, choisit la source de chaque famille et assemble un
`ExtractionDepot` :

- CBM est la source principale du code (routes, appels HTTP, environnement) ;
- le code local (`extraction_code`) est le repli ;
- les contrats, la configuration et les traces ont leurs modules dédiés ;
- Kubernetes, Helm et ingress sont dans `extraction_config`.

Il ne contacte aucun serveur, n'exécute aucun code et ne lit aucun secret. Une valeur
douteuse ou illisible produit un diagnostic, jamais une invention.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from meridian.adapters.outbound.connectors import cbm_liens
from meridian.adapters.outbound.connectors import connecteur_interfaces
from meridian.adapters.outbound.connectors.extraction_code import (
    extraire_dotnet as _extraire_dotnet,
    extraire_java as _methodes_java,
    extraire_javascript as _extraire_javascript,
    extraire_python as _extraire_python,
)
from meridian.adapters.outbound.connectors.extraction_commune import (
    chemin as _chemin,
    nom_propriete as _nom_propriete,
    preuve as _preuve,
)
from meridian.adapters.outbound.connectors.extraction_config import (
    EXTENSIONS_CONFIG as _EXT_CONFIG,
    EXTENSIONS_YAML as _EXT_YAML,
    charger_yaml as _charger_yaml,
    est_document_charge as _est_document_charge,
    est_helm_values as _est_helm_values,
    extraire_configuration as _extraire_configuration,
    extraire_configuration_yaml as _extraire_configuration_yaml,
    extraire_infra as _extraire_infra,
)
from meridian.adapters.outbound.connectors.extraction_contrats import (
    est_contrat as _est_contrat,
    extraire_contrat as _extraire_contrat,
)
from meridian.adapters.outbound.connectors.extraction_traces import (
    extraire_traces as _extraire_traces,
)
from meridian.adapters.outbound.connectors.lecture_fichiers import (
    DOSSIERS_TECHNIQUES,
    decoder_texte as _decoder,
    est_binaire as _est_binaire,
)
from meridian.domain.liens_composants import (
    Appel,
    Composant,
    Configuration,
    Deploiement,
    ExtractionDepot,
    Interface,
    SourceDepot,
)

__all__ = ["extraire_depot"]

_EXT_CODE_LUE = frozenset({".java", ".py", ".cs", ".js", ".jsx", ".ts", ".tsx"})
# Un nœud `File` existe pour presque tous les fichiers, y compris non parsés :
# il ne prouve pas que CBM a compris le langage. Seuls ces kinds sont une couverture.
_KINDS_CBM_CODE = frozenset({
    "cbm_class", "cbm_function", "cbm_method", "cbm_variable", "cbm_section",
    "cbm_route", "cbm_env", "cbm_table", "cbm_package", "cbm_decorator",
    "cbm_process", "cbm_image", "cbm_resource", "cbm_relation_http_calls",
    "web_servlet", "jee_injection",
})
_DOSSIERS_IGNORES = DOSSIERS_TECHNIQUES | frozenset({
    "target", ".idea", ".mypy_cache", ".pytest_cache",
})
_EXTENSIONS_LUES = frozenset({
    ".java", ".js", ".jsx", ".ts", ".tsx", ".py", ".cs", ".yaml", ".yml", ".json",
    ".xml", ".wsdl", ".graphql", ".gql", ".proto", ".properties", ".env", ".conf",
    ".config",
})
_RE_KIND_K8S = re.compile(
    r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Rollout|"
    r"Service|Ingress|ConfigMap)\b")


def source_fichier(chemin, texte: str) -> str:
    """Classe un fichier dans un niveau de source, sans lire de valeur sensible."""
    chemin = Path(chemin)
    nom = chemin.name.lower()
    suffixe = chemin.suffix.lower()
    if suffixe in {".java", ".js", ".jsx", ".ts", ".tsx", ".py", ".cs"}:
        return "code"
    if suffixe in {".properties", ".conf", ".config"} or nom.startswith(".env"):
        return "config"
    if suffixe in {".wsdl", ".xml", ".graphql", ".gql", ".proto"}:
        return "contrats"
    if suffixe in {".yaml", ".yml"}:
        if nom in {"values.yaml", "values.yml", "chart.yaml"}:
            return "helm"
        if (connecteur_interfaces.est_openapi(texte)
                or connecteur_interfaces.est_asyncapi(texte)):
            return "contrats"
        if _RE_KIND_K8S.search(texte):
            return "kubernetes"
        return "config"
    if suffixe == ".json":
        if "trace" in nom or (texte.lstrip().startswith("[") and '"url"' in texte):
            return "traces"
        if re.search(r'"\s*(openapi|swagger|asyncapi)\s*"', texte):
            return "contrats"
        return "autre"
    return "autre"


def lire_fichiers(racine, *, sources_autorisees=None, max_fichiers: int = 800,
                  max_octets: int = 2_000_000) -> tuple[dict[str, str], list[str]]:
    """Lit les fichiers utiles d'une racine, avec limites et politique de sources."""
    base = Path(racine)
    if not base.is_dir():
        raise ValueError("racine introuvable ou n'est pas un dossier")
    fichiers: dict[str, str] = {}
    diagnostics: list[str] = []
    for chemin in sorted(base.rglob("*")):
        if len(fichiers) >= max_fichiers:
            diagnostics.append(f"{base} : limite de {max_fichiers} fichiers atteinte")
            break
        if not chemin.is_file() or chemin.is_symlink():
            continue
        if any(partie in _DOSSIERS_IGNORES for partie in chemin.relative_to(base).parts):
            continue
        if chemin.suffix.lower() not in _EXTENSIONS_LUES:
            continue
        try:
            if chemin.stat().st_size > max_octets:
                diagnostics.append(f"{chemin.relative_to(base)} : fichier trop gros, ignoré")
                continue
            donnees = chemin.read_bytes()
        except OSError as erreur:
            diagnostics.append(
                f"{chemin.relative_to(base)} : illisible ({type(erreur).__name__})")
            continue
        if _est_binaire(donnees):
            continue
        texte = _decoder(donnees, latin1=False)
        if texte is None:
            diagnostics.append(
                f"{chemin.relative_to(base)} : encodage non UTF-8, ignoré")
            continue
        if sources_autorisees is not None and source_fichier(chemin, texte) not in sources_autorisees:
            continue
        fichiers[chemin.relative_to(base).as_posix()] = texte
    return fichiers, diagnostics


def _dedupliquer(items: Iterable, cle) -> list:
    vus = {}
    for item in items:
        marque = cle(item)
        if marque not in vus:
            vus[marque] = item
    return list(vus.values())


def _uniques(items: Iterable, cle=lambda item: item) -> list:
    vus = {}
    for item in items:
        vus.setdefault(cle(item), item)
    return list(vus.values())


def _fusionner_interfaces(interfaces: Iterable[Interface]) -> list[Interface]:
    """Une même opération vue par le code et par le contrat reste une seule interface."""
    groupes: dict[tuple, Interface] = {}
    for interface in interfaces:
        cle = (interface.composant_id, interface.protocole, interface.operation,
               interface.environment)
        existant = groupes.get(cle)
        if existant is None:
            groupes[cle] = interface
            continue
        groupes[cle] = replace(
            existant,
            nom=existant.nom or interface.nom,
            source_kind="CODE" if "CODE" in (existant.source_kind, interface.source_kind)
            else existant.source_kind,
            portee=existant.portee if existant.portee != "UNKNOWN" else interface.portee,
            service_name=existant.service_name or interface.service_name,
            context_path=existant.context_path or interface.context_path,
            contrat_ref=existant.contrat_ref or interface.contrat_ref,
            preuves=tuple(_uniques([*existant.preuves, *interface.preuves],
                                   cle=lambda preuve: preuve.id)),
        )
    return list(groupes.values())


def extraire_depot(depot: SourceDepot, observations=()) -> ExtractionDepot:
    """Lit un dépôt et rend ses interfaces, appels, déploiements et configurations.

    `observations` (CBM ou index fédéré) est la source principale pour le code :
    un fichier déjà couvert par CBM n'est pas relu par les parseurs locaux. Sans
    observations, le comportement reste le repli historique.
    """
    observations = tuple(observations or ())
    fichiers = {str(chemin).replace("\\", "/"): str(texte)
                for chemin, texte in (depot.fichiers or {}).items()}
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    deploiements: list[Deploiement] = []
    diagnostics: list[str] = []

    # 1. Configuration et déploiement d'abord : ils donnent le nom de service, le contexte
    # et les routes de passerelle dont le code et les contrats ont besoin.
    for chemin in sorted(fichiers):
        texte = fichiers[chemin]
        suffixe = "." + chemin.rsplit(".", 1)[-1].lower() if "." in chemin else ""
        if suffixe in _EXT_CONFIG:
            configurations_, appels_, diagnostics_ = _extraire_configuration(
                chemin, texte, depot.environment)
        elif suffixe in _EXT_YAML:
            if _est_contrat(chemin, texte):
                continue
            documents, probleme = _charger_yaml(texte)
            if probleme:
                diagnostics.append(f"{chemin} : {probleme}")
                continue
            if _est_helm_values(chemin) or any(
                    _est_document_charge(document) for document in documents):
                deploiements_, configurations_, appels_, diagnostics_ = _extraire_infra(
                    chemin, texte, depot)
                deploiements.extend(deploiements_)
            else:
                configurations_, appels_, diagnostics_ = _extraire_configuration_yaml(
                    chemin, texte, depot.environment, "CONFIG")
        elif suffixe == ".json" and "trace" in chemin.lower():
            appels_, diagnostics_ = _extraire_traces(chemin, texte, depot)
        else:
            continue
        configurations.extend(configurations_)
        appels.extend(appels_)
        diagnostics.extend(diagnostics_)

    service_name = ""
    context_path = ""
    for configuration in configurations:
        cle = configuration.cle.casefold()
        if cle in ("spring.application.name", "application.name", "service.name"):
            service_name = configuration.valeur
        elif cle in ("server.servlet.context-path", "server.context-path",
                     "quarkus.servlet.context-path", "micronaut.server.context-path"):
            context_path = _chemin(configuration.valeur)
    if service_name:
        deploiements.append(Deploiement(
            composant_id=depot.composant_id, application_id=depot.application_id,
            environment=depot.environment, service_name=service_name,
            preuves=(_preuve("CONFIG", f"configuration:{service_name}",
                             "spring.application.name", confidence=0.85),),
        ))

    # 2. Code : CBM d'abord, parseurs locaux seulement pour les fichiers non couverts.
    fichiers_couverts = {
        str(observation.file) for observation in observations
        if str(observation.kind or "").casefold() in _KINDS_CBM_CODE
    }
    interfaces_: list[Interface] = []
    if observations:
        extraction_cbm = cbm_liens.extraire_observations(
            observations, depot.application_id, depot.composant_id, depot.environment,
            service_name=service_name, owner=depot.owner,
            type_composant=depot.type_composant)
        interfaces_.extend(extraction_cbm.interfaces)
        appels.extend(extraction_cbm.appels)
        configurations.extend(extraction_cbm.configurations)

    # 3. Contrats et repli local pour le code que CBM n'a pas couvert.
    for chemin in sorted(fichiers):
        texte = fichiers[chemin]
        suffixe = "." + chemin.rsplit(".", 1)[-1].lower() if "." in chemin else ""
        if suffixe in _EXT_CODE_LUE and chemin in fichiers_couverts:
            continue
        if suffixe == ".java":
            interfaces_code, appels_code, diagnostics_ = _methodes_java(
                texte, chemin, depot.application_id, depot.composant_id,
                depot.environment, service_name, context_path)
            interfaces_.extend(interfaces_code)
            appels.extend(appels_code)
            diagnostics.extend(diagnostics_)
        elif suffixe == ".py":
            interfaces_code, appels_code, diagnostics_ = _extraire_python(
                chemin, texte, depot.application_id, depot.composant_id,
                depot.environment, service_name, context_path)
            interfaces_.extend(interfaces_code)
            appels.extend(appels_code)
            diagnostics.extend(diagnostics_)
        elif suffixe == ".cs":
            interfaces_code, appels_code, diagnostics_ = _extraire_dotnet(
                chemin, texte, depot.application_id, depot.composant_id,
                depot.environment, service_name, context_path)
            interfaces_.extend(interfaces_code)
            appels.extend(appels_code)
            diagnostics.extend(diagnostics_)
        elif suffixe in (".js", ".jsx", ".ts", ".tsx"):
            appels_code, diagnostics_ = _extraire_javascript(
                chemin, texte, depot.application_id, depot.composant_id, depot.environment)
            appels.extend(appels_code)
            diagnostics.extend(diagnostics_)
        elif suffixe == ".json" and "trace" in chemin.lower():
            continue
        else:
            genre = _est_contrat(chemin, texte)
            if genre:
                interfaces_contrat, diagnostics_ = _extraire_contrat(
                    chemin, texte, depot.application_id, depot.composant_id,
                    depot.environment, genre)
                interfaces_.extend(interfaces_contrat)
                diagnostics.extend(diagnostics_)

    composant = Composant(
        application_id=depot.application_id, nom=depot.composant_id,
        type=depot.type_composant, owner=depot.owner)

    # Les appels de configuration n'ont pas encore de composant : ils appartiennent au dépôt.
    appels = [
        Appel(
            composant_id=depot.composant_id, application_id=depot.application_id,
            protocole=appel.protocole, cible=appel.cible, cible_type=appel.cible_type,
            methode=appel.methode, chemin=appel.chemin, operation=appel.operation,
            environment=appel.environment, source_kind=appel.source_kind,
            role=appel.role, origine=appel.origine, preuves=appel.preuves)
        for appel in appels
    ]
    # Une URL de configuration déjà utilisée par un appel typé (`${...}`) est un binding,
    # pas un échange indépendant : la garder créerait un faux cas « ANY /base ».
    proprietes = {_nom_propriete(appel.cible).casefold()
                  for appel in appels if appel.cible_type == "PROPRIETE"}
    appels = [
        appel for appel in appels
        if not (appel.cible_type == "URL" and appel.source_kind in ("CONFIG", "HELM")
                and appel.origine.casefold() in proprietes)
    ]
    interfaces_ = [
        Interface(
            composant_id=depot.composant_id, application_id=depot.application_id,
            protocole=interface.protocole, operation=interface.operation,
            methode=interface.methode, chemin=interface.chemin, nom=interface.nom,
            environment=interface.environment, portee=interface.portee,
            source_kind=interface.source_kind, role=interface.role,
            service_name=interface.service_name or service_name,
            context_path=interface.context_path or context_path,
            contrat_ref=interface.contrat_ref, preuves=interface.preuves)
        for interface in interfaces_
    ]

    return ExtractionDepot(
        composant=composant,
        interfaces=tuple(_fusionner_interfaces(interfaces_)),
        appels=tuple(_dedupliquer(
            appels, lambda appel: (appel.protocole, appel.methode, appel.cible,
                                    appel.chemin, appel.environment, appel.source_kind))),
        deploiements=tuple(_dedupliquer(
            deploiements, lambda deploiement: (deploiement.service_name,
                                                deploiement.environment,
                                                deploiement.namespace,
                                                tuple(route.id for route in deploiement.routes)))),
        configurations=tuple(_dedupliquer(
            configurations, lambda configuration: (configuration.cle, configuration.environment))),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )
