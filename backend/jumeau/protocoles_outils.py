"""Génération de manifestes d'outils depuis GraphQL, gRPC et AsyncAPI (ADR-0004).

Chaque champ, méthode ou opération devient un contrat déclaratif du registre capacitaire : lecture seule pour les
requêtes, abonnements et réceptions, écriture explicite pour les mutations et publications. Le module ne fait aucun
appel réseau, ne charge aucun code, ne copie aucun payload et n'exécute aucun outil.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from jumeau import interfaces
from jumeau.capacites import ManifesteOutil, RegistreCapacites

__all__ = [
    "ErreurProtocoles",
    "charger_dans",
    "manifests_asyncapi",
    "manifests_graphql",
    "manifests_grpc",
    "operations_asyncapi",
    "operations_graphql",
    "operations_grpc",
]

_LONGUEUR_NOM_MAX = 80
_PREFIXES_LECTURE_GRPC = (
    "get", "list", "read", "search", "watch", "stream", "query", "fetch", "describe", "lookup",
)
_LECTURES_ASYNCAPI = frozenset({"subscribe", "receive"})
_RE_NON_NOM = re.compile(r"[^a-z0-9_]+")
_RE_SEPARATEURS = re.compile(r"[-_]{2,}")
_RE_NOM = re.compile(r"[_A-Za-z][_0-9A-Za-z]*")
_RE_TYPE_GRAPHQL = re.compile(r"(?<![\w.])(?:extend\s+)?type\s+(Query|Mutation|Subscription)\b")
_RE_SERVICE = re.compile(r"(?<![\w.])service\s+([A-Za-z_]\w*)\s*\{")
_RE_RPC = re.compile(
    r"(?<![\w.])rpc\s+([A-Za-z_]\w*)\s*\(\s*(?:stream\s+)?[\w.]+\s*\)\s*"
    r"returns\s*\(\s*(?:stream\s+)?[\w.]+\s*\)"
)
_OUVRANTS = {"(": ")", "[": "]", "{": "}"}


class ErreurProtocoles(ValueError):
    """Le document de protocole est invalide ou illisible."""


def _segment(valeur: Any) -> str:
    """Un fragment de nom stable : minuscules, chiffres et séparateurs simples."""
    brut = unicodedata.normalize("NFKD", str(valeur or ""))
    brut = "".join(caractere for caractere in brut if not unicodedata.combining(caractere)).lower()
    brut = _RE_NON_NOM.sub("-", brut)
    return _RE_SEPARATEURS.sub("-", brut).strip("_-")


def _slug_application(application_id: str) -> str:
    segment = _segment(application_id) or "application"
    if not segment[0].isalpha():
        segment = f"a-{segment}"
    return segment


def _nom_unique(base: str, identite: str, utilises: set[str]) -> str:
    if base not in utilises and len(base) <= _LONGUEUR_NOM_MAX:
        return base
    empreinte = hashlib.sha256(identite.encode("utf-8")).hexdigest()[:8]
    racine = base
    if len(racine) > _LONGUEUR_NOM_MAX - 9:
        racine = racine[: _LONGUEUR_NOM_MAX - 9].rstrip("._-")
    candidat = f"{racine}-{empreinte}"
    compteur = 1
    while candidat in utilises:
        suffixe = f"-{empreinte}-{compteur}"
        racine = base[: _LONGUEUR_NOM_MAX - len(suffixe)].rstrip("._-")
        candidat = f"{racine}{suffixe}"
        compteur += 1
    return candidat


def _masquer(fragment: str) -> str:
    return "".join("\n" if caractere == "\n" else " " for caractere in fragment)


def _texte_structurel(texte: str) -> str:
    """Neutralise chaînes et commentaires sans déplacer les positions du document."""
    sortie: list[str] = []
    i = 0
    taille = len(texte)
    while i < taille:
        if texte.startswith('"""', i):
            fin = texte.find('"""', i + 3)
            fin = taille if fin < 0 else fin + 3
            sortie.append(_masquer(texte[i:fin]))
            i = fin
            continue
        caractere = texte[i]
        if caractere in "\"'":
            j = i + 1
            while j < taille:
                if texte[j] == "\\":
                    j += 2
                    continue
                if texte[j] == caractere:
                    j += 1
                    break
                j += 1
            j = min(j, taille)
            sortie.append(_masquer(texte[i:j]))
            i = j
            continue
        if texte.startswith("/*", i) or texte.startswith("//", i) or caractere == "#":
            if texte.startswith("/*", i):
                fin = texte.find("*/", i + 2)
                fin = taille if fin < 0 else fin + 2
            else:
                fin = texte.find("\n", i)
                fin = taille if fin < 0 else fin
            sortie.append(_masquer(texte[i:fin]))
            i = fin
            continue
        sortie.append(caractere)
        i += 1
    return "".join(sortie)


def _sauter_espaces(texte: str, debut: int) -> int:
    while debut < len(texte) and texte[debut].isspace():
        debut += 1
    return debut


def _sauter_bloc(texte: str, debut: int) -> int:
    if debut >= len(texte) or texte[debut] not in _OUVRANTS:
        return debut + 1
    pile = [_OUVRANTS[texte[debut]]]
    i = debut + 1
    while i < len(texte) and pile:
        caractere = texte[i]
        if caractere in _OUVRANTS:
            pile.append(_OUVRANTS[caractere])
        elif caractere == pile[-1]:
            pile.pop()
        i += 1
    return i


def _sauter_directive(texte: str, debut: int) -> int:
    i = debut + 1
    correspondance = _RE_NOM.match(texte, i)
    if correspondance is not None:
        i = correspondance.end()
    i = _sauter_espaces(texte, i)
    if i < len(texte) and texte[i] == "(":
        i = _sauter_bloc(texte, i)
    return i


def _sauter_type_graphql(texte: str, debut: int) -> int:
    i = _sauter_espaces(texte, debut)
    if i < len(texte) and texte[i] == "[":
        i = _sauter_type_graphql(texte, i + 1)
        i = _sauter_espaces(texte, i)
        if i < len(texte) and texte[i] == "]":
            i += 1
    else:
        correspondance = _RE_NOM.match(texte, i)
        if correspondance is not None:
            i = correspondance.end()
    i = _sauter_espaces(texte, i)
    if i < len(texte) and texte[i] == "!":
        i += 1
    return i


def _champs_graphql(corps: str) -> list[str]:
    champs: list[str] = []
    i = 0
    taille = len(corps)
    while i < taille:
        i = _sauter_espaces(corps, i)
        if i >= taille:
            break
        caractere = corps[i]
        if caractere in ",}":
            i += 1
            continue
        if caractere == "@":
            i = _sauter_directive(corps, i)
            continue
        correspondance = _RE_NOM.match(corps, i)
        if correspondance is None:
            i += 1
            continue
        nom = correspondance.group(0)
        i = _sauter_espaces(corps, correspondance.end())
        if i < taille and corps[i] == "(":
            i = _sauter_bloc(corps, i)
            i = _sauter_espaces(corps, i)
        if i >= taille or corps[i] != ":":
            continue
        i = _sauter_type_graphql(corps, i + 1)
        while True:
            i = _sauter_espaces(corps, i)
            if i < taille and corps[i] == "@":
                i = _sauter_directive(corps, i)
                continue
            break
        if not nom.startswith("__"):
            champs.append(nom)
    return champs


def _premiere_accolade(texte: str, debut: int) -> int | None:
    i = debut
    while i < len(texte):
        if texte[i] in "([":
            i = _sauter_bloc(texte, i)
            continue
        if texte[i] == "{":
            return i
        i += 1
    return None


def _champs_par_type(sdl: str) -> dict[str, list[str]]:
    structurel = _texte_structurel(sdl)
    champs = {"Query": [], "Mutation": [], "Subscription": []}
    for correspondance in _RE_TYPE_GRAPHQL.finditer(structurel):
        ouvrante = _premiere_accolade(structurel, correspondance.end())
        if ouvrante is None:
            continue
        fin = _sauter_bloc(structurel, ouvrante)
        corps = structurel[ouvrante + 1: max(ouvrante + 1, fin - 1)]
        champs[correspondance.group(1)].extend(_champs_graphql(corps))
    return champs


def _description_graphql(application: str, champ: str, genre: str) -> str:
    if genre == "Mutation":
        return (
            f"Mutation GraphQL « {champ} » de l'application {application} : écriture déclarée, "
            "sans exécution automatique."
        )
    if genre == "Subscription":
        return (
            f"Abonnement GraphQL « {champ} » de l'application {application} : flux (stream) en lecture seule, "
            "sans effet de bord."
        )
    return (
        f"Requête GraphQL « {champ} » de l'application {application} : lecture seule, sans effet de bord."
    )


def _description_grpc(application: str, service: str, methode: str, lecture_seule: bool) -> str:
    if lecture_seule:
        return (
            f"RPC gRPC « {service}.{methode} » de l'application {application} : lecture seule, "
            "sans effet de bord."
        )
    return (
        f"RPC gRPC « {service}.{methode} » de l'application {application} : écriture déclarée, "
        "sans exécution automatique."
    )


def _description_asyncapi(application: str, canal: str, identifiant: str, sens: str) -> str:
    if sens in _LECTURES_ASYNCAPI:
        action = "réception en lecture seule, sans effet de bord"
    else:
        action = "publication en écriture déclarée, sans exécution automatique"
    return (
        f"Opération AsyncAPI « {identifiant} » du canal « {canal} » de l'application {application} : {action}."
    )


def _manifeste(
    nom: str,
    version: str,
    description: str,
    lecture_seule: bool,
    effet: str | None,
    source: str,
    tenant: Any,
    acteur: Any,
    perimetre: Any,
) -> ManifesteOutil:
    return ManifesteOutil(
        nom=nom,
        version=version,
        description=description,
        capacite="observer" if lecture_seule else "agir",
        schema_entree={},
        schema_sortie={},
        tenant=tenant,
        acteur=acteur,
        perimetre=perimetre,
        lecture_seule=lecture_seule,
        cout=0.0,
        timeout_ms=5000,
        mode_preuve="OBSERVED" if lecture_seule else "AUCUNE",
        effets_de_bord=() if lecture_seule else (effet or "",),
        source=source,
    )


def _application(application_id: Any) -> str:
    if not isinstance(application_id, str) or not application_id.strip():
        raise ErreurProtocoles("application_id : chaîne non vide attendue")
    return application_id.strip()


def operations_graphql(sdl: str) -> list[dict]:
    """Rend les champs Query/Mutation/Subscription sans exécuter la requête."""
    if not isinstance(sdl, str) or not sdl.strip():
        return []
    champs = _champs_par_type(sdl)
    return [
        {"genre": genre, "nom": nom, "lecture_seule": genre != "Mutation"}
        for genre in ("Query", "Mutation", "Subscription")
        for nom in champs[genre]
    ]


def operations_grpc(proto_text: str) -> list[dict]:
    """Rend les rpc d'un fichier protobuf, service et méthode, sans compiler le proto."""
    if not isinstance(proto_text, str) or not proto_text.strip():
        return []
    structurel = _texte_structurel(proto_text)
    resultats = []
    for service in _RE_SERVICE.finditer(structurel):
        nom_service = service.group(1)
        ouvrante = service.end() - 1
        fin = _sauter_bloc(structurel, ouvrante)
        corps = structurel[ouvrante + 1: max(ouvrante + 1, fin - 1)]
        for rpc in _RE_RPC.finditer(corps):
            resultats.append({
                "service": nom_service,
                "methode": rpc.group(1),
                "lecture_seule": rpc.group(1).lower().startswith(_PREFIXES_LECTURE_GRPC),
            })
    return resultats


def operations_asyncapi(document: Any) -> list[dict]:
    """Rend les opérations AsyncAPI (canal, identifiant, sens) sans lire le payload."""
    charge = _document_asyncapi(document)
    if charge is None:
        return []
    return [
        {"canal": canal, "identifiant": identifiant, "sens": sens,
         "lecture_seule": sens in _LECTURES_ASYNCAPI}
        for canal, identifiant, sens in _operations_asyncapi(charge)
    ]


def manifests_graphql(
    application_id: str,
    sdl: str,
    version: str = "1.0.0",
    tenant: Any = None,
    acteur: Any = None,
    perimetre: Any = None,
) -> list[ManifesteOutil]:
    """Lit une SDL GraphQL et rend un manifeste par champ de Query, Mutation et Subscription.

    Les requêtes et abonnements sont des lectures (`observer`, `OBSERVED`) ; une mutation est une écriture
    (`agir`, effet `graphql:mutation`). Les champs d'introspection `__...` sont ignorés. Aucun schéma d'entrée
    ni de sortie n'est inventé : le contrat reste déclaratif.
    """
    application = _application(application_id)
    if not isinstance(sdl, str):
        raise ErreurProtocoles("sdl : texte GraphQL attendu")
    if not sdl.strip():
        return []

    noms: set[str] = set()
    manifestes: list[ManifesteOutil] = []
    champs = _champs_par_type(sdl)
    for genre in ("Query", "Mutation", "Subscription"):
        for champ in champs[genre]:
            lecture_seule = genre != "Mutation"
            base = f"{_slug_application(application)}.graphql.{_segment(champ) or 'champ'}"
            nom = _nom_unique(base, f"graphql:{genre}:{champ}", noms)
            noms.add(nom)
            manifestes.append(_manifeste(
                nom=nom,
                version=version,
                description=_description_graphql(application, champ, genre),
                lecture_seule=lecture_seule,
                effet=None if lecture_seule else "graphql:mutation",
                source="graphql",
                tenant=tenant,
                acteur=acteur,
                perimetre=perimetre,
            ))
    return manifestes


def manifests_grpc(
    application_id: str,
    proto_text: str,
    version: str = "1.0.0",
    tenant: Any = None,
    acteur: Any = None,
    perimetre: Any = None,
) -> list[ManifesteOutil]:
    """Lit un fichier `.proto` et rend un manifeste par `rpc`, commentaires ignorés.

    Les méthodes dont le nom commence par un verbe de lecture sont des lectures (`observer`, `OBSERVED`) ;
    les autres sont des écritures (`agir`, effet `grpc:<service>.<methode>`, `AUCUNE`).
    """
    application = _application(application_id)
    if not isinstance(proto_text, str):
        raise ErreurProtocoles("proto_text : texte protobuf attendu")
    if not proto_text.strip():
        return []

    structurel = _texte_structurel(proto_text)
    noms: set[str] = set()
    manifestes: list[ManifesteOutil] = []
    for service in _RE_SERVICE.finditer(structurel):
        nom_service = service.group(1)
        ouvrante = service.end() - 1
        fin = _sauter_bloc(structurel, ouvrante)
        corps = structurel[ouvrante + 1: max(ouvrante + 1, fin - 1)]
        for rpc in _RE_RPC.finditer(corps):
            methode = rpc.group(1)
            lecture_seule = methode.lower().startswith(_PREFIXES_LECTURE_GRPC)
            base = f"{_slug_application(application)}.grpc.{_segment(methode) or 'methode'}"
            nom = _nom_unique(base, f"grpc:{nom_service}:{methode}", noms)
            noms.add(nom)
            manifestes.append(_manifeste(
                nom=nom,
                version=version,
                description=_description_grpc(application, nom_service, methode, lecture_seule),
                lecture_seule=lecture_seule,
                effet=None if lecture_seule else f"grpc:{nom_service}.{methode}",
                source="grpc",
                tenant=tenant,
                acteur=acteur,
                perimetre=perimetre,
            ))
    return manifestes


def _ref_canal(valeur: str) -> str:
    prefixe = "#/channels/"
    if valeur.startswith(prefixe):
        morceau = valeur[len(prefixe):].split("/", 1)[0]
        return morceau.replace("~1", "/").replace("~0", "~") or "canal"
    return valeur.strip() or "canal"


def _nom_canal(valeur: Any) -> str | None:
    if isinstance(valeur, Mapping):
        reference = valeur.get("$ref")
        if isinstance(reference, str):
            return _ref_canal(reference)
        for cle in ("address", "name", "channel"):
            nom = _nom_canal(valeur.get(cle))
            if nom:
                return nom
        return None
    if isinstance(valeur, str):
        return _ref_canal(valeur)
    return None


def _operations_asyncapi(document: Mapping) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    canaux = document.get("channels")
    if isinstance(canaux, Mapping):
        for canal, element in canaux.items():
            if not isinstance(canal, str) or not isinstance(element, Mapping):
                continue
            for cle, sens in (("publish", "publish"), ("subscribe", "subscribe")):
                operation = element.get(cle)
                if not isinstance(operation, Mapping):
                    continue
                identifiant = operation.get("operationId") or operation.get("name") or canal
                candidates.append((canal, str(identifiant), sens))

    operations = document.get("operations")
    if isinstance(operations, Mapping):
        for cle, operation in operations.items():
            if not isinstance(operation, Mapping):
                continue
            action = operation.get("action")
            if not isinstance(action, str) or action.strip().lower() not in ("send", "receive"):
                continue
            sens = action.strip().lower()
            canal = _nom_canal(operation.get("channel")) or "canal"
            identifiant = operation.get("operationId") or operation.get("name") or str(cle)
            candidates.append((canal, str(identifiant), sens))

    uniques: list[tuple[str, str, str]] = []
    vus: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        if candidate not in vus:
            vus.add(candidate)
            uniques.append(candidate)
    return uniques


def _document_asyncapi(document: Any) -> Mapping | None:
    if isinstance(document, str):
        if not document.strip():
            return None
        donnees, erreur = interfaces._charger_document(document)
        if erreur is not None:
            raise ErreurProtocoles(f"document AsyncAPI illisible : {erreur}")
        document = donnees
    if document is None:
        return None
    if not isinstance(document, Mapping):
        raise ErreurProtocoles("document AsyncAPI : objet attendu")
    return document


def manifests_asyncapi(
    application_id: str,
    document: Any,
    version: str = "1.0.0",
    tenant: Any = None,
    acteur: Any = None,
    perimetre: Any = None,
) -> list[ManifesteOutil]:
    """Lit un document AsyncAPI (dict, JSON ou YAML) et rend un manifeste par opération.

    `subscribe` et `receive` sont des lectures (`observer`, `OBSERVED`) ; `publish` et `send` sont des
    écritures (`agir`, effet `asyncapi:publish`, `AUCUNE`). Le payload n'est jamais recopié.
    """
    application = _application(application_id)
    charge = _document_asyncapi(document)
    if charge is None:
        return []

    noms: set[str] = set()
    manifestes: list[ManifesteOutil] = []
    for canal, identifiant, sens in _operations_asyncapi(charge):
        lecture_seule = sens in _LECTURES_ASYNCAPI
        base = f"{_slug_application(application)}.asyncapi.{_segment(identifiant) or 'operation'}"
        nom = _nom_unique(base, f"asyncapi:{canal}:{identifiant}:{sens}", noms)
        noms.add(nom)
        manifestes.append(_manifeste(
            nom=nom,
            version=version,
            description=_description_asyncapi(application, canal, identifiant, sens),
            lecture_seule=lecture_seule,
            effet=None if lecture_seule else "asyncapi:publish",
            source="asyncapi",
            tenant=tenant,
            acteur=acteur,
            perimetre=perimetre,
        ))
    return manifestes


def charger_dans(registre: RegistreCapacites, manifestes: Iterable[ManifesteOutil]) -> list[str]:
    """Enregistre des manifestes déjà générés dans un `RegistreCapacites` ; rend leurs noms."""
    enregistrer = getattr(registre, "enregistrer", None)
    if not callable(enregistrer):
        raise TypeError("registre capacitaire attendu")
    noms: list[str] = []
    for manifeste in manifestes:
        enregistrer(manifeste)
        noms.append(manifeste.nom)
    return noms
