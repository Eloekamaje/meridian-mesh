"""Extraction déterministe des producteurs, consommateurs et déploiements.

Le module lit des fichiers déjà présents dans un dépôt ou un artefact :

- code Java/JavaScript : routes Spring, clients Feign/RestTemplate/WebClient, listeners JMS ;
- contrats : OpenAPI, WSDL, GraphQL, gRPC, AsyncAPI ;
- configuration : propriétés, YAML, variables d'environnement ;
- déploiement : Kubernetes, Helm, ingress.

Il ne contacte aucun serveur, n'exécute aucun code et ne lit aucun secret. Une valeur douteuse
ou illisible produit un diagnostic, jamais une invention.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from meridian.adapters.outbound.connectors import java_source
from meridian.application import interfaces_protocoles
from meridian.domain import interfaces
from meridian.domain.liens_composants import (
    Appel,
    Composant,
    Configuration,
    Deploiement,
    ExtractionDepot,
    Interface,
    Preuve,
    RoutePasserelle,
    SourceDepot,
)

__all__ = ["extraire_depot"]

_METHODES_SPRING = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
}
_METHODES_CLIENT = {
    "getForObject": "GET", "getForEntity": "GET",
    "postForObject": "POST", "postForEntity": "POST",
    "put": "PUT", "delete": "DELETE", "patchForObject": "PATCH",
}
_RE_OPENAPI_JSON = re.compile(r'"\s*(?:openapi|swagger)\s*"\s*:', re.I)
_RE_OPENAPI_YAML = re.compile(r"(?m)^[\"']?(?:openapi|swagger)[\"']?\s*:", re.I)
_RE_ASYNCAPI = re.compile(r"(?im)^\s*[\"']?asyncapi[\"']?\s*:")
_RE_WSDL = re.compile(r"<(?:\w+:)?definitions(?=[\s/>])", re.I)
_RE_GRAPHQL = re.compile(r"(?m)^\s*(?:extend\s+)?type\s+(?:Query|Mutation|Subscription)\b")
_RE_PROTO = re.compile(r"(?m)^\s*(?:syntax\s*=|service\s+\w+\s*\{)")
_RE_CONFIG = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*[:=]\s*(.+?)\s*$")
_RE_REST = re.compile(
    r"\.(getForObject|getForEntity|postForObject|postForEntity|put|delete|patchForObject|exchange)"
    r"\s*\(\s*[\"']([^\"']+)[\"']", re.I)
_RE_WEBCLIENT = re.compile(
    r"\.(get|post|put|patch|delete)\s*\(\s*\)\s*\.uri\s*\(\s*[\"']([^\"']+)[\"']", re.I)
_RE_BASEURL = re.compile(r"\.baseUrl\s*\(\s*[\"']([^\"']+)[\"']", re.I)
_RE_HTTP_METHOD = re.compile(r"HttpMethod\.([A-Z]+)", re.I)
_RE_JS = re.compile(
    r"(?:axios|http|api|client)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[`\"']([^`\"']+)[`\"']",
    re.I)
_RE_FETCH = re.compile(r"\bfetch\s*\(\s*[`\"']([^`\"']+)[`\"']", re.I)
_RE_JMS_SEND = re.compile(r"\b(?:jmsTemplate|jms|producer|template)\s*\.\s*"
                          r"(?:convertAndSend|send)\s*\(\s*[\"']([^\"']+)[\"']", re.I)
_RE_KAFKA_SEND = re.compile(r"\b(?:kafkaTemplate|kafka|producer)\s*\.\s*send\s*\(\s*"
                            r"[\"']([^\"']+)[\"']", re.I)
_RE_PROPRIETE = re.compile(r"^\$\{([^}]+)\}$")
_RE_SECRET = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|api[_-]?key|apikey|"
    r"access[_-]?key|private[_-]?key|client[_-]?secret)", re.I)
_EXT_CONFIG = frozenset({".properties", ".env", ".conf", ".config"})
_EXT_CODE = frozenset({".java", ".js", ".jsx", ".ts", ".tsx"})
_EXT_YAML = frozenset({".yaml", ".yml"})
_KINDS_DEPLOIEMENT = frozenset({"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout"})
_KINDS_CHARGE = frozenset({"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout",
                           "Service", "Ingress", "ConfigMap"})
_DOSSIERS_IGNORES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "target", "build", "dist",
    ".venv", "venv", "__pycache__", ".cache", ".idea", ".mypy_cache", ".pytest_cache",
})
_EXTENSIONS_LUES = frozenset({
    ".java", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml", ".json", ".xml",
    ".wsdl", ".graphql", ".gql", ".proto", ".properties", ".env", ".conf", ".config",
})
_RE_OPENAPI_TEXTE = re.compile(r'(?im)^\s*["\']?(openapi|swagger|asyncapi)["\']?\s*:')
_RE_KIND_K8S = re.compile(
    r"(?m)^\s*kind\s*:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Rollout|"
    r"Service|Ingress|ConfigMap)\b")


def source_fichier(chemin, texte: str) -> str:
    """Classe un fichier dans un niveau de source, sans lire de valeur sensible."""
    chemin = Path(chemin)
    nom = chemin.name.lower()
    suffixe = chemin.suffix.lower()
    if suffixe in {".java", ".js", ".jsx", ".ts", ".tsx"}:
        return "code"
    if suffixe in {".properties", ".conf", ".config"} or nom.startswith(".env"):
        return "config"
    if suffixe in {".wsdl", ".xml", ".graphql", ".gql", ".proto"}:
        return "contrats"
    if suffixe in {".yaml", ".yml"}:
        if nom in {"values.yaml", "values.yml", "chart.yaml"}:
            return "helm"
        if _RE_OPENAPI_TEXTE.search(texte):
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
        if b"\x00" in donnees[:4096]:
            continue
        try:
            texte = donnees.decode("utf-8-sig")
        except UnicodeDecodeError:
            diagnostics.append(
                f"{chemin.relative_to(base)} : encodage non UTF-8, ignoré")
            continue
        if sources_autorisees is not None and source_fichier(chemin, texte) not in sources_autorisees:
            continue
        fichiers[chemin.relative_to(base).as_posix()] = texte
    return fichiers, diagnostics


def _est_secret(cle: str) -> bool:
    return bool(_RE_SECRET.search(str(cle or "")))


def _nom_propriete(cible: str) -> str:
    trouve = _RE_PROPRIETE.match(str(cible or "").strip())
    return trouve.group(1).strip() if trouve else str(cible or "").strip()


_CLES_SECRETES_URL = frozenset({
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "apikey", "access_key", "private_key", "client_secret",
})


def _sans_identifiants(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except ValueError:
        return False
    if parties.username or parties.password or "@" in parties.netloc:
        return False
    return not any(cle.strip().lower() in _CLES_SECRETES_URL
                   for cle, _ in parse_qsl(parties.query, keep_blank_values=True))


def _chemin(*parties) -> str:
    morceaux: list[str] = []
    for partie in parties:
        if partie is None:
            continue
        texte = str(partie).strip()
        if not texte:
            continue
        if "://" in texte:
            texte = urlsplit(texte).path
        morceaux.extend(fragment for fragment in texte.replace("\\", "/").split("/") if fragment)
    return "/" + "/".join(morceaux) if morceaux else ""


def _nom_hote(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _ligne(texte: str, position: int) -> int:
    return texte.count("\n", 0, max(0, position)) + 1


def _preuve(source: str, locator: str, detail: str = "", mode: str = "DECLARE",
            confidence: float = 0.85) -> Preuve:
    return Preuve(source=source, locator=locator, detail=detail, mode=mode,
                  confidence=confidence)


def _appel_http(composant: str, application: str, fichier: str, ligne: int, methode: str,
                cible: str, source_kind: str, environment: str,
                detail: str = "") -> Appel | None:
    cible = str(cible or "").strip()
    if not cible:
        return None
    if cible.startswith(("${", "{{")):
        cible_type, chemin = "PROPRIETE", ""
    elif "://" in cible:
        if not _sans_identifiants(cible):
            return None
        cible_type, chemin = "URL", _chemin(urlsplit(cible).path)
    elif cible.startswith("/"):
        cible_type, chemin = "CHEMIN", _chemin(cible)
    else:
        cible_type, chemin = "SERVICE", _chemin(urlsplit(cible).path)
    operation = f"{methode} {chemin}".strip() if chemin else methode
    return Appel(
        composant_id=composant, application_id=application, protocole="HTTP",
        cible=cible, cible_type=cible_type, methode=methode, chemin=chemin,
        operation=operation, environment=environment, source_kind=source_kind,
        preuves=(_preuve(source_kind, f"{fichier}:{ligne}",
                         detail or f"{methode} {chemin or cible}", confidence=0.9),),
    )


def _configuration(fichier: str, cle: str, valeur, environment: str,
                   source_kind: str = "CONFIG") -> tuple[Configuration | None, Appel | None, str]:
    cle = str(cle or "").strip()
    valeur = str(valeur or "").strip().strip("\"'")
    if not cle or not valeur or _est_secret(cle):
        return None, None, ""
    if valeur.startswith(("${", "{{")):
        return Configuration(
            cle=cle, valeur=valeur, fichier=fichier, environment=environment,
            source_kind=source_kind,
            preuves=(_preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.75),),
        ), None, ""
    if not valeur.lower().startswith(("http://", "https://", "ws://", "wss://")):
        configuration = Configuration(
            cle=cle, valeur=valeur, fichier=fichier, environment=environment,
            source_kind=source_kind,
            preuves=(_preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.8),),
        )
        return configuration, None, ""
    if not _sans_identifiants(valeur):
        return None, None, f"{fichier} : URL avec identifiants ignorée pour {cle}"
    configuration = Configuration(
        cle=cle, valeur=valeur, fichier=fichier, environment=environment,
        source_kind=source_kind,
        preuves=(_preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.8),),
    )
    chemin = _chemin(urlsplit(valeur).path)
    soap = ".wsdl" in valeur.lower() or "wsdl" in cle.casefold()
    protocole = "SOAP" if soap else "HTTP"
    methode = "SOAP" if soap else "ANY"
    appel = Appel(
        composant_id="", application_id="", protocole=protocole,
        cible=valeur, cible_type="URL", methode=methode, chemin=chemin,
        operation=f"{methode} {chemin}".strip(), environment=environment,
        source_kind=source_kind, origine=cle,
        preuves=(_preuve(source_kind, f"{fichier}#{cle}", cle, confidence=0.75),),
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


def _charger_yaml(texte: str) -> tuple[list, str]:
    try:
        import yaml
    except ImportError:
        return [], "PyYAML absent : document YAML non lu"
    try:
        documents = [document for document in yaml.safe_load_all(texte) if document is not None]
    except Exception as exc:  # noqa: BLE001 - un document hostile ne doit pas faire tomber l'extraction
        return [], f"YAML illisible ({type(exc).__name__})"
    return documents, ""


def _est_helm_values(fichier: str) -> bool:
    nom = fichier.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return nom in ("values.yaml", "values.yml")


def _est_contrat(fichier: str, texte: str) -> str:
    suffixe = "." + fichier.rsplit(".", 1)[-1].lower() if "." in fichier else ""
    if suffixe in (".yaml", ".yml", ".json") and (
            _RE_OPENAPI_JSON.search(texte) or _RE_OPENAPI_YAML.search(texte)):
        return "openapi"
    if suffixe in (".yaml", ".yml") and _RE_ASYNCAPI.search(texte):
        return "asyncapi"
    if suffixe in (".wsdl", ".xml") and _RE_WSDL.search(texte):
        return "wsdl"
    if suffixe in (".graphql", ".gql") or _RE_GRAPHQL.search(texte):
        return "graphql"
    if suffixe == ".proto" or _RE_PROTO.search(texte):
        return "proto"
    return ""


def _interface_depuis_operation(application: str, composant: str, operation, contrat,
                                environment: str) -> Interface:
    protocole = str(getattr(operation, "protocol", "") or "").lower()
    protocole = {
        "rest": "HTTP", "soap": "SOAP", "graphql": "GRAPHQL", "grpc": "GRPC",
        "asyncapi": "ASYNCAPI",
    }.get(protocole, "AUTRE")
    methode = str(getattr(operation, "method", "") or "")
    chemin = str(getattr(operation, "path", "") or "")
    if protocole == "HTTP":
        libelle = f"{methode.upper()} {chemin}".strip()
    elif protocole == "SOAP":
        libelle = f"SOAP {chemin}".strip()
    else:
        libelle = f"{methode.upper()} {chemin}".strip() if methode else chemin
    return Interface(
        composant_id=composant, application_id=application, protocole=protocole,
        operation=libelle or chemin or methode, methode=methode, chemin=chemin,
        nom=str(getattr(operation, "name", "") or libelle), environment=environment,
        source_kind="CONTRAT", contrat_ref=str(getattr(contrat, "id", "") or ""),
        preuves=(_preuve(
            "CONTRAT", f"{contrat.locator}:{getattr(operation, 'name', '') or chemin}",
            f"{contrat.format} {contrat.version or ''} {libelle}".strip(), confidence=0.9),),
    )


def _extraire_contrat(fichier: str, texte: str, application: str, composant: str,
                      environment: str, genre: str) -> tuple[list[Interface], list[str]]:
    diagnostics: list[str] = []
    if genre == "openapi":
        graph = interfaces.parse_openapi(application, texte, fichier, environment)
    elif genre == "wsdl":
        graph = interfaces.parse_wsdl(application, texte, fichier, environment)
    elif genre == "graphql":
        graph = interfaces_protocoles.parse_graphql(application, texte, fichier, environment)
    elif genre == "proto":
        graph = interfaces_protocoles.parse_proto(application, texte, fichier, environment)
    elif genre == "asyncapi":
        graph = interfaces_protocoles.parse_asyncapi(application, texte, fichier, environment)
    else:
        return [], diagnostics
    diagnostics.extend(f"{fichier} : {diagnostic}" for diagnostic in graph.diagnostics)
    contrats = {contrat.id: contrat for contrat in graph.contracts}
    resultat = []
    for operation in graph.operations:
        contrat = contrats.get(operation.contract_id)
        if contrat is None:
            continue
        resultat.append(_interface_depuis_operation(
            application, composant, operation, contrat, environment))
    return resultat, diagnostics


def _arguments_annotation(attributes: Mapping, nom: str) -> dict:
    details = attributes.get("annotation_details") or {}
    valeur = details.get(nom) if isinstance(details, Mapping) else None
    return valeur if isinstance(valeur, dict) else {}


def _valeur_annotation(details: Mapping, *noms) -> str:
    for nom in noms:
        valeur = details.get(nom)
        if isinstance(valeur, (list, tuple)):
            valeur = valeur[0] if valeur else ""
        if valeur not in (None, ""):
            return str(valeur).strip()
    return ""


def _methodes_java(texte: str, fichier: str, application: str, composant: str,
                   environment: str, service_name: str,
                   context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    diagnostics: list[str] = []
    observations = java_source.extraire(fichier, texte)
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    types = {o.attributes.get("fqn"): o for o in observations if o.kind == "java_type"}

    for observation in observations:
        if observation.kind != "spring_route":
            continue
        attributes = observation.attributes
        controleur = str(attributes.get("controller") or attributes.get("java_class") or "")
        type_controleur = types.get(controleur)
        if type_controleur is not None and _arguments_annotation(
                type_controleur.attributes, "FeignClient"):
            # Une méthode `@GetMapping` sur une interface Feign décrit un appel, pas une route.
            continue
        methode = str(attributes.get("http_method") or attributes.get("method") or "")
        methode = methode.upper().rsplit(".", 1)[-1]
        if methode in ("", "ANY") and not attributes.get("member"):
            continue
        prefixe = str(attributes.get("prefix") or "")
        route = str(attributes.get("path") or attributes.get("value") or "")
        if prefixe and route and (route == prefixe or route.startswith(prefixe.rstrip("/") + "/")):
            chemin = _chemin(route)
        else:
            chemin = _chemin(prefixe, route)
        if not chemin:
            continue
        interfaces_.append(Interface(
            composant_id=composant, application_id=application, protocole="HTTP",
            operation=f"{methode} {chemin}".strip(), methode=methode, chemin=chemin,
            nom=str(attributes.get("member") or chemin), environment=environment,
            source_kind="CODE", service_name=service_name, context_path=context_path,
            preuves=(_preuve("CODE", f"{fichier}:{observation.start}",
                             f"{methode} {chemin}", confidence=0.9),),
        ))

    for observation in observations:
        if observation.kind != "java_type":
            continue
        details = _arguments_annotation(observation.attributes, "FeignClient")
        if not details:
            continue
        fqn = str(observation.attributes.get("fqn") or "")
        nom_service = _valeur_annotation(details, "name", "value", "service")
        url = _valeur_annotation(details, "url")
        base = _valeur_annotation(details, "path")
        for methode_obs in observations:
            if methode_obs.kind != "java_method":
                continue
            if methode_obs.attributes.get("owner") != fqn:
                continue
            annotation = methode_obs.attributes.get("annotation_details") or {}
            if not isinstance(annotation, Mapping):
                continue
            methode = ""
            sous_chemin = ""
            for nom, verbe in _METHODES_SPRING.items():
                if nom in annotation:
                    methode = verbe
                    sous_chemin = _valeur_annotation(annotation[nom], "value", "path")
                    break
            if not methode:
                details_route = annotation.get("RequestMapping")
                if isinstance(details_route, dict):
                    methode = (_valeur_annotation(details_route, "method") or "ANY")
                    methode = methode.upper().rsplit(".", 1)[-1]
                    sous_chemin = _valeur_annotation(details_route, "value", "path")
            if not methode:
                continue
            cible = url or nom_service
            if not cible:
                continue
            chemin = _chemin(base, sous_chemin)
            appel = _appel_http(
                composant, application, fichier, methode_obs.start, methode.upper(), cible,
                "CODE", environment,
                detail=f"Feign {nom_service or cible} {methode.upper()} {chemin}".strip())
            if appel is not None:
                appels.append(Appel(
                    composant_id=appel.composant_id, application_id=appel.application_id,
                    protocole="HTTP", cible=appel.cible, cible_type=appel.cible_type,
                    methode=appel.methode, chemin=chemin,
                    operation=f"{appel.methode} {chemin}".strip(), environment=environment,
                    source_kind="CODE", preuves=appel.preuves,
                ))

    base_url = ""
    trouve_base = _RE_BASEURL.search(texte)
    if trouve_base:
        base_url = trouve_base.group(1)
    for trouve in _RE_REST.finditer(texte):
        methode = _METHODES_CLIENT.get(trouve.group(1).lower(), "ANY").upper()
        if trouve.group(1).lower() == "exchange":
            fenetre = texte[trouve.end():trouve.end() + 160]
            http_method = _RE_HTTP_METHOD.search(fenetre)
            methode = http_method.group(1).upper() if http_method else "ANY"
        appel = _appel_http(composant, application, fichier,
                            _ligne(texte, trouve.start()), methode, trouve.group(2),
                            "CODE", environment)
        if appel is not None:
            appels.append(appel)
    for trouve in _RE_WEBCLIENT.finditer(texte):
        cible = trouve.group(2)
        if cible.startswith("/") and base_url:
            cible = base_url.rstrip("/") + "/" + cible.lstrip("/")
        appel = _appel_http(composant, application, fichier,
                            _ligne(texte, trouve.start()), trouve.group(1).upper(),
                            cible, "CODE", environment)
        if appel is not None:
            appels.append(appel)
    for trouve in _RE_JMS_SEND.finditer(texte):
        appels.append(Appel(
            composant_id=composant, application_id=application, protocole="JMS",
            cible=trouve.group(1), cible_type="QUEUE", methode="ENVOIE",
            chemin=trouve.group(1), operation=trouve.group(1), environment=environment,
            source_kind="CODE",
            preuves=(_preuve("CODE", f"{fichier}:{_ligne(texte, trouve.start())}",
                             f"JMS {trouve.group(1)}", confidence=0.9),),
        ))
    for trouve in _RE_KAFKA_SEND.finditer(texte):
        appels.append(Appel(
            composant_id=composant, application_id=application, protocole="KAFKA",
            cible=trouve.group(1), cible_type="QUEUE", methode="ENVOIE",
            chemin=trouve.group(1), operation=trouve.group(1), environment=environment,
            source_kind="CODE",
            preuves=(_preuve("CODE", f"{fichier}:{_ligne(texte, trouve.start())}",
                             f"Kafka {trouve.group(1)}", confidence=0.9),),
        ))

    for observation in observations:
        if observation.kind != "java_method":
            continue
        for annotation, protocole in (("JmsListener", "JMS"), ("RabbitListener", "JMS"),
                                      ("KafkaListener", "KAFKA")):
            details = _arguments_annotation(observation.attributes, annotation)
            if not details:
                continue
            destination = _valeur_annotation(
                details, "destination", "destinations", "queues", "queue", "topics", "topic")
            if not destination:
                continue
            interfaces_.append(Interface(
                composant_id=composant, application_id=application, protocole=protocole,
                operation=destination, methode="RECOIT", chemin=destination,
                nom=str(observation.attributes.get("name") or destination),
                environment=environment, source_kind="CODE", role="FOURNISSEUR",
                service_name=service_name,
                preuves=(_preuve("CODE", f"{fichier}:{observation.start}",
                                 f"{annotation} {destination}", confidence=0.9),),
            ))
    return interfaces_, appels, diagnostics


def _extraire_javascript(fichier: str, texte: str, application: str, composant: str,
                         environment: str) -> tuple[list[Appel], list[str]]:
    appels: list[Appel] = []
    for trouve in _RE_JS.finditer(texte):
        appel = _appel_http(composant, application, fichier,
                            _ligne(texte, trouve.start()), trouve.group(1).upper(),
                            trouve.group(2), "CODE", environment)
        if appel is not None:
            appels.append(appel)
    for trouve in _RE_FETCH.finditer(texte):
        appel = _appel_http(composant, application, fichier,
                            _ligne(texte, trouve.start()), "GET", trouve.group(1),
                            "CODE", environment)
        if appel is not None:
            appels.append(appel)
    return appels, []


def _extraire_configuration(fichier: str, texte: str, environment: str,
                            source_kind: str = "CONFIG") -> tuple[list[Configuration],
                                                                  list[Appel], list[str]]:
    configurations: list[Configuration] = []
    appels: list[Appel] = []
    diagnostics: list[str] = []
    for numero, ligne in enumerate(texte.splitlines(), 1):
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


def _extraire_configuration_yaml(fichier: str, texte: str, environment: str,
                                 source_kind: str) -> tuple[list[Configuration],
                                                            list[Appel], list[str]]:
    documents, probleme = _charger_yaml(texte)
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
    specification = document.get("spec") or {}
    for regle in specification.get("rules") or ():
        if not isinstance(regle, Mapping):
            continue
        host = str(regle.get("host") or "")
        http = regle.get("http") or {}
        for chemin in http.get("paths") or ():
            if not isinstance(chemin, Mapping):
                continue
            backend = chemin.get("backend") or {}
            service = backend.get("service") or {}
            nom = service.get("name") or backend.get("serviceName") or ""
            if not nom:
                continue
            route = str(chemin.get("path") or "/")
            routes.append(RoutePasserelle(
                chemin=_chemin(route), service=str(nom), host=host, environment=environment,
                preuves=(_preuve("DEPLOIEMENT", fichier, f"ingress {route} -> {nom}",
                                 confidence=0.95),),
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


def _extraire_infra(fichier: str, texte: str, depot: SourceDepot) -> tuple[list[Deploiement],
                                                                           list[Configuration],
                                                                           list[Appel],
                                                                           list[str]]:
    documents, probleme = _charger_yaml(texte)
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
        labels = metadata.get("labels") or {}
        if kind in _KINDS_DEPLOIEMENT:
            specification = document.get("spec") or {}
            modele = specification.get("template") or {}
            labels_modele = (modele.get("metadata") or {}).get("labels") or {}
            conteneurs = ((modele.get("spec") or {}).get("containers") or [])
            images = tuple(str(conteneur.get("image")) for conteneur in conteneurs
                           if isinstance(conteneur, Mapping) and conteneur.get("image"))
            service_name = nom or (conteneurs[0].get("name") if conteneurs else "") or depot.composant_id
            deploiements.append(Deploiement(
                composant_id=depot.composant_id, application_id=depot.application_id,
                environment=depot.environment, service_name=str(service_name),
                images=images, labels={**labels, **labels_modele},
                preuves=(_preuve("DEPLOIEMENT", fichier, f"{kind} {service_name}",
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
                environment=depot.environment, service_name=str(service_name),
                labels=specification.get("selector") or labels,
                preuves=(_preuve("DEPLOIEMENT", fichier, f"Service {service_name}",
                                 confidence=0.95),),
            ))
        elif kind == "Ingress":
            routes = _routes_ingress(document, fichier, depot.environment)
            if routes:
                hosts = tuple(route.host for route in routes if route.host)
                deploiements.append(Deploiement(
                    composant_id=depot.composant_id, application_id=depot.application_id,
                    environment=depot.environment, service_name="", hosts=hosts,
                    routes=tuple(routes),
                    preuves=(_preuve("DEPLOIEMENT", fichier, f"Ingress {nom}",
                                     confidence=0.95),),
                ))
        elif kind == "ConfigMap":
            donnees = document.get("data") or {}
            configurations_, appels_, diagnostics_ = _env_appels(
                donnees, fichier, depot.environment, "DEPLOIEMENT")
            configurations.extend(configurations_)
            appels.extend(appels_)
            diagnostics.extend(diagnostics_)

    if _est_helm_values(fichier):
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
            routes: list[RoutePasserelle] = []
            ingress = document.get("ingress") or {}
            if isinstance(ingress, Mapping):
                for hote in ingress.get("hosts") or ():
                    if isinstance(hote, Mapping):
                        host = str(hote.get("host") or "")
                        for chemin in hote.get("paths") or ():
                            valeur = chemin.get("path") if isinstance(chemin, Mapping) else chemin
                            if valeur:
                                routes.append(RoutePasserelle(
                                    chemin=_chemin(valeur), service=nom_service, host=host,
                                    environment=depot.environment,
                                    preuves=(_preuve("HELM", fichier,
                                                     f"ingress {valeur} -> {nom_service}",
                                                     confidence=0.85),),
                                ))
            deploiements.append(Deploiement(
                composant_id=depot.composant_id, application_id=depot.application_id,
                environment=depot.environment, service_name=nom_service,
                images=((f"{repository}:{tag}" if repository and tag else repository),),
                routes=tuple(routes),
                labels={str(cle): str(valeur) for cle, valeur in document.items()
                        if isinstance(valeur, (str, int, float, bool))},
                preuves=(_preuve("HELM", fichier, f"values {nom_service}", confidence=0.85),),
            ))
            configurations_, appels_, diagnostics_ = _env_appels(
                document.get("env") or {}, fichier, depot.environment)
            configurations.extend(configurations_)
            appels.extend(appels_)
            diagnostics.extend(diagnostics_)
    return deploiements, configurations, appels, diagnostics


def _extraire_traces(fichier: str, texte: str, depot: SourceDepot) -> tuple[list[Appel], list[str]]:
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
        chemin = str(trace.get("path") or trace.get("chemin") or "")
        if not chemin and "://" in cible:
            chemin = _chemin(urlsplit(cible).path)
        operation = str(trace.get("operation") or f"{methode} {chemin}".strip())
        appel = _appel_http(
            str(trace.get("component") or trace.get("composant") or depot.composant_id),
            str(trace.get("application_id") or depot.application_id),
            fichier, index + 1, methode, cible, "TRACE", depot.environment,
            detail=operation)
        if appel is None:
            continue
        appels.append(Appel(
            composant_id=appel.composant_id, application_id=appel.application_id,
            protocole=appel.protocole, cible=appel.cible, cible_type=appel.cible_type,
            methode=appel.methode, chemin=appel.chemin or chemin, operation=operation,
            environment=depot.environment, source_kind="TRACE",
            preuves=(_preuve("TRACE", f"{fichier}#{index + 1}", operation,
                             mode="OBSERVE", confidence=0.95),),
        ))
    return appels, []


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


def extraire_depot(depot: SourceDepot) -> ExtractionDepot:
    """Lit un dépôt et rend ses interfaces, appels, déploiements et configurations."""
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
                    isinstance(document, Mapping) and document.get("kind") in _KINDS_CHARGE
                    for document in documents):
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

    # 2. Code et contrats : ce que le composant expose et ce qu'il appelle.
    interfaces_: list[Interface] = []
    for chemin in sorted(fichiers):
        texte = fichiers[chemin]
        suffixe = "." + chemin.rsplit(".", 1)[-1].lower() if "." in chemin else ""
        if suffixe == ".java":
            interfaces_code, appels_code, diagnostics_ = _methodes_java(
                texte, chemin, depot.application_id, depot.composant_id,
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
                                                tuple(route.id for route in deploiement.routes)))),
        configurations=tuple(_dedupliquer(
            configurations, lambda configuration: (configuration.cle, configuration.environment))),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )
