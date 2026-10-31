"""Adaptateur HTTP déclaratif et borné pour les outils du Jumeau.

L'adaptateur ne suit aucune redirection, n'ajoute aucun secret, refuse les méthodes, hôtes et chemins non
autorisés et ne renvoie que le statut, le type de contenu et un corps borné. Le transport est injectable :
les tests peuvent ainsi vérifier le contrat sans ouvrir de connexion réseau.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
import math
import re
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

MAX_OCTETS = 1_000_000
MAX_TEXTE = 100_000
MAX_ENTETE = 8_192
MAX_TYPE_CONTENU = 200

STATUT_HOTE_REFUSE = "hote_refuse"
STATUT_METHODE_REFUSEE = "methode_refusee"
STATUT_CHEMIN_REFUSE = "chemin_refuse"
STATUT_OUTIL_REFUSE = "outil_refuse"
STATUT_REDIRECTION = "redirection"
STATUT_TIMEOUT = "timeout"
STATUT_TRANSPORT = "transport"
STATUT_REPONSE_INVALIDE = "reponse_invalide"
STATUT_REPONSE_TROP_VOLUMINEUSE = "reponse_trop_volumineuse"

_CODES_REDIRECTION = frozenset({301, 302, 303, 307, 308})
_METHODES_LECTURE = frozenset({"GET", "HEAD", "OPTIONS"})
_LOCALHOST = frozenset({"localhost", "127.0.0.1", "::1"})
_OPTIONS_AUTORISEES = frozenset({"params", "json", "data"})
_METHODE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_NOM_EN_TETE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_MOTS_ENTETE_SENSIBLES = frozenset({
    "auth", "authentication", "authorization", "bearer", "cookie", "credential", "credentials",
    "jwt", "key", "password", "passwd", "secret", "session", "signature", "token",
})
_ENTETES_INTERDITS = frozenset({
    "connection", "content-length", "expect", "host", "proxy-connection", "te", "trailer",
    "transfer-encoding", "upgrade",
})
_MOTIFS_VALEUR_SENSIBLE = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bbasic\s+[A-Za-z0-9+/=]{8,}", re.IGNORECASE),
    re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{8,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{8,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{12,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
)


class HTTPInvalide(ValueError):
    """La configuration de l'adaptateur ou un argument d'appel ne respecte pas le contrat."""


class HTTPRefuse(Exception):
    """Un appel est refusé par la politique HTTP avant ou après le transport, sans fuite de secret."""

    def __init__(self, statut: str, detail: str | None = None) -> None:
        self.statut = statut
        self.detail = detail
        message = statut if detail is None else f"{statut} : {detail}"
        super().__init__(message)

    @property
    def categorie(self) -> str:
        """Alias lisible de la catégorie de refus."""
        return self.statut

    @property
    def status(self) -> str:
        """Alias anglais de la catégorie de refus."""
        return self.statut


def _a_des_controles(texte: str) -> bool:
    return any(ord(caractere) < 32 or ord(caractere) == 127 for caractere in texte)


def _decoder_repetitif(texte: str, passes: int = 3) -> str:
    courant = texte
    for _ in range(passes):
        suivant = unquote(courant)
        if suivant == courant:
            break
        courant = suivant
    return courant


def _traversee(chemin: str) -> bool:
    courant = chemin
    for _ in range(3):
        if ".." in courant.replace("\\", "/").split("/"):
            return True
        suivant = unquote(courant)
        if suivant == courant:
            break
        courant = suivant
    return False


def _contient_tools_call(texte: str) -> bool:
    if not texte:
        return False
    decode = _decoder_repetitif(texte).casefold()
    if "tools/call" in decode:
        return True
    morceaux = [morceau for morceau in re.split(r"/+", decode) if morceau and morceau != "."]
    return any(gauche == "tools" and droite == "call"
               for gauche, droite in zip(morceaux, morceaux[1:]))


def _nom_entete_sensible(nom: str) -> bool:
    morceaux = [morceau for morceau in re.split(r"[^a-z0-9]+", nom.lower()) if morceau]
    return any(morceau in _MOTS_ENTETE_SENSIBLES for morceau in morceaux)


def _valeur_entete_sensible(valeur: str) -> bool:
    return any(motif.search(valeur) for motif in _MOTIFS_VALEUR_SENSIBLE)


def _valider_entetes(entetes: Mapping[str, str] | None) -> dict[str, str]:
    if entetes is None:
        return {}
    if not isinstance(entetes, Mapping):
        raise HTTPInvalide("headers : objet attendu")
    sortie: dict[str, str] = {}
    vus: set[str] = set()
    for nom, valeur in entetes.items():
        if not isinstance(nom, str) or not isinstance(valeur, str):
            raise HTTPInvalide("headers : noms et valeurs textuels attendus")
        nom = nom.strip()
        if not nom or not _NOM_EN_TETE.fullmatch(nom):
            raise HTTPInvalide("headers : nom d'en-tête invalide")
        if len(nom) > MAX_TYPE_CONTENU:
            raise HTTPInvalide("headers : nom d'en-tête trop long")
        normalise = nom.lower()
        if normalise in vus:
            raise HTTPInvalide("headers : en-tête en double")
        vus.add(normalise)
        if normalise in _ENTETES_INTERDITS or _nom_entete_sensible(nom):
            raise HTTPInvalide("headers : en-tête interdit ou porteur de secret")
        if len(valeur) > MAX_ENTETE or _a_des_controles(valeur):
            raise HTTPInvalide("headers : valeur d'en-tête invalide")
        if _valeur_entete_sensible(valeur):
            raise HTTPInvalide("headers : secret en clair refusé")
        sortie[nom] = valeur
    return sortie


def _valider_allowlist(entrees: Sequence[str] | str | None) -> tuple[str, ...]:
    if entrees is None:
        return ()
    if isinstance(entrees, str):
        entrees = (entrees,)
    try:
        valeurs = tuple(entrees)
    except TypeError as erreur:
        raise HTTPInvalide("allowlist_hosts : séquence d'hôtes attendue") from erreur
    sortie: list[str] = []
    for entree in valeurs:
        if not isinstance(entree, str):
            raise HTTPInvalide("allowlist_hosts : chaînes attendues")
        texte = entree.strip().lower()
        if not texte:
            raise HTTPInvalide("allowlist_hosts : hôte vide interdit")
        if any(caractere in texte for caractere in ":/@?#\\") and texte != "*":
            if "://" in texte or "/" in texte or "@" in texte or "?" in texte or "#" in texte:
                raise HTTPInvalide("allowlist_hosts : nom d'hôte attendu")
        if texte != "*" and not re.fullmatch(r"\*?\.[a-z0-9.-]+|[a-z0-9.-]+|\[[0-9a-f:.]+\]",
                                             texte):
            raise HTTPInvalide("allowlist_hosts : nom d'hôte invalide")
        if texte not in sortie:
            sortie.append(texte)
    return tuple(sortie)


def _hote_autorise(hote: str, allowlist: tuple[str, ...]) -> bool:
    if not allowlist:
        return True
    for motif in allowlist:
        if motif.startswith("[") and motif.endswith("]"):
            motif = motif[1:-1]
        if motif == "*" or hote == motif:
            return True
        if motif.startswith("*.") or motif.startswith("."):
            suffixe = motif[1:] if motif.startswith("*") else motif
            if hote.endswith(suffixe) and hote != suffixe.lstrip("."):
                return True
    return False


def _valider_base(base_url: str) -> tuple[Any, str, str]:
    if not isinstance(base_url, str) or not base_url or base_url != base_url.strip():
        raise HTTPInvalide("base_url : URL absolue attendue")
    if (any(caractere.isspace() for caractere in base_url) or _a_des_controles(base_url)
            or "\\" in base_url):
        raise HTTPInvalide("base_url : caractères interdits")
    try:
        analyse = urlsplit(base_url)
    except ValueError as erreur:
        raise HTTPInvalide("base_url : URL invalide") from erreur
    if analyse.scheme not in ("http", "https") or not analyse.netloc:
        raise HTTPInvalide("base_url : URL absolue http(s) attendue")
    if analyse.fragment or analyse.query:
        raise HTTPInvalide("base_url : requête et fragment interdits")
    if analyse.username is not None or analyse.password is not None or "@" in analyse.netloc:
        raise HTTPInvalide("base_url : identifiants interdits")
    try:
        hote = analyse.hostname
        analyse.port
    except ValueError as erreur:
        raise HTTPInvalide("base_url : hôte ou port invalide") from erreur
    if not hote:
        raise HTTPInvalide("base_url : hôte attendu")
    hote = hote.lower()
    if analyse.scheme == "http" and hote not in _LOCALHOST:
        raise HTTPInvalide("base_url : HTTPS requis hors localhost")
    chemin = analyse.path or ""
    if _traversee(chemin):
        raise HTTPInvalide("base_url : traversée de chemin interdite")
    if _contient_tools_call(chemin):
        raise HTTPInvalide("base_url : tools/call interdit")
    return analyse, hote, chemin


def _valider_methodes(methodes: Sequence[str] | str | None) -> tuple[str, ...]:
    if methodes is None:
        return ()
    if isinstance(methodes, str):
        methodes = (methodes,)
    try:
        valeurs = tuple(methodes)
    except TypeError as erreur:
        raise HTTPInvalide("allow_methods : séquence de méthodes attendue") from erreur
    sortie: list[str] = []
    for methode in valeurs:
        if not isinstance(methode, str):
            raise HTTPInvalide("allow_methods : chaînes attendues")
        methode = methode.strip().upper()
        if not methode or not _METHODE.fullmatch(methode):
            raise HTTPInvalide("allow_methods : méthode invalide")
        if methode not in sortie:
            sortie.append(methode)
    return tuple(sortie)


def _valider_timeout(timeout_s: float) -> float:
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise HTTPInvalide("timeout_s : nombre attendu")
    valeur = float(timeout_s)
    if not math.isfinite(valeur) or valeur <= 0:
        raise HTTPInvalide("timeout_s : valeur strictement positive attendue")
    return valeur


def _valider_chemin(chemin: str) -> tuple[str, str]:
    if not isinstance(chemin, str) or not chemin:
        raise HTTPInvalide("path : chaîne non vide attendue")
    if any(caractere.isspace() for caractere in chemin) or _a_des_controles(chemin):
        raise HTTPInvalide("path : caractères interdits")
    if "\\" in chemin or chemin.startswith("//"):
        raise HTTPRefuse(STATUT_CHEMIN_REFUSE, "chemin absolu refusé")
    try:
        analyse = urlsplit(chemin)
    except ValueError as erreur:
        raise HTTPInvalide("path : chemin invalide") from erreur
    if analyse.scheme or analyse.netloc or "#" in chemin:
        raise HTTPRefuse(STATUT_CHEMIN_REFUSE, "chemin hors de l'hôte refusé")
    if _traversee(chemin) or _traversee(analyse.path):
        raise HTTPRefuse(STATUT_CHEMIN_REFUSE, "traversée de chemin refusée")
    if _a_des_controles(_decoder_repetitif(chemin)):
        raise HTTPRefuse(STATUT_CHEMIN_REFUSE, "caractères de contrôle refusés")
    texte = analyse.path or "/"
    if not texte.startswith("/"):
        texte = "/" + texte
    if _contient_tools_call(texte) or _contient_tools_call(analyse.query):
        raise HTTPRefuse(STATUT_OUTIL_REFUSE, "tools/call interdit")
    return texte, analyse.query


def _copier_params(params: Any) -> Any:
    if isinstance(params, Mapping):
        return dict(params)
    if isinstance(params, (list, tuple)) and all(
            isinstance(element, (list, tuple)) and len(element) == 2 for element in params):
        return list(params)
    raise HTTPInvalide("params : objet ou paires clé/valeur attendus")


def _options_appel(methode: str, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    inconnues = set(kwargs) - _OPTIONS_AUTORISEES
    if inconnues:
        raise HTTPInvalide("option d'appel non autorisée")
    options: dict[str, Any] = {}
    if "params" in kwargs:
        options["params"] = _copier_params(kwargs["params"])
    if "json" in kwargs and "data" in kwargs:
        raise HTTPInvalide("json et data sont exclusifs")
    if ("json" in kwargs or "data" in kwargs) and methode in _METHODES_LECTURE:
        raise HTTPRefuse(STATUT_METHODE_REFUSEE, "corps interdit pour une méthode de lecture")
    if "json" in kwargs:
        options["json"] = kwargs["json"]
    if "data" in kwargs:
        options["data"] = kwargs["data"]
    return options


def _valeur_reponse(reponse: Any, noms: Sequence[str], defaut: Any = None) -> Any:
    if isinstance(reponse, Mapping):
        for nom in noms:
            if nom in reponse:
                return reponse[nom]
        return defaut
    for nom in noms:
        try:
            valeur = getattr(reponse, nom)
        except Exception:
            continue
        if valeur is not None:
            return valeur
    return defaut


def _entete(entetes: Any, nom: str) -> str | None:
    if not isinstance(entetes, Mapping):
        return None
    for cle, valeur in entetes.items():
        if isinstance(cle, str) and cle.lower() == nom:
            return None if valeur is None else str(valeur)
    return None


def _type_contenu(entetes: Any) -> str | None:
    valeur = _entete(entetes, "content-type")
    if valeur is None:
        return None
    propre = re.sub(r"[\r\n\x00-\x1f\x7f]", "", valeur).strip()
    return propre[:MAX_TYPE_CONTENU] or None


def _statut_reponse(reponse: Any) -> int:
    valeur = _valeur_reponse(reponse, ("status_code", "status", "code"))
    if isinstance(valeur, bool):
        raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "statut de réponse invalide")
    try:
        statut = int(valeur)
    except (TypeError, ValueError):
        raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "statut de réponse invalide") from None
    if str(statut) != str(valeur).strip() and not isinstance(valeur, int):
        raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "statut de réponse invalide")
    if not 100 <= statut <= 599:
        raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "statut de réponse invalide")
    return statut


def _contenu_reponse(reponse: Any) -> Any:
    contenu = _valeur_reponse(reponse, ("content", "body", "text"))
    if contenu is not None:
        return contenu
    methode_json = getattr(reponse, "json", None)
    if callable(methode_json):
        try:
            return methode_json()
        except Exception:
            raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "corps de réponse illisible") from None
    return ""


def _charset(type_contenu: str | None) -> str:
    if not type_contenu:
        return "utf-8"
    trouve = re.search(r"charset\s*=\s*\"?([A-Za-z0-9._-]+)", type_contenu, re.IGNORECASE)
    return trouve.group(1) if trouve else "utf-8"


def _taille_annoncee(entetes: Any) -> int | None:
    valeur = _entete(entetes, "content-length")
    if valeur is None or not valeur.strip().isdigit():
        return None
    return int(valeur.strip())


def _corps(contenu: Any, type_contenu: str | None) -> Any:
    if isinstance(contenu, (dict, list, int, float, bool)) or contenu is None:
        objet = contenu
        try:
            texte = json.dumps(objet, ensure_ascii=False)
        except (TypeError, ValueError):
            raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "corps de réponse invalide") from None
        if len(texte.encode("utf-8")) > MAX_OCTETS:
            raise HTTPRefuse(STATUT_REPONSE_TROP_VOLUMINEUSE, "réponse trop volumineuse")
        if len(texte) > MAX_TEXTE:
            return texte[:MAX_TEXTE]
        return objet
    if isinstance(contenu, str):
        texte = contenu
    elif isinstance(contenu, (bytes, bytearray, memoryview)):
        brut = bytes(contenu)
        if len(brut) > MAX_OCTETS:
            raise HTTPRefuse(STATUT_REPONSE_TROP_VOLUMINEUSE, "réponse trop volumineuse")
        try:
            texte = brut.decode(_charset(type_contenu), errors="replace")
        except LookupError:
            texte = brut.decode("utf-8", errors="replace")
    else:
        raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "corps de réponse invalide")
    if len(texte) > MAX_OCTETS:
        raise HTTPRefuse(STATUT_REPONSE_TROP_VOLUMINEUSE, "réponse trop volumineuse")
    if texte.startswith("\ufeff"):
        texte = texte[1:]
    if len(texte) > MAX_TEXTE:
        return texte[:MAX_TEXTE]
    try:
        return json.loads(texte)
    except (TypeError, ValueError):
        return texte


def _lire_reponse(reponse: Any) -> dict[str, Any]:
    statut = _statut_reponse(reponse)
    entetes = _valeur_reponse(reponse, ("headers",), {})
    annoncee = _taille_annoncee(entetes)
    if annoncee is not None and annoncee > MAX_OCTETS:
        raise HTTPRefuse(STATUT_REPONSE_TROP_VOLUMINEUSE, "réponse trop volumineuse")
    if statut in _CODES_REDIRECTION:
        raise HTTPRefuse(STATUT_REDIRECTION, "redirection refusée")
    type_contenu = _type_contenu(entetes)
    if type_contenu is None and isinstance(reponse, Mapping) and "content_type" in reponse:
        type_contenu = _type_contenu({"content-type": reponse.get("content_type")})
    contenu = _contenu_reponse(reponse)
    return {
        "status": statut,
        "content_type": type_contenu,
        "body": _corps(contenu, type_contenu),
    }


def creer_adaptateur_http(
    base_url: str,
    *,
    allowlist_hosts: Sequence[str] | str | None = (),
    allow_methods: Sequence[str] | str | None = ("GET", "HEAD"),
    timeout_s: float = 5.0,
    headers: Mapping[str, str] | None = None,
    transport: Callable[..., Any] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Construit un adaptateur d'appels HTTP déclaratifs bornés à une base et à une politique.

    L'URL de base doit être HTTPS, sauf pour localhost/127.0.0.1 en HTTP. Les identifiants dans l'URL,
    les en-têtes porteurs de secrets, les méthodes non autorisées, les chemins absolus, les traversées
    de chemin, les redirections, les réponses trop volumineuses et ``tools/call`` sont refusés. Le
    transport reçu reçoit ``method``, ``url``, ``headers``, ``timeout`` et ``allow_redirects=False``.
    """
    analyse, hote, chemin_base = _valider_base(base_url)
    allowlist = _valider_allowlist(allowlist_hosts)
    if not _hote_autorise(hote, allowlist):
        raise HTTPInvalide("base_url : hôte hors allowlist")
    methodes = _valider_methodes(allow_methods)
    timeout = _valider_timeout(timeout_s)
    entetes = _valider_entetes(headers)
    if transport is not None and not callable(transport):
        raise HTTPInvalide("transport : fonction attendue")
    prefixe = chemin_base.rstrip("/")

    def adaptateur(method: str = "GET", path: str = "/", **kwargs: Any) -> dict[str, Any]:
        """Appelle l'URL autorisée et rend ``{status, content_type, body}`` sans en-tête sensible."""
        if not isinstance(method, str):
            raise HTTPInvalide("method : chaîne attendue")
        methode = method.strip().upper()
        if not methode or not _METHODE.fullmatch(methode):
            raise HTTPInvalide("method : méthode HTTP invalide")
        if methode not in methodes:
            raise HTTPRefuse(STATUT_METHODE_REFUSEE, "méthode non autorisée")
        chemin, requete = _valider_chemin(path)
        options = _options_appel(methode, kwargs)
        url = urlunsplit((analyse.scheme, analyse.netloc, prefixe + chemin, requete, ""))
        verifiee = urlsplit(url)
        if verifiee.netloc != analyse.netloc or verifiee.hostname != hote:
            raise HTTPRefuse(STATUT_HOTE_REFUSE, "hôte hors de la base")
        options.update({
            "headers": dict(entetes),
            "timeout": timeout,
            "allow_redirects": False,
        })
        appel = transport if transport is not None else requests.request
        try:
            reponse = appel(methode, url, **options)
        except (requests.exceptions.Timeout, TimeoutError):
            raise HTTPRefuse(STATUT_TIMEOUT, "délai dépassé") from None
        except (HTTPInvalide, HTTPRefuse):
            raise
        except Exception:
            raise HTTPRefuse(STATUT_TRANSPORT, "échec du transport") from None
        try:
            return _lire_reponse(reponse)
        except (HTTPInvalide, HTTPRefuse):
            raise
        except Exception:
            raise HTTPRefuse(STATUT_REPONSE_INVALIDE, "réponse invalide") from None

    return adaptateur


__all__ = [
    "MAX_OCTETS",
    "MAX_TEXTE",
    "STATUT_HOTE_REFUSE",
    "STATUT_METHODE_REFUSEE",
    "STATUT_CHEMIN_REFUSE",
    "STATUT_OUTIL_REFUSE",
    "STATUT_REDIRECTION",
    "STATUT_TIMEOUT",
    "STATUT_TRANSPORT",
    "STATUT_REPONSE_INVALIDE",
    "STATUT_REPONSE_TROP_VOLUMINEUSE",
    "HTTPInvalide",
    "HTTPRefuse",
    "creer_adaptateur_http",
]
