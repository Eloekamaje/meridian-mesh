"""Extraction locale du code : Java/Spring/JAX-RS, Python, JavaScript et ASP.NET.

C'est le **repli** lorsque CBM n'a pas couvert un fichier. Aucun parseur ne lit
le disque : tout le texte est fourni par l'appelant.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping

from meridian.adapters.outbound.connectors import java_source
from meridian.adapters.outbound.connectors.extraction_commune import (
    appel_http as _appel_http,
    arguments_annotation as _arguments_annotation,
    chemin as _chemin,
    jndi_cible,
    ligne as _ligne,
    preuve as _preuve,
    valeur_annotation as _valeur_annotation,
    valeurs_annotation as _valeurs_annotation,
)
from meridian.domain.liens_composants import Appel, Interface

__all__ = [
    "extraire_dotnet",
    "extraire_java",
    "extraire_javascript",
    "extraire_python",
]

_METHODES_SPRING = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
}
_METHODES_CLIENT = {
    "getForObject": "GET", "getForEntity": "GET",
    "postForObject": "POST", "postForEntity": "POST",
    "put": "PUT", "delete": "DELETE", "patchForObject": "PATCH",
}
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
_RE_PY_ROUTE = re.compile(
    r"@\s*(?:[\w.]+\.)?(get|post|put|patch|delete|head|options)\s*\(\s*[\"']([^\"']+)",
    re.I)
_RE_PY_FLASK = re.compile(
    r"@\s*[\w.]+\.route\s*\(\s*[\"']([^\"']+)[\"']"
    r"(?:[^)]*methods\s*=\s*\[([^\]]*)\])?", re.I)
_RE_PY_CLIENT = re.compile(
    r"\b(?:requests|httpx|session|client)\s*\.\s*"
    r"(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']+)", re.I)
_RE_PY_PREFIX = re.compile(
    r"\b(?:APIRouter|Blueprint)\s*\([^)]*\b(?:prefix|url_prefix)\s*=\s*[\"']([^\"']+)",
    re.I)
_RE_CS_ROUTE = re.compile(r"\[Route\s*\(\s*\"([^\"]+)\"\s*\)\]", re.I)
_RE_CS_METHOD = re.compile(
    r"\[Http(Get|Post|Put|Patch|Delete|Head|Options)(?:\s*\(\s*\"([^\"]*)\"\s*\))?\]",
    re.I)
_RE_CS_CLASS = re.compile(r"\bclass\s+(\w+Controller)\b")
_RE_CS_CLIENT = re.compile(
    r"\.(GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync|GetFromJsonAsync|"
    r"PostAsJsonAsync|PutAsJsonAsync)\s*\(\s*\"([^\"]+)\"", re.I)
_RE_JMS_SEND = re.compile(r"\b(?:jmsTemplate|jms|producer|template)\s*\.\s*"
                          r"(?:convertAndSend|send)\s*\(\s*[\"']([^\"']+)[\"']", re.I)
_RE_KAFKA_SEND = re.compile(r"\b(?:kafkaTemplate|kafka|producer)\s*\.\s*send\s*\(\s*"
                            r"[\"']([^\"']+)[\"']", re.I)
_VERBES_PY = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH",
              "delete": "DELETE", "head": "HEAD", "options": "OPTIONS"}


def extraire_java(texte: str, fichier: str, application: str, composant: str,
                  environment: str, service_name: str,
                  context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    diagnostics: list[str] = []
    observations = java_source.extraire(fichier, texte)
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    types = {o.attributes.get("fqn"): o for o in observations if o.kind == "java_type"}

    for observation in observations:
        if observation.kind not in ("spring_route", "jaxrs_route"):
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

    # Servlets JEE : @WebServlet("/chemin")
    for observation in observations:
        if observation.kind != "web_servlet":
            continue
        for chemin in _valeurs_annotation(
                observation.attributes, "value", "urlPatterns", "urlPattern"):
            chemin = _chemin(chemin)
            if not chemin:
                continue
            interfaces_.append(Interface(
                composant_id=composant, application_id=application, protocole="HTTP",
                operation=f"ANY {chemin}", methode="ANY", chemin=chemin,
                nom=str(observation.attributes.get("name") or chemin),
                environment=environment, source_kind="CODE",
                service_name=service_name, context_path=context_path,
                preuves=(_preuve("CODE", f"{fichier}:{observation.start}",
                                 f"Servlet {chemin}", confidence=0.85),),
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

    for observation in observations:
        if observation.kind != "jee_injection":
            continue
        cible = jndi_cible(observation.attributes or {})
        if not cible:
            continue
        appels.append(Appel(
            composant_id=composant, application_id=application, protocole="JNDI",
            cible=cible, cible_type="JNDI", methode="ANY", chemin=cible,
            operation=cible, environment=environment, source_kind="CODE",
            preuves=(_preuve("CODE", f"{fichier}:{observation.start}",
                             f"JNDI {cible}", confidence=0.85),),
        ))
    return interfaces_, appels, diagnostics


def extraire_dotnet(fichier: str, texte: str, application: str, composant: str,
                    environment: str, service_name: str,
                    context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    """ASP.NET : [Route]/[HttpGet] producteurs et HttpClient consommateurs."""
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    classe = _RE_CS_CLASS.search(texte)
    controleur = classe.group(1).removesuffix("Controller") if classe else ""
    route_classe = _RE_CS_ROUTE.search(texte)
    base = route_classe.group(1) if route_classe else ""
    base = base.replace("[controller]", controleur).replace("[action]", "")
    for trouve in _RE_CS_METHOD.finditer(texte):
        methode = trouve.group(1).upper()
        route = trouve.group(2) or ""
        chemin = _chemin(route) if route.startswith("/") else _chemin(base, route)
        if not chemin:
            continue
        interfaces_.append(Interface(
            composant_id=composant, application_id=application, protocole="HTTP",
            operation=f"{methode} {chemin}", methode=methode, chemin=chemin,
            nom=chemin, environment=environment, source_kind="CODE",
            service_name=service_name, context_path=context_path,
            preuves=(_preuve("CODE", f"{fichier}:{_ligne(texte, trouve.start())}",
                             f"ASP.NET {methode} {chemin}", confidence=0.85),),
        ))
    verbes = {"getasync": "GET", "postasync": "POST", "putasync": "PUT",
              "deleteasync": "DELETE", "patchasync": "PATCH",
              "getfromjsonasync": "GET", "postasjsonasync": "POST",
              "putasjsonasync": "PUT"}
    for trouve in _RE_CS_CLIENT.finditer(texte):
        methode = verbes.get(trouve.group(1).lower(), "ANY")
        appel = _appel_http(
            composant, application, fichier, _ligne(texte, trouve.start()),
            methode, trouve.group(2), "CODE", environment)
        if appel is not None:
            appels.append(appel)
    return interfaces_, appels, []


def _constante_python(node, constantes: Mapping[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    if isinstance(node, ast.Name):
        return str(constantes.get(node.id) or "").strip()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        gauche = _constante_python(node.left, constantes)
        droite = _constante_python(node.right, constantes)
        if gauche and droite:
            return gauche + droite
    return ""


def _methodes_python(node, constantes: Mapping[str, str]) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        valeurs = [_constante_python(element, constantes) for element in node.elts]
    else:
        valeur = _constante_python(node, constantes)
        valeurs = re.findall(r"[\"'](\w+)[\"']", valeur) if valeur else []
    return [valeur.upper() for valeur in valeurs
            if valeur.upper() in _VERBES_PY.values()] or ["GET"]


def _extraire_python_ast(fichier: str, texte: str, application: str, composant: str,
                         environment: str, service_name: str,
                         context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    """FastAPI/Flask et requests/httpx par AST : commentaires et chaînes hors code ignorés."""
    arbre = ast.parse(texte, filename=fichier)
    constantes: dict[str, str] = {}
    prefixes: dict[str, str] = {}
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        cible = node.targets[0]
        if not isinstance(cible, ast.Name):
            continue
        valeur = _constante_python(node.value, constantes)
        if valeur:
            constantes[cible.id] = valeur
        if isinstance(node.value, ast.Call):
            fonction = node.value.func
            nom = (fonction.id if isinstance(fonction, ast.Name)
                   else fonction.attr if isinstance(fonction, ast.Attribute) else "")
            if nom in ("APIRouter", "Blueprint"):
                prefixe = next((mot.arg for mot in node.value.keywords
                                if mot.arg in ("prefix", "url_prefix")), "")
                if prefixe:
                    prefixes[cible.id] = next(
                        (_constante_python(mot.value, constantes) for mot in node.value.keywords
                         if mot.arg in ("prefix", "url_prefix")), "")
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    vus = set()
    for node in ast.walk(arbre):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorateur in node.decorator_list:
            if not isinstance(decorateur, ast.Call) or not isinstance(
                    decorateur.func, ast.Attribute):
                continue
            attribut = decorateur.func.attr.lower()
            base = decorateur.func.value
            nom_base = (base.id if isinstance(base, ast.Name)
                        else base.attr if isinstance(base, ast.Attribute) else "")
            prefixe = prefixes.get(nom_base, "")
            if attribut in _VERBES_PY:
                methode = _VERBES_PY[attribut]
                route = _constante_python(decorateur.args[0], constantes) if decorateur.args else ""
                methodes = [methode]
            elif attribut in ("route", "api_route"):
                route = _constante_python(decorateur.args[0], constantes) if decorateur.args else ""
                liste = next((mot.value for mot in decorateur.keywords
                              if mot.arg == "methods"), None)
                methodes = _methodes_python(liste, constantes) if liste is not None else ["GET"]
            else:
                continue
            chemin = _chemin(prefixe, route)
            if not chemin:
                continue
            for methode in methodes:
                if (methode, chemin) in vus:
                    continue
                vus.add((methode, chemin))
                interfaces_.append(Interface(
                    composant_id=composant, application_id=application, protocole="HTTP",
                    operation=f"{methode} {chemin}", methode=methode, chemin=chemin,
                    nom=node.name, environment=environment, source_kind="CODE",
                    service_name=service_name, context_path=context_path,
                    preuves=(_preuve("CODE", f"{fichier}:{node.lineno}",
                                     f"Python AST {methode} {chemin}", confidence=0.95),),
                ))
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        base = node.func.value
        nom_base = (base.id if isinstance(base, ast.Name)
                    else base.attr if isinstance(base, ast.Attribute) else "")
        methode = _VERBES_PY.get(node.func.attr.lower())
        if methode is None or nom_base not in ("requests", "httpx", "session", "client"):
            continue
        if not node.args:
            continue
        cible = _constante_python(node.args[0], constantes)
        if not cible:
            continue
        appel = _appel_http(composant, application, fichier, node.lineno, methode,
                            cible, "CODE", environment)
        if appel is not None:
            appels.append(appel)
    return interfaces_, appels, []


def extraire_python(fichier: str, texte: str, application: str, composant: str,
                    environment: str, service_name: str,
                    context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    try:
        return _extraire_python_ast(
            fichier, texte, application, composant, environment,
            service_name, context_path)
    except (SyntaxError, ValueError, RecursionError) as exc:
        interfaces_, appels, diagnostics = _extraire_python_regex(
            fichier, texte, application, composant, environment,
            service_name, context_path)
        diagnostics.append(
            f"{fichier} : AST Python indisponible ({type(exc).__name__}), repli textuel")
        return interfaces_, appels, diagnostics


def _extraire_python_regex(fichier: str, texte: str, application: str, composant: str,
                           environment: str, service_name: str,
                           context_path: str) -> tuple[list[Interface], list[Appel], list[str]]:
    """Repli textuel pour un fichier Python que `ast` ne peut pas lire."""
    interfaces_: list[Interface] = []
    appels: list[Appel] = []
    prefixe = ""
    trouve_prefixe = _RE_PY_PREFIX.search(texte)
    if trouve_prefixe:
        prefixe = _chemin(trouve_prefixe.group(1))
    vus = set()
    for trouve in _RE_PY_ROUTE.finditer(texte):
        methode, route = trouve.group(1).upper(), _chemin(prefixe, trouve.group(2))
        if not route or (methode, route) in vus:
            continue
        vus.add((methode, route))
        interfaces_.append(Interface(
            composant_id=composant, application_id=application, protocole="HTTP",
            operation=f"{methode} {route}", methode=methode, chemin=route,
            nom=route, environment=environment, source_kind="CODE",
            service_name=service_name, context_path=context_path,
            preuves=(_preuve("CODE", f"{fichier}:{_ligne(texte, trouve.start())}",
                             f"Python {methode} {route}", confidence=0.85),),
        ))
    for trouve in _RE_PY_FLASK.finditer(texte):
        route = _chemin(prefixe, trouve.group(1))
        if not route:
            continue
        methodes = re.findall(r"[\"'](\w+)[\"']", trouve.group(2) or "")
        for methode in (methodes or ("GET",)):
            methode = methode.upper()
            if (methode, route) in vus:
                continue
            vus.add((methode, route))
            interfaces_.append(Interface(
                composant_id=composant, application_id=application, protocole="HTTP",
                operation=f"{methode} {route}", methode=methode, chemin=route,
                nom=route, environment=environment, source_kind="CODE",
                service_name=service_name, context_path=context_path,
                preuves=(_preuve("CODE", f"{fichier}:{_ligne(texte, trouve.start())}",
                                 f"Flask {methode} {route}", confidence=0.85),),
            ))
    for trouve in _RE_PY_CLIENT.finditer(texte):
        appel = _appel_http(
            composant, application, fichier, _ligne(texte, trouve.start()),
            trouve.group(1).upper(), trouve.group(2), "CODE", environment)
        if appel is not None:
            appels.append(appel)
    return interfaces_, appels, []


def extraire_javascript(fichier: str, texte: str, application: str, composant: str,
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
