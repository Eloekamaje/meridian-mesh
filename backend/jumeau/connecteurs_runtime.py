"""Connecteur runtime APM/gateway, en mode ombre : les appels observés deviennent des assertions `observed`.

Le connecteur ne fait aucun réseau, ne lit aucun secret et n'écrit rien : il transforme un export normalisé ou
OTLP JSON (APM, gateway, service mesh) en `InterfaceGraph` séparé. Le déclaré n'est jamais modifié ni promu : les assertions
produites portent toutes `mode="observed"`, et une fusion éventuelle avec le graphe déclaré reste une décision de
l'appelant, via `interfaces.merge`. Les identifiants sont calculés sur le contenu : le contrat porte l'empreinte des
observations triées, les opérations gardent une identité stable (application propriétaire, environnement, protocole,
méthode, chemin). Un chemin d'URL est réduit à son chemin, les identifiants `user:password@` et les secrets de requête
sont masqués avant toute assertion. Un export trop gros, illisible, hors schéma ou porteur d'identifiants est refusé
avec un message qui ne recopie jamais la valeur fautive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from jumeau.interfaces import Assertion, Contract, InterfaceGraph, Operation

__all__ = [
    "MAX_OBSERVATIONS", "TAILLE_MAX", "charger_observations", "depuis_fichier", "depuis_observations",
    "depuis_otlp", "depuis_texte", "lire_export", "lire_observations", "lire_otlp", "resume",
    "resume_observations",
]

TAILLE_MAX = 2_000_000
MAX_OBSERVATIONS = 50_000
CONFIANCE_HAUTE = 0.95
CONFIANCE_MOYENNE = 0.6
CONFIANCE_BASSE = 0.4
_CONFIANCE_QUALITE = {3: CONFIANCE_HAUTE, 2: 0.8, 1: CONFIANCE_MOYENNE, 0: CONFIANCE_BASSE}

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({"pwd", "pass", "auth", "apikey", "api_key", "api-key", "access_key",
                            "private_key", "key"})
_RE_TS = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?$", re.IGNORECASE)
_RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_RE_METHODE = re.compile(r"^\S{1,64}$")
_RE_USERINFO_SCHEMA = re.compile(r"(?i)https?://[^/\s@]*@")
_RE_USERINFO_SANS_SCHEMA = re.compile(r"^[^/\s@]+:[^/\s@]*@[^/\s]+")
_KINDS_OTLP = {
    "SPAN_KIND_UNSPECIFIED": 0, "SPAN_KIND_INTERNAL": 1, "SPAN_KIND_SERVER": 2,
    "SPAN_KIND_CLIENT": 3, "SPAN_KIND_PRODUCER": 4, "SPAN_KIND_CONSUMER": 5,
    "UNSPECIFIED": 0, "INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5,
}
_CLES_OTLP_SENSIBLES = (
    "http.url", "url.full", "http.target", "url.path", "http.route", "http.path",
    "http.method", "http.request.method", "rpc.method", "rpc.service", "rpc.system",
    "service.name", "service", "peer.service", "server.address", "net.peer.name",
    "gateway", "gateway.name", "apm.gateway", "http.gateway", "operation_id", "operation.id",
)


def _empreinte(*parties: Any) -> str:
    """Empreinte canonique : même contenu, même valeur, quel que soit l'ordre des clés."""
    brut = json.dumps(parties, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _id(prefixe: str, *parties: Any) -> str:
    return f"{prefixe}_{_empreinte(*parties)[:16]}"


def _canon(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _cle_sensible(cle: str) -> bool:
    normalisee = unquote_plus(cle).strip().lower()
    return (normalisee in _CLES_SECRETES or normalisee.endswith(("_key", "-key"))
            or any(marque in normalisee for marque in _MARQUEURS_SECRETS))


def _query_sans_secrets(query: str) -> str:
    morceaux = []
    for morceau in query.split("&"):
        cle, separateur, _ = morceau.partition("=")
        morceaux.append(f"{cle}{separateur}***" if separateur and _cle_sensible(cle) else morceau)
    return _RE_USERINFO_SCHEMA.sub(lambda m: m.group(0).split("://", 1)[0] + "://", "&".join(morceaux))


def _contient_userinfo(texte: str) -> bool:
    """Vrai si la valeur porte des identifiants `user:password@`, avec ou sans schéma."""
    if not isinstance(texte, str) or not texte:
        return False
    if _RE_USERINFO_SCHEMA.search(texte) or _RE_USERINFO_SANS_SCHEMA.match(texte):
        return True
    try:
        parties = urlsplit(texte)
    except (ValueError, UnicodeError):
        return False
    return parties.username is not None or parties.password is not None or "@" in parties.netloc


def _secret_de_requete(texte: str) -> bool:
    """Vrai si une clé de requête sensible porte une valeur non déjà masquée."""
    if not isinstance(texte, str) or "?" not in texte:
        return False
    try:
        query = urlsplit(texte).query
    except (ValueError, UnicodeError):
        return False
    if not query:
        return False
    try:
        paires = parse_qsl(query, keep_blank_values=True)
    except ValueError:
        return False
    return any(_cle_sensible(cle) and valeur not in ("", "***") for cle, valeur in paires)


def _chemin_propre(brut: str) -> Optional[str]:
    """Réduit une URL ou un chemin à un chemin absolu, sans identifiants et sans secret de requête."""
    texte = brut.strip()
    if not texte:
        return None
    if len(texte) > 4096:
        texte = texte[:4096]
    if "://" in texte or texte.startswith("//"):
        try:
            parties = urlsplit(texte)
        except (ValueError, UnicodeError):
            return None
        chemin, query = parties.path or "/", parties.query
    elif _RE_USERINFO_SANS_SCHEMA.match(texte):
        reste = texte.split("@", 1)[1]
        _, _, apres_hote = reste.partition("/")
        chemin, _, query = apres_hote.partition("?")
        chemin = f"/{chemin}" if chemin else "/"
    else:
        sans_fragment = texte.split("#", 1)[0]
        chemin, _, query = sans_fragment.partition("?")
    chemin = _RE_CONTROLE.sub("", chemin).strip() or "/"
    if not chemin.startswith("/"):
        chemin = f"/{chemin}"
    chemin = chemin[:2048]
    query = _query_sans_secrets(query)
    return f"{chemin}?{query}" if query else chemin


def _champ_texte(valeur: Any, nom: str, obligatoire: bool = False,
                 max_len: int = 256) -> tuple[Optional[str], Optional[str]]:
    if valeur is None:
        return (None, f"{nom} manquant") if obligatoire else (None, None)
    if not isinstance(valeur, str):
        return None, f"{nom} : chaîne attendue"
    texte = valeur.strip()
    if not texte:
        return (None, f"{nom} vide") if obligatoire else (None, None)
    if len(texte) > max_len:
        return None, f"{nom} trop long"
    if _RE_CONTROLE.search(texte):
        return None, f"{nom} contient un caractère de contrôle"
    return texte, None


def _champ_app(valeur: Any, nom: str) -> tuple[Optional[str], Optional[str]]:
    texte, erreur = _champ_texte(valeur, nom, max_len=256)
    if erreur:
        return None, erreur
    if texte is None:
        return None, None
    if "://" in texte or _contient_userinfo(texte):
        return None, f"{nom} invalide"
    return texte, None


def _identifiant(valeur: Any, nom: str, max_len: int = 256) -> tuple[Optional[str], Optional[str]]:
    """Identifiant lisible, jamais porteur d'un secret : une valeur douteuse est retirée, pas recopiée."""
    texte, erreur = _champ_texte(valeur, nom, max_len=max_len)
    if erreur:
        return None, erreur
    if texte is None:
        return None, None
    if _contient_userinfo(texte) or _secret_de_requete(texte):
        return None, None
    return texte, None


def _champ_statut(valeur: Any) -> tuple[Optional[int], Optional[str]]:
    if valeur is None:
        return None, None
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return None, "status : entier attendu"
    if valeur < 0 or valeur > 599:
        return None, "status : hors bornes (0 à 599)"
    return valeur, None


def _champ_duree(valeur: Any) -> tuple[Optional[float], Optional[str]]:
    if valeur is None:
        return None, None
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None, "duration_ms : nombre attendu"
    if not math.isfinite(float(valeur)) or valeur < 0:
        return None, "duration_ms : valeur positive finie attendue"
    return valeur, None


def _champ_protocole(valeur: Any) -> tuple[Optional[str], Optional[str]]:
    texte, erreur = _champ_texte(valeur, "protocol", max_len=32)
    if erreur:
        return None, erreur
    if texte is None:
        return "rest", None
    texte = texte.lower()
    return {"http": "rest", "https": "rest"}.get(texte, texte), None


def _valeur_otlp(valeur: Any) -> Any:
    """Décode une valeur d'attribut OTLP JSON (stringValue, intValue, arrayValue, etc.)."""
    if not isinstance(valeur, dict):
        return valeur
    if "stringValue" in valeur:
        brut = valeur["stringValue"]
        return brut if isinstance(brut, str) else None
    if "intValue" in valeur:
        return _entier_brut(valeur["intValue"])
    if "doubleValue" in valeur:
        brut = valeur["doubleValue"]
        if isinstance(brut, bool):
            return None
        if isinstance(brut, (int, float)):
            return float(brut)
        if isinstance(brut, str):
            try:
                return float(brut.strip())
            except ValueError:
                return None
        return None
    if "boolValue" in valeur:
        brut = valeur["boolValue"]
        return brut if isinstance(brut, bool) else None
    if "arrayValue" in valeur:
        brut = valeur["arrayValue"]
        if isinstance(brut, dict):
            brut = brut.get("values", [])
        return [_valeur_otlp(item) for item in brut] if isinstance(brut, list) else None
    if "kvlistValue" in valeur:
        brut = valeur["kvlistValue"]
        if isinstance(brut, dict):
            brut = brut.get("values", [])
        return _attributs_otlp(brut)
    return None


def _attributs_otlp(liste: Any) -> dict:
    """Convertit une liste OTLP `{key, value}` (ou une table simple) en dictionnaire."""
    if isinstance(liste, dict):
        return {str(cle): _valeur_otlp(valeur) for cle, valeur in liste.items()}
    resultat = {}
    if not isinstance(liste, list):
        return resultat
    for item in liste:
        if not isinstance(item, dict):
            continue
        cle = item.get("key")
        if isinstance(cle, str) and cle:
            resultat[cle] = _valeur_otlp(item.get("value"))
    return resultat


def _entier_brut(valeur: Any) -> Optional[int]:
    if isinstance(valeur, bool) or valeur is None:
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, float) and valeur.is_integer():
        return int(valeur)
    if isinstance(valeur, str):
        try:
            return int(valeur.strip(), 10)
        except ValueError:
            return None
    return None


def _entier_otlp(attributes: dict, *cles: str) -> Optional[int]:
    for cle in cles:
        entier = _entier_brut(attributes.get(cle))
        if entier is not None:
            return entier
    return None


def _texte_otlp(attributes: dict, *cles: str) -> Optional[str]:
    for cle in cles:
        valeur = attributes.get(cle)
        if isinstance(valeur, str):
            texte = valeur.strip()
            if texte:
                return texte
    return None


def _iso_depuis_ns(valeur: Any) -> Optional[str]:
    """Horodatage Unix en nanosecondes vers ISO 8601 UTC, sans passer par un flottant."""
    entier = _entier_brut(valeur)
    if entier is None or entier <= 0:
        return None
    secondes, nanos = divmod(entier, 1_000_000_000)
    try:
        base = datetime.fromtimestamp(secondes, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    rendu = base.strftime("%Y-%m-%dT%H:%M:%S")
    if nanos:
        rendu += "." + f"{nanos:09d}".rstrip("0")
    return rendu + "Z"


def _kind_otlp(span: dict) -> int:
    valeur = span.get("kind", span.get("spanKind"))
    if isinstance(valeur, bool):
        return 0
    if isinstance(valeur, int):
        return valeur if 0 <= valeur <= 5 else 0
    if isinstance(valeur, str):
        texte = valeur.strip().upper()
        if texte in _KINDS_OTLP:
            return _KINDS_OTLP[texte]
        entier = _entier_brut(texte)
        return entier if entier is not None and 0 <= entier <= 5 else 0
    return 0


def _protocole_otlp(attributes: dict) -> str:
    systeme = _texte_otlp(attributes, "rpc.system")
    if systeme:
        return "grpc" if systeme.lower() == "grpc" else systeme.lower()
    if "rpc.method" in attributes or "rpc.service" in attributes:
        return "grpc"
    return "rest"


def _duree_otlp(span: dict, attributes: dict) -> Optional[float]:
    debut = _entier_brut(span.get("startTimeUnixNano") or span.get("start_time_unix_nano"))
    fin = _entier_brut(span.get("endTimeUnixNano") or span.get("end_time_unix_nano"))
    if debut is not None and fin is not None and fin >= debut:
        return (fin - debut) / 1_000_000.0
    for cle in ("duration_ms", "duration"):
        valeur = attributes.get(cle)
        if isinstance(valeur, bool) or valeur is None:
            continue
        if isinstance(valeur, (int, float)):
            nombre = float(valeur)
        elif isinstance(valeur, str):
            try:
                nombre = float(valeur.strip())
            except ValueError:
                continue
        else:
            continue
        if math.isfinite(nombre) and nombre >= 0:
            return nombre
    return None


def _secret_otlp(attributes: dict, nom_span: Any) -> bool:
    for cle in _CLES_OTLP_SENSIBLES:
        valeur = attributes.get(cle)
        if isinstance(valeur, str) and (_contient_userinfo(valeur) or _secret_de_requete(valeur)):
            return True
    return isinstance(nom_span, str) and (_contient_userinfo(nom_span) or _secret_de_requete(nom_span))


def _observation_otlp(span: dict, attributes: dict, index: int,
                      strict: bool) -> tuple[Optional[dict], list[str]]:
    """Observation normalisée issue d'un span OTLP, ou diagnostics sans recopier les valeurs."""
    if strict and _secret_otlp(attributes, span.get("name")):
        raise ValueError(f"OTLP span {index} : identifiants ou secret dans un attribut")

    diagnostics = []
    ts = _iso_depuis_ns(span.get("startTimeUnixNano") or span.get("start_time_unix_nano"))
    if ts is None:
        return None, [f"OTLP span {index} : startTimeUnixNano manquant ou invalide"]

    methode_http = _texte_otlp(attributes, "http.request.method", "http.method")
    methode_rpc = _texte_otlp(attributes, "rpc.method")
    if methode_http and (_contient_userinfo(methode_http) or _secret_de_requete(methode_http)):
        methode_http = None
    if methode_rpc and (_contient_userinfo(methode_rpc) or _secret_de_requete(methode_rpc)):
        methode_rpc = None
    if methode_http:
        methode = methode_http
    elif methode_rpc:
        methode = methode_rpc.rsplit("/", 1)[-1] or methode_rpc
    else:
        return None, [f"OTLP span {index} : méthode manquante"]

    chemin = _texte_otlp(attributes, "http.route", "http.target", "url.path", "http.url", "url.full",
                         "http.path")
    if chemin is None and methode_rpc:
        service_rpc = (_texte_otlp(attributes, "rpc.service") or "").strip("/")
        if _contient_userinfo(service_rpc) or _secret_de_requete(service_rpc):
            service_rpc = ""
        methode_complete = methode_rpc.lstrip("/")
        if "/" in methode_complete:
            chemin = f"/{methode_complete}"
        elif service_rpc:
            chemin = f"/{service_rpc}/{methode_complete}"
        else:
            chemin = f"/{methode_complete}"
    if chemin is None:
        return None, [f"OTLP span {index} : chemin manquant"]

    service = _texte_otlp(attributes, "service.name", "service")
    peer = _texte_otlp(attributes, "peer.service")
    adresse_serveur = _texte_otlp(attributes, "server.address")
    nom_pair = _texte_otlp(attributes, "net.peer.name")
    kind = _kind_otlp(span)
    caller: Optional[str] = None
    callee: Optional[str] = None
    if kind == 2:
        callee = service
        caller = peer or nom_pair
        if callee is None:
            diagnostics.append(f"OTLP span {index} : callee indéterminé (service.name absent)")
    elif kind == 3 or kind == 4:
        caller = service
        callee = peer or adresse_serveur or nom_pair
        if caller is None:
            diagnostics.append(f"OTLP span {index} : caller indéterminé (service.name absent)")
    elif kind == 5:
        callee = service
        caller = peer or nom_pair
        if callee is None:
            diagnostics.append(f"OTLP span {index} : callee indéterminé (service.name absent)")
    elif service:
        caller = service
        callee = peer or adresse_serveur or nom_pair
        if callee:
            diagnostics.append(f"OTLP span {index} : sens caller/callee indéterminé (kind absent)")
        else:
            diagnostics.append(f"OTLP span {index} : callee indéterminé (kind absent)")
    else:
        callee = peer or adresse_serveur or nom_pair
        if callee:
            diagnostics.append(f"OTLP span {index} : caller indéterminé (kind absent)")
    if caller is None and callee is None:
        diagnostics.append(f"OTLP span {index} : caller et callee indéterminés")
        return None, diagnostics

    statut = _entier_otlp(attributes, "http.status_code", "http.response.status_code")
    if statut is None:
        statut_grpc = _entier_otlp(attributes, "rpc.grpc.status_code")
        if statut_grpc is not None:
            statut = 200 if statut_grpc == 0 else 500
    if statut is not None and not 0 <= statut <= 599:
        diagnostics.append(f"OTLP span {index} : status hors bornes ignoré")
        statut = None

    trace = span.get("traceId") or span.get("trace_id")
    if not isinstance(trace, str) or not trace.strip():
        trace = None
    gateway = _texte_otlp(attributes, "gateway.name", "gateway", "apm.gateway", "http.gateway")
    operation_id = _texte_otlp(attributes, "operation_id", "operation.id")
    protocole = _protocole_otlp(attributes)
    if _contient_userinfo(protocole) or _secret_de_requete(protocole):
        protocole = "rest"

    brute = {
        "ts": ts, "caller": caller, "callee": callee, "protocol": protocole,
        "method": methode, "path": chemin, "operation_id": operation_id, "status": statut,
        "duration_ms": _duree_otlp(span, attributes), "trace_id": trace, "gateway": gateway,
    }
    normalisee, erreur = _normaliser(brute, index)
    if erreur:
        diagnostics.append(erreur.replace(f"observation {index}", f"OTLP span {index}", 1))
        return None, diagnostics
    return normalisee, diagnostics


def _normaliser(observation: Any, index: int) -> tuple[Optional[dict], Optional[str]]:
    """Observation normalisée, ou le diagnostic qui explique pourquoi elle est ignorée (sans sa valeur)."""
    if not isinstance(observation, dict):
        return None, f"observation {index} : objet attendu"

    ts, erreur = _champ_texte(observation.get("ts"), "ts", obligatoire=True, max_len=64)
    if erreur:
        return None, f"observation {index} : {erreur}"
    if not _RE_TS.match(ts):
        return None, f"observation {index} : ts invalide (ISO 8601 attendu)"

    caller, erreur = _champ_app(observation.get("caller"), "caller")
    if erreur:
        return None, f"observation {index} : {erreur}"
    callee, erreur = _champ_app(observation.get("callee"), "callee")
    if erreur:
        return None, f"observation {index} : {erreur}"
    if caller is None and callee is None:
        return None, f"observation {index} : caller ou callee requis"

    protocole, erreur = _champ_protocole(observation.get("protocol"))
    if erreur:
        return None, f"observation {index} : {erreur}"

    methode, erreur = _champ_texte(observation.get("method"), "method", obligatoire=True, max_len=64)
    if erreur:
        return None, f"observation {index} : {erreur}"
    if not _RE_METHODE.match(methode):
        return None, f"observation {index} : method invalide"
    methode = methode.upper()

    chemin_brut = observation.get("path")
    if not isinstance(chemin_brut, str):
        return None, f"observation {index} : path : chaîne attendue"
    chemin = _chemin_propre(chemin_brut)
    if chemin is None:
        return None, f"observation {index} : path invalide"

    operation_id, erreur = _identifiant(observation.get("operation_id"), "operation_id")
    if erreur:
        return None, f"observation {index} : {erreur}"
    statut, erreur = _champ_statut(observation.get("status"))
    if erreur:
        return None, f"observation {index} : {erreur}"
    duree, erreur = _champ_duree(observation.get("duration_ms"))
    if erreur:
        return None, f"observation {index} : {erreur}"
    trace, erreur = _identifiant(observation.get("trace_id"), "trace_id")
    if erreur:
        return None, f"observation {index} : {erreur}"
    gateway, erreur = _identifiant(observation.get("gateway"), "gateway")
    if erreur:
        return None, f"observation {index} : {erreur}"

    return {
        "ts": ts, "caller": caller, "callee": callee, "protocol": protocole, "method": methode,
        "path": chemin, "operation_id": operation_id, "status": statut, "duration_ms": duree,
        "trace_id": trace, "gateway": gateway,
    }, None


def _concerne(observation: dict, application_id: str) -> bool:
    return observation.get("caller") == application_id or observation.get("callee") == application_id


def _collecter(observations: Any, application_id: Optional[str]) -> tuple[list[dict], list[str]]:
    """Observations normalisées, dédupliquées et triées ; les invalides laissent un diagnostic sans valeur."""
    if observations is None:
        return [], []
    if isinstance(observations, (str, bytes, os.PathLike)):
        observations = lire_export(observations)
    elif isinstance(observations, dict):
        observations = observations.get("observations", observations)
    if isinstance(observations, dict):
        observations = [observations]
    try:
        brutes = list(observations)
    except TypeError:
        raise ValueError("observations : liste attendue") from None

    valides, diagnostics = [], []
    for index, brute in enumerate(brutes, 1):
        normalisee, erreur = _normaliser(brute, index)
        if erreur:
            diagnostics.append(erreur)
            continue
        if application_id is not None and not _concerne(normalisee, application_id):
            continue
        valides.append(normalisee)

    vus, sortie = set(), []
    for observation in sorted(valides, key=_canon):
        marque = _canon(observation)
        if marque not in vus:
            vus.add(marque)
            sortie.append(observation)
    return sortie, diagnostics


def _libelle(valeur: Any, defaut: str) -> str:
    if valeur is None:
        return defaut
    texte = _RE_CONTROLE.sub("", str(valeur)).strip()
    if not texte:
        return defaut
    if _contient_userinfo(texte) or _secret_de_requete(texte):
        return defaut
    return texte[:128]


def _application(valeur: Any) -> str:
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError("application_id requis")
    texte = valeur.strip()
    if len(texte) > 256 or _RE_CONTROLE.search(texte) or "://" in texte or _contient_userinfo(texte):
        raise ValueError("application_id invalide")
    return texte


def _locator(source: str, environment: str) -> str:
    return f"{source}:{environment}"


def _confiance(observation: dict) -> float:
    qualite = sum(1 for champ in ("trace_id", "status", "duration_ms") if observation.get(champ) is not None)
    return _CONFIANCE_QUALITE[qualite]


def _evidence(observation: dict) -> str:
    """Preuve lisible et canonique : trace, gateway et qualité de la mesure, jamais un secret."""
    meta = {champ: observation.get(champ) for champ in
            ("caller", "callee", "protocol", "method", "path", "operation_id", "status", "duration_ms",
             "trace_id", "gateway") if observation.get(champ) is not None}
    return json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _operation(contrat: Contract, proprietaire: str, observation: dict, environment: str) -> Operation:
    methode, chemin = observation["method"], observation["path"]
    nom = observation.get("operation_id") or f"{methode} {chemin}"
    return Operation(
        id=_id("op", "runtime", proprietaire or "", environment, observation["protocol"], methode, chemin),
        contract_id=contrat.id, protocol=observation["protocol"], method=methode, path=chemin, name=nom,
        version=None, environment=environment)


def _cle_assertion(a: Assertion) -> tuple:
    return (a.subject, a.predicate, a.object, a.mode, a.source, a.locator, a.environment, a.confidence,
            a.evidence, a.observed_at, a.valid_from)


def _uniques(objets: Iterable[Any], cle) -> list:
    vus, sortie = set(), []
    for objet in objets:
        marque = cle(objet)
        if marque not in vus:
            vus.add(marque)
            sortie.append(objet)
    return sortie


def _dedupliquer(graph: InterfaceGraph) -> InterfaceGraph:
    graph.contracts = _uniques(graph.contracts, lambda c: c.id)
    graph.operations = _uniques(graph.operations, lambda o: o.id)
    graph.assertions = _uniques(graph.assertions, _cle_assertion)
    return graph


def depuis_observations(application_id: str, observations: Any, environment: str = "inconnu",
                        source: str = "apm") -> InterfaceGraph:
    """Transforme des observations APM/gateway en un graphe `observed`, en mode ombre et sans écraser le déclaré.

    `caller == application_id` produit une assertion `CONSOMME` vers `"callee : METHOD path"` ; `callee ==
    application_id` produit une assertion `EXPOSE` de `"METHOD path"`. Un appel entre deux autres applications est
    ignoré. Le contrat runtime porte l'empreinte des observations normalisées, dédupliquées et triées ; les
    opérations ont une identité stable et le graphe rendu est neuf : aucune assertion `declared` n'est créée,
    promue ou modifiée.
    """
    application = _application(application_id)
    environnement = _libelle(environment, "inconnu")
    origine = _libelle(source, "apm")
    valides, diagnostics = _collecter(observations, application)
    digest = _empreinte(valides)
    contrat = Contract(
        id=_id("ctr", "runtime", application, environnement, digest), format="runtime", version=None,
        digest=digest, locator=_locator(origine, environnement), application_id=application,
        environment=environnement)
    graph = InterfaceGraph(contracts=[contrat], diagnostics=diagnostics, partial=bool(diagnostics))
    if not valides:
        if not diagnostics:
            graph.diagnostics.append("aucune observation ne concerne cette application")
        graph.partial = True
        return graph

    for observation in valides:
        caller, callee = observation.get("caller"), observation.get("callee")
        confiance = _confiance(observation)
        preuve = _evidence(observation)
        locator = _locator(origine, environnement)
        if caller == application:
            reference = (f"{callee} : {observation['method']} {observation['path']}"
                         if callee else f"{observation['method']} {observation['path']}")
            graph.operations.append(_operation(contrat, callee or "", observation, environnement))
            graph.assertions.append(Assertion(
                subject=application, predicate="CONSOMME", object=reference, mode="observed", source=origine,
                locator=locator, environment=environnement, confidence=confiance, evidence=preuve,
                observed_at=observation["ts"]))
        if callee == application:
            graph.operations.append(_operation(contrat, application, observation, environnement))
            graph.assertions.append(Assertion(
                subject=application, predicate="EXPOSE", object=f"{observation['method']} {observation['path']}",
                mode="observed", source=origine, locator=locator, environment=environnement,
                confidence=confiance, evidence=preuve, observed_at=observation["ts"]))
    return _dedupliquer(graph)


def depuis_otlp(application_id: str, payload: Any, environment: str = "inconnu",
                source: str = "apm") -> InterfaceGraph:
    """Convertit un export OTLP JSON (dict, fichier, texte ou octets) en graphe `observed`.

    Le sens vient de `span.kind` : un span `CLIENT` expose le `service.name` comme `caller`, un span `SERVER`
    comme `callee` ; `peer.service`, `server.address` ou `net.peer.name` fournissent l'autre côté. Sans direction
    identifiable, l'observation reste partielle et un diagnostic est ajouté, sans inventer d'application. Les
    spans sans horodatage, méthode ou chemin exploitables sont ignorés avec un compteur ; le graphe produit ne
    contient que des assertions `observed`.
    """
    application = _application(application_id)
    observations, diagnostics = _observations_otlp(
        _charge_otlp(payload, TAILLE_MAX), MAX_OBSERVATIONS, True)
    graph = depuis_observations(application, observations, environment, source)
    if diagnostics:
        graph.diagnostics = diagnostics + graph.diagnostics
        graph.partial = True
    return graph


def _lire_fichier(chemin: Path, max_octets: int) -> str:
    try:
        attributs = chemin.stat()
    except OSError:
        raise ValueError("fichier introuvable ou illisible") from None
    if not stat.S_ISREG(attributs.st_mode):
        raise ValueError("fichier spécial refusé")
    if attributs.st_size > max_octets:
        raise ValueError(f"export trop volumineux (maximum {max_octets} octets)")
    try:
        with chemin.open("rb") as flux:
            donnees = flux.read(max_octets + 1)
    except OSError:
        raise ValueError("fichier illisible") from None
    if len(donnees) > max_octets:
        raise ValueError(f"export trop volumineux (maximum {max_octets} octets)")
    if b"\x00" in donnees:
        raise ValueError("export binaire refusé")
    try:
        return donnees.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("export non UTF-8") from None


def _lire_source(source: Any, max_octets: int) -> str:
    if isinstance(source, (bytes, bytearray)):
        donnees = bytes(source)
        if len(donnees) > max_octets:
            raise ValueError(f"export trop volumineux (maximum {max_octets} octets)")
        try:
            return donnees.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("export non UTF-8") from None
    if isinstance(source, os.PathLike):
        return _lire_fichier(Path(source), max_octets)
    if isinstance(source, str):
        if source.lstrip("\ufeff \t\r\n").startswith(("{", "[")):
            if len(source.encode("utf-8")) > max_octets:
                raise ValueError(f"export trop volumineux (maximum {max_octets} octets)")
            return source
        return _lire_fichier(Path(source), max_octets)
    raise ValueError("export : chemin de fichier ou texte JSON attendu")


def _est_otlp(donnees: Any) -> bool:
    return isinstance(donnees, dict) and any(cle in donnees for cle in ("resourceSpans", "resource_spans"))


def _charge_otlp(source: Any, max_octets: int) -> dict:
    if isinstance(source, dict):
        try:
            taille = len(json.dumps(source, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            raise ValueError("OTLP : JSON invalide") from None
        if taille > max_octets:
            raise ValueError(f"export OTLP trop volumineux (maximum {max_octets} octets)")
        return source
    texte = _lire_source(source, max_octets).lstrip("\ufeff")
    if not texte.strip():
        raise ValueError("export OTLP vide")
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise ValueError(f"JSON invalide (ligne {erreur.lineno}, colonne {erreur.colno})") from None
    if not isinstance(donnees, dict):
        raise ValueError("OTLP : objet JSON attendu")
    return donnees


def _observations_otlp(donnees: Any, max_spans: int, strict: bool) -> tuple[list[dict], list[str]]:
    """Convertit un document OTLP JSON en observations normalisées, sans réseau ni valeur fautive."""
    if not isinstance(donnees, dict):
        raise ValueError("OTLP : objet JSON attendu")
    resource_spans = donnees.get("resourceSpans")
    if resource_spans is None:
        resource_spans = donnees.get("resource_spans")
    if not isinstance(resource_spans, list):
        raise ValueError("OTLP : resourceSpans attendu")

    observations: list[dict] = []
    diagnostics: list[str] = []
    vus = set()
    total = ignores = 0
    for index_rs, resource_span in enumerate(resource_spans, 1):
        if not isinstance(resource_span, dict):
            ignores += 1
            diagnostics.append(f"OTLP resourceSpans {index_rs} : objet attendu")
            continue
        ressource = resource_span.get("resource")
        attributs_ressource = (_attributs_otlp(ressource.get("attributes"))
                               if isinstance(ressource, dict) else {})
        scopes = resource_span.get("scopeSpans")
        if scopes is None:
            scopes = resource_span.get("scope_spans")
        if scopes is None:
            scopes = resource_span.get("instrumentationLibrarySpans")
        if scopes is None:
            continue
        if not isinstance(scopes, list):
            ignores += 1
            diagnostics.append(f"OTLP resourceSpans {index_rs} : scopeSpans attendu")
            continue
        for index_scope, scope in enumerate(scopes, 1):
            if not isinstance(scope, dict):
                ignores += 1
                diagnostics.append(f"OTLP scopeSpans {index_scope} : objet attendu")
                continue
            spans = scope.get("spans")
            if spans is None:
                continue
            if not isinstance(spans, list):
                ignores += 1
                diagnostics.append(f"OTLP scopeSpans {index_scope} : spans attendu")
                continue
            for span in spans:
                total += 1
                if total > max_spans:
                    raise ValueError(f"export OTLP trop volumineux (maximum {max_spans} spans)")
                if not isinstance(span, dict):
                    ignores += 1
                    diagnostics.append(f"OTLP span {total} : objet attendu")
                    continue
                marque = (span.get("traceId") or span.get("trace_id"),
                          span.get("spanId") or span.get("span_id"))
                if all(isinstance(partie, str) and partie for partie in marque):
                    if marque in vus:
                        continue
                    vus.add(marque)
                attributs = dict(attributs_ressource)
                attributs.update(_attributs_otlp(span.get("attributes")))
                observation, messages = _observation_otlp(span, attributs, total, strict)
                if observation is None:
                    ignores += 1
                    diagnostics.extend(messages)
                    continue
                diagnostics.extend(messages)
                observations.append(observation)
    if ignores:
        diagnostics.insert(0, f"OTLP : {ignores} span(s) ignoré(s) sur {total}")
    return observations, diagnostics


def _valider_observation(observation: Any, index: int) -> None:
    _, erreur = _normaliser(observation, index)
    if erreur:
        raise ValueError(erreur)
    for champ in ("path", "gateway", "trace_id", "operation_id", "caller", "callee"):
        valeur = observation.get(champ)
        if isinstance(valeur, str) and (_contient_userinfo(valeur) or _secret_de_requete(valeur)):
            raise ValueError(f"observation {index} : {champ} contient des identifiants ou un secret")


def lire_export(source: Any, max_octets: int = TAILLE_MAX, max_observations: int = MAX_OBSERVATIONS,
                strict: bool = True, format: str = "auto") -> list[dict]:
    """Lit un export JSON (fichier, texte ou octets) sans réseau, avec schéma et taille bornés.

    `format="auto"` reconnaît un export OTLP (`resourceSpans`) et le convertit en observations normalisées ;
    `"otlp"` l'impose, `"normalise"` lit le schéma historique. La racine normalisée est une liste d'observations,
    ou un objet qui les porte sous `observations`. Les erreurs ne recopient jamais le document ; avec `strict`,
    toute URL porteuse d'identifiants ou de secret de requête est refusée. `strict=False` laisse la
    transformation masquer ces valeurs.
    """
    if max_octets < 0 or max_observations < 0:
        raise ValueError("les limites doivent être positives ou nulles")
    if format not in ("auto", "otlp", "normalise"):
        raise ValueError("format : auto, otlp ou normalise attendu")
    if isinstance(source, dict):
        donnees = source
    else:
        texte = _lire_source(source, max_octets).lstrip("\ufeff")
        if not texte.strip():
            raise ValueError("export vide")
        try:
            donnees = json.loads(texte)
        except json.JSONDecodeError as erreur:
            raise ValueError(f"JSON invalide (ligne {erreur.lineno}, colonne {erreur.colno})") from None
    if format == "otlp" or (format == "auto" and _est_otlp(donnees)):
        if isinstance(source, dict):
            donnees = _charge_otlp(source, max_octets)
        observations, _ = _observations_otlp(donnees, max_observations, strict)
        return observations
    if isinstance(donnees, dict) and "observations" in donnees:
        donnees = donnees["observations"]
    if not isinstance(donnees, list):
        raise ValueError("export : liste d'observations attendue")
    if len(donnees) > max_observations:
        raise ValueError(f"export trop volumineux (maximum {max_observations} observations)")
    for index, observation in enumerate(donnees, 1):
        if strict:
            _valider_observation(observation, index)
        else:
            _, erreur = _normaliser(observation, index)
            if erreur:
                raise ValueError(erreur)
    return [dict(observation) for observation in donnees]


def lire_otlp(source: Any, max_octets: int = TAILLE_MAX, max_spans: int = MAX_OBSERVATIONS,
              strict: bool = True) -> list[dict]:
    """Lit un export OTLP JSON (dict, fichier, texte ou octets) et rend des observations normalisées.

    Les spans incomplets sont ignorés avec un diagnostic, les doublons `(traceId, spanId)` sont écartés et les
    limites de taille et de nombre de spans s'appliquent. Avec `strict`, un identifiant ou un secret de requête
    fait refuser l'export sans recopier la valeur ; sinon le chemin est masqué avant restitution.
    """
    if max_octets < 0 or max_spans < 0:
        raise ValueError("les limites doivent être positives ou nulles")
    observations, _ = _observations_otlp(_charge_otlp(source, max_octets), max_spans, strict)
    return observations


lire_observations = lire_export
charger_observations = lire_export


def depuis_texte(texte: str, application_id: str, environment: str = "inconnu",
                 source: str = "apm") -> InterfaceGraph:
    return depuis_observations(application_id, lire_export(texte), environment, source)


def depuis_fichier(chemin: Any, application_id: str, environment: str = "inconnu",
                   source: str = "apm") -> InterfaceGraph:
    return depuis_observations(application_id, lire_export(chemin), environment, source)


def _meta_evidence(evidence: Any) -> Optional[dict]:
    if not isinstance(evidence, str):
        return None
    try:
        meta = json.loads(evidence)
    except (TypeError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _reference(objet: str) -> tuple[str, str]:
    reference = objet.rsplit(" : ", 1)[-1]
    methode, _, chemin = reference.partition(" ")
    return methode, chemin


def _protocole_operation(graph: InterfaceGraph, objet: str) -> Optional[str]:
    methode, chemin = _reference(objet)
    for operation in graph.operations:
        if operation.method == methode and operation.path == chemin:
            return operation.protocol
    return graph.operations[0].protocol if len({o.protocol for o in graph.operations}) == 1 else None


def _compteurs(appels: int, erreurs: int, protocoles: dict, appelants: dict, appeles: dict) -> dict:
    return {
        "appels": appels, "erreurs": erreurs,
        "protocoles": dict(sorted(protocoles.items())),
        "applications": {"caller": dict(sorted(appelants.items())), "callee": dict(sorted(appeles.items()))},
    }


def resume(graph: InterfaceGraph) -> dict:
    """Compte les appels observés d'un graphe : protocoles, erreurs `status >= 400`, applications caller/callee.

    Les assertions d'un même appel (par exemple un auto-appel qui produit `CONSOMME` et `EXPOSE`) ne sont
    comptées qu'une fois. Les assertions non observées sont ignorées : le déclaré ne gonfle pas les compteurs.
    """
    if not isinstance(graph, InterfaceGraph):
        return resume_observations(graph)
    appels = erreurs = 0
    protocoles: dict[str, int] = {}
    appelants: dict[str, int] = {}
    appeles: dict[str, int] = {}
    vus = set()
    for assertion in graph.assertions:
        if assertion.mode != "observed":
            continue
        meta = _meta_evidence(assertion.evidence)
        marque = (assertion.observed_at, assertion.source, assertion.locator, assertion.evidence)
        if marque in vus:
            continue
        vus.add(marque)
        appels += 1
        protocole = (meta or {}).get("protocol") or _protocole_operation(graph, assertion.object)
        if protocole:
            protocoles[protocole] = protocoles.get(protocole, 0) + 1
        statut = (meta or {}).get("status")
        if isinstance(statut, int) and not isinstance(statut, bool) and statut >= 400:
            erreurs += 1
        caller = (meta or {}).get("caller")
        callee = (meta or {}).get("callee")
        if not caller and assertion.predicate == "CONSOMME":
            caller = assertion.subject
        if not callee and assertion.predicate == "EXPOSE":
            callee = assertion.subject
        if not callee and assertion.predicate == "CONSOMME" and " : " in assertion.object:
            callee = assertion.object.split(" : ", 1)[0] or None
        if caller:
            appelants[caller] = appelants.get(caller, 0) + 1
        if callee:
            appeles[callee] = appeles.get(callee, 0) + 1
    return _compteurs(appels, erreurs, protocoles, appelants, appeles)


def resume_observations(observations: Any, application_id: Optional[str] = None) -> dict:
    """Compteurs calculés directement sur des observations brutes (ou sur un graphe déjà construit)."""
    if isinstance(observations, InterfaceGraph):
        return resume(observations)
    application = _application(application_id) if application_id is not None else None
    valides, _ = _collecter(observations, application)
    appels = erreurs = 0
    protocoles: dict[str, int] = {}
    appelants: dict[str, int] = {}
    appeles: dict[str, int] = {}
    for observation in valides:
        appels += 1
        protocoles[observation["protocol"]] = protocoles.get(observation["protocol"], 0) + 1
        if observation.get("status") is not None and observation["status"] >= 400:
            erreurs += 1
        caller, callee = observation.get("caller"), observation.get("callee")
        if caller:
            appelants[caller] = appelants.get(caller, 0) + 1
        if callee:
            appeles[callee] = appeles.get(callee, 0) + 1
    return _compteurs(appels, erreurs, protocoles, appelants, appeles)


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m jumeau.connecteurs_runtime",
        description="Lire un export APM/gateway normalisé et imprimer le graphe runtime observé en JSON.")
    analyseur.add_argument("fichier")
    analyseur.add_argument("application_id")
    analyseur.add_argument("--environment", default="inconnu")
    analyseur.add_argument("--source", default="apm")
    analyseur.add_argument("--format", choices=("auto", "otlp", "normalise"), default="auto")
    analyseur.add_argument("--max-octets", type=int, default=TAILLE_MAX)
    analyseur.add_argument("--max-observations", type=int, default=MAX_OBSERVATIONS)
    arguments = analyseur.parse_args(argv)
    try:
        observations = lire_export(arguments.fichier, max_octets=arguments.max_octets,
                                   max_observations=arguments.max_observations,
                                   format=arguments.format)
        graph = depuis_observations(arguments.application_id, observations, arguments.environment, arguments.source)
    except (ValueError, OSError) as erreur:
        print(f"lecture impossible : {erreur}", file=sys.stderr)
        return 2
    print(json.dumps(graph.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
