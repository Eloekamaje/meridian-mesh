"""Compilation des opérations d'interface en manifestes d'outils (ADR-0004).

Un graphe d'interfaces déjà lu (OpenAPI, WSDL, configuration, claims) devient une liste de manifestes
capacitaires. REST, SOAP et gRPC sont reconnus : une opération de lecture devient `observer`, une
écriture devient `agir` avec un effet de bord explicite. Le module est pur : ni base, ni réseau, ni
exécution, ni secret. La provenance `interface` et le protocole dans la description qualifient le manifeste produit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import re
import unicodedata
from typing import Any

from jumeau import interfaces
from jumeau.capacites import ManifesteOutil, RegistreCapacites

__all__ = ["charger_dans", "main", "manifests_depuis_interface"]

_METHODES_LECTURE = frozenset({"GET", "HEAD", "OPTIONS"})
_PREFIXES_LECTURE_SOAP = ("get", "list", "read", "find", "search", "query", "fetch", "describe", "lookup")
_PREFIXES_LECTURE_GRPC = ("get", "list", "read", "search", "watch", "stream", "query", "fetch", "describe")
_RE_NON_NOM = re.compile(r"[^a-z0-9_]+")
_RE_SEPARATEURS = re.compile(r"[-_]{2,}")
_RE_URL = re.compile(r"(?i)(?:[a-z][a-z0-9+.\-]*://|(?<![\w.])www\.[a-z0-9])")
_RE_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_RE_AFFECTATION_SENSIBLE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)
_RE_JETON_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}")
_RE_WSDL = re.compile(r"<\s*(?:[\w.-]+:)?definitions\b", re.IGNORECASE)
_RE_OPENAPI = re.compile(r"(?im)^\s*(?:openapi|swagger)\s*:|[\"'](?:openapi|swagger)[\"']\s*:")
_LONGUEUR_NOM_MAX = 80
_LONGUEUR_TEXTE_MAX = 200
_LIBELLES_PROTOCOLE = {"rest": "REST", "soap": "SOAP", "grpc": "gRPC", "graphql": "GraphQL",
                       "asyncapi": "AsyncAPI"}


def _champ(objet: Any, nom: str, defaut: Any = None) -> Any:
    if isinstance(objet, Mapping):
        return objet.get(nom, defaut)
    return getattr(objet, nom, defaut)


def _texte(valeur: Any) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _segment(valeur: Any) -> str:
    """Un fragment de nom stable : minuscules, chiffres et séparateurs simples."""
    brut = unicodedata.normalize("NFKD", str(valeur or ""))
    brut = "".join(caractere for caractere in brut if not unicodedata.combining(caractere)).lower()
    brut = _RE_NON_NOM.sub("-", brut)
    brut = _RE_SEPARATEURS.sub("-", brut).strip("_-")
    return brut


def _slug_application(application_id: Any) -> str:
    segment = _segment(application_id) or "application"
    if not segment[0].isalpha():
        segment = f"a-{segment}"
    return segment


def _nom_operation(operation: Any, action: str | None) -> str:
    nom = _segment(_champ(operation, "name"))
    if nom:
        return nom
    methode = _texte(_champ(operation, "method")) or ""
    return _segment(f"{methode} {action or ''}") or "operation"


def _nom_unique(base: str, empreinte: str, utilises: set[str]) -> str:
    if base not in utilises and len(base) <= _LONGUEUR_NOM_MAX:
        return base
    digest = hashlib.sha256(empreinte.encode("utf-8")).hexdigest()[:8]
    racine = base
    if len(racine) > _LONGUEUR_NOM_MAX - 9:
        racine = racine[:_LONGUEUR_NOM_MAX - 9].rstrip("._-")
    candidat = f"{racine}-{digest}"
    compteur = 1
    while candidat in utilises:
        suffixe = f"-{digest}-{compteur}"
        racine = base[:_LONGUEUR_NOM_MAX - len(suffixe)].rstrip("._-")
        candidat = f"{racine}{suffixe}"
        compteur += 1
    return candidat


def _texte_propre(valeur: Any, longueur_max: int = _LONGUEUR_TEXTE_MAX) -> str | None:
    """Un texte utilisable dans un manifeste : ni URL, ni HTML, ni affectation de secret."""
    if valeur is None:
        return None
    texte = " ".join(str(valeur).split())
    if not texte:
        return None
    if len(texte) > longueur_max:
        texte = texte[:longueur_max].rstrip()
    if _RE_URL.search(texte) or _RE_HTML.search(texte):
        return None
    if _RE_AFFECTATION_SENSIBLE.search(texte) or _RE_JETON_BEARER.search(texte):
        return None
    return texte or None


def _protocole(operation: Any, contrat: Any) -> str:
    brut = (_texte(_champ(operation, "protocol")) or "").lower()
    format_contrat = (_texte(_champ(contrat, "format")) or "").lower()
    if brut == "soap" or format_contrat == "wsdl":
        return "soap"
    if brut == "grpc" or format_contrat == "grpc":
        return "grpc"
    if brut == "graphql" or format_contrat == "graphql":
        return "graphql"
    if brut == "asyncapi" or format_contrat == "asyncapi":
        return "asyncapi"
    return "rest"


def _commence_par(valeur: Any, prefixes: tuple[str, ...]) -> bool:
    texte = _texte(valeur)
    if texte is None:
        return False
    normalise = texte.lower()
    candidats = {normalise}
    for separateur in ("/", "#", ":", "."):
        if separateur in normalise:
            candidats.add(normalise.rsplit(separateur, 1)[-1])
    return any(candidat.startswith(prefixe) for candidat in candidats for prefixe in prefixes)


def _effet(prefixe: str, valeur: Any, secours: Any) -> str:
    texte = _texte_propre(valeur) or _texte_propre(secours) or "operation"
    return f"{prefixe}:{texte}"


def _description(application: Any, protocole: str, operation: Any, action: Any, environment: Any) -> str:
    app = _texte_propre(application) or "application"
    env = _texte_propre(environment, 100) or "inconnu"
    nom = _texte_propre(_champ(operation, "name")) or _texte_propre(action) or "operation"
    action_propre = _texte_propre(action)
    libelle = _LIBELLES_PROTOCOLE.get(protocole, protocole.upper())
    if protocole == "rest":
        methode = _texte_propre(_champ(operation, "method"), 20) or "HTTP"
        debut = f"Opération {libelle} {methode} {nom}"
    else:
        debut = f"Opération {libelle} {nom}"
    if action_propre and action_propre != nom:
        debut = f"{debut} ({action_propre})"
    return f"{debut} de l'application {app} en environnement {env}."


def _manifeste_interface(valeurs: dict[str, Any]) -> ManifesteOutil:
    return ManifesteOutil(source="interface", **valeurs)


def _operations_et_contrats(graph: Any) -> tuple[list[Any], list[Any]]:
    if graph is None:
        return [], []
    if isinstance(graph, Mapping):
        if "operations" in graph or "contracts" in graph:
            operations = graph.get("operations") or []
            contrats = graph.get("contracts") or []
            return list(operations), list(contrats)
        return [graph], []
    if isinstance(graph, (list, tuple)):
        return list(graph), []
    operations = getattr(graph, "operations", None)
    contrats = getattr(graph, "contracts", None)
    if operations is None and contrats is None:
        raise TypeError("graphe d'interfaces, opérations ou objet avec operations/contracts attendu")
    return list(operations or []), list(contrats or [])


def _index_contrats(contrats: list[Any]) -> dict[Any, Any]:
    index: dict[Any, Any] = {}
    for contrat in contrats:
        identifiant = _champ(contrat, "id")
        if identifiant is not None:
            index[identifiant] = contrat
    return index


def manifests_depuis_interface(
    graph: Any,
    version: str = "1.0.0",
    tenant: Any = None,
    acteur: Any = None,
    perimetre: Any = None,
) -> list[ManifesteOutil]:
    """Rend un manifeste par opération connue, REST, SOAP ou gRPC, sans exécution ni secret.

    `graph` est un `InterfaceGraph`, un objet portant `operations`/`contracts`, ou une liste/tuple
    d'opérations (objets ou mappings). L'application vient du contrat correspondant, sinon de
    l'environnement de l'opération, sinon de `application`. Les lectures sont `observer` avec preuve
    `OBSERVED` ; les écritures sont `agir` avec un effet de bord explicite et aucune preuve.
    """
    operations, contrats = _operations_et_contrats(graph)
    index = _index_contrats(contrats)
    manifestes: list[ManifesteOutil] = []
    noms: set[str] = set()
    for operation in operations:
        contrat = index.get(_champ(operation, "contract_id"))
        environnement = _texte(_champ(operation, "environment"))
        if environnement is None and contrat is not None:
            environnement = _texte(_champ(contrat, "environment"))
        application = _texte(_champ(contrat, "application_id")) if contrat is not None else None
        application = application or environnement or "application"

        protocole = _protocole(operation, contrat)
        methode_brute = _texte(_champ(operation, "method")) or ""
        methode = methode_brute.upper()
        nom_operation = _texte(_champ(operation, "name"))
        action = (_texte(_champ(operation, "path")) or _texte(_champ(operation, "action"))
                  or nom_operation or "")

        if protocole == "soap":
            lecture_seule = (_commence_par(nom_operation, _PREFIXES_LECTURE_SOAP)
                             or _commence_par(action, _PREFIXES_LECTURE_SOAP))
            effets = () if lecture_seule else (_effet("soap", action, nom_operation),)
        elif protocole == "grpc":
            lecture_seule = (_commence_par(nom_operation, _PREFIXES_LECTURE_GRPC)
                             or _commence_par(action, _PREFIXES_LECTURE_GRPC)
                             or _commence_par(methode_brute, _PREFIXES_LECTURE_GRPC))
            effets = () if lecture_seule else (
                _effet("grpc", methode_brute or action, nom_operation),)
        elif protocole == "graphql":
            lecture_seule = methode in ("QUERY", "SUBSCRIPTION")
            effets = () if lecture_seule else (_effet("graphql", nom_operation or action, "mutation"),)
        elif protocole == "asyncapi":
            lecture_seule = methode in ("SUBSCRIBE", "RECEIVE")
            effets = () if lecture_seule else (_effet("asyncapi", action or nom_operation, "publish"),)
        else:
            lecture_seule = methode in _METHODES_LECTURE
            effets = () if lecture_seule else (_effet("http", methode or "UNKNOWN", "operation"),)

        base = f"{_slug_application(application)}.{_nom_operation(operation, action)}"
        empreinte = "|".join(str(partie or "") for partie in (
            protocole, methode, action, nom_operation, _champ(operation, "contract_id")))
        nom = _nom_unique(base, empreinte, noms)
        noms.add(nom)

        valeurs = {
            "nom": nom,
            "version": version,
            "description": _description(application, protocole, operation, action, environnement),
            "capacite": "observer" if lecture_seule else "agir",
            "schema_entree": {},
            "schema_sortie": {},
            "tenant": tenant,
            "acteur": acteur,
            "perimetre": perimetre,
            "lecture_seule": lecture_seule,
            "cout": 0.0,
            "timeout_ms": 5000,
            "mode_preuve": "OBSERVED" if lecture_seule else "AUCUNE",
            "effets_de_bord": effets,
        }
        manifestes.append(_manifeste_interface(valeurs))
    return manifestes


def charger_dans(
    registre: RegistreCapacites,
    graph: Any,
    version: str = "1.0.0",
    tenant: Any = None,
    acteur: Any = None,
    perimetre: Any = None,
) -> list[str]:
    """Génère puis enregistre les manifestes dans un `RegistreCapacites` ; rend leurs noms.

    Les doublons et conflits de version restent la décision du registre : ce module ne les masque pas.
    """
    enregistrer = getattr(registre, "enregistrer", None)
    if not callable(enregistrer):
        raise TypeError("registre capacitaire attendu")
    noms: list[str] = []
    for manifeste in manifests_depuis_interface(graph, version, tenant, acteur, perimetre):
        enregistrer(manifeste)
        noms.append(manifeste.nom)
    return noms


def _detecter_format(locator: str, texte: str) -> str:
    debut = texte.lstrip()[:4096]
    if _RE_WSDL.search(debut):
        return "wsdl"
    if _RE_OPENAPI.search(debut):
        return "openapi"
    suffixe = Path(locator).suffix.lower()
    if suffixe == ".wsdl":
        return "wsdl"
    if suffixe in (".json", ".yaml", ".yml"):
        return "openapi"
    return "wsdl" if debut.startswith("<") else "openapi"


def main(argv: Any = None) -> int:
    """Compile un fichier OpenAPI ou WSDL en noms de manifestes, sans réseau ni exécution."""
    analyseur = argparse.ArgumentParser(
        description="Compile les opérations d'un fichier OpenAPI ou WSDL en noms de manifestes.")
    analyseur.add_argument("--application", required=True)
    analyseur.add_argument("--fichier", required=True)
    analyseur.add_argument("--tenant")
    analyseur.add_argument("--acteur")
    analyseur.add_argument("--perimetre")
    arguments = analyseur.parse_args(argv)
    try:
        texte = Path(arguments.fichier).read_text(encoding="utf-8")
    except OSError as erreur:
        analyseur.error(f"fichier illisible : {erreur}")
    if _detecter_format(arguments.fichier, texte) == "wsdl":
        graphe = interfaces.parse_wsdl(arguments.application, texte, arguments.fichier)
    else:
        graphe = interfaces.parse_openapi(arguments.application, texte, arguments.fichier)
    manifestes = manifests_depuis_interface(
        graphe, tenant=arguments.tenant, acteur=arguments.acteur, perimetre=arguments.perimetre)
    print(json.dumps([manifeste.nom for manifeste in manifestes], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
