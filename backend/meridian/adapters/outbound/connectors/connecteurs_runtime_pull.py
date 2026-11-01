"""Tirage OTLP authentifié : un export de collecteur devient un graphe d'interfaces observé.

Mêmes garde-fous que les autres lecteurs distants : HTTPS uniquement, hôte explicitement autorisé
(`JUMEAU_OTLP_HOTES` ou `hotes_autorises`), refus des adresses locales et des identifiants dans l'URL, aucune
redirection suivie (l'en-tête d'autorisation suivrait ailleurs), réponse bornée en taille et schéma OTLP vérifié.
Le jeton vit dans un secret `env:`/`vault:` résolu par `naissance.resoudre_secret` ; il n'est jamais journalisé,
recopié dans une erreur ni renvoyé. Aucun accès base : le graphe rendu est en mode ombre, à l'appelant de le
persister.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

from meridian.adapters.outbound.connectors import naissance
from meridian.adapters.outbound.connectors.connecteurs_runtime import TAILLE_MAX, depuis_otlp
from meridian.adapters.outbound.connectors.github import _SansRedirection
from meridian.adapters.outbound.connectors.naissance import HOTE_VALIDE, hote_public

VARIABLE_HOTES = "JUMEAU_OTLP_HOTES"
DELAI = 10
MAX_OCTETS = TAILLE_MAX

_ouvrir = urllib.request.build_opener(_SansRedirection).open


class ErreurTirage(ValueError):
    """Tirage OTLP refusé ; le message peut être montré, jamais une URL secrète ni un jeton."""


class HoteRefuse(ErreurTirage):
    """URL, schéma ou hôte hors de la politique de tirage."""


class SecretRefuse(ErreurTirage):
    """Secret absent, illisible ou mal formé."""


class ReponseHTTP(ErreurTirage):
    """Le collecteur a répondu autre chose qu'un export exploitable."""

    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut


class RedirectionRefusee(ReponseHTTP):
    """Une redirection n'est jamais suivie : l'en-tête d'autorisation suivrait ailleurs."""


class AccesRefuse(ReponseHTTP):
    """Le collecteur refuse le jeton (401/403)."""


class ReponseTropGrande(ErreurTirage):
    """La réponse dépasse la borne d'octets."""


class JSONInvalide(ErreurTirage):
    """La réponse n'est pas du JSON UTF-8."""


class SchemaOTLP(ErreurTirage):
    """Le JSON ne porte pas le tableau `resourceSpans`."""


class SourceInjoignable(ErreurTirage):
    """Le collecteur n'a pas répondu (réseau, délai)."""


# Alias lisibles pour les appelants qui nomment l'erreur autrement.
HoteNonAutorise = HoteRefuse
ReponseTropVolumineuse = ReponseTropGrande


def resoudre_secret(reference: Optional[str]) -> Optional[str]:
    """Indirection testable vers `naissance.resoudre_secret` ; le secret n'est jamais rendu par erreur."""
    return naissance.resoudre_secret(reference)


def _hotes(hotes_autorises: Optional[Iterable[str]] = None) -> set[str]:
    """Hôtes autorisés : variable d'environnement (liste séparée par virgules) et/ou paramètre explicite."""
    bruts: list[str] = (os.environ.get(VARIABLE_HOTES) or "").split(",")
    if isinstance(hotes_autorises, str):
        bruts.extend(hotes_autorises.split(","))
    elif hotes_autorises is not None:
        bruts.extend(str(hote) for hote in hotes_autorises)
    return {hote.strip().lower().rstrip(".") for hote in bruts if hote and hote.strip()}


def hotes_autorises(hotes_autorises: Optional[Iterable[str]] = None) -> set[str]:
    """Ensemble canonique des hôtes autorisés, pour vérifier la politique avant un tirage."""
    return _hotes(hotes_autorises)


def _nom_hote(url: Any) -> str:
    """Nom d'hôte d'une URL HTTPS publique, sans identifiants ni port exotique (sinon `HoteRefuse`)."""
    try:
        parties = urlsplit(url)
    except (AttributeError, TypeError, ValueError, UnicodeError):
        raise HoteRefuse("URL OTLP invalide") from None
    if parties.scheme.lower() != "https":
        raise HoteRefuse("URL OTLP : HTTPS requis")
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        raise HoteRefuse("URL OTLP : identifiants dans l'URL interdits")
    try:
        hote = (parties.hostname or "").strip().lower().rstrip(".")
        port = parties.port
    except ValueError:
        raise HoteRefuse("URL OTLP invalide") from None
    if not hote:
        raise HoteRefuse("URL OTLP : hôte attendu")
    if not HOTE_VALIDE.fullmatch(hote) or not hote_public(hote):
        raise HoteRefuse("URL OTLP : hôte local ou adresse IP interdit")
    if port not in (None, 443):
        raise HoteRefuse("URL OTLP : port non autorisé")
    return hote


def _hote_autorise(url: Any, hotes_autorises: Optional[Iterable[str]] = None) -> str:
    hote = _nom_hote(url)
    autorises = _hotes(hotes_autorises)
    if not autorises:
        raise HoteRefuse(f"aucun hôte OTLP autorisé ({VARIABLE_HOTES} vide)")
    if hote not in autorises:
        raise HoteRefuse("URL OTLP : hôte non autorisé")
    return hote


def _secret(secret_ref: Optional[str]) -> Optional[str]:
    """Résout `env:`/`vault:` sans jamais recopier la valeur ni le message d'origine dans l'erreur."""
    if not secret_ref:
        return None
    try:
        secret = resoudre_secret(secret_ref)
    except Exception:
        raise SecretRefuse("secret OTLP introuvable ou refusé") from None
    if not secret:
        raise SecretRefuse("secret OTLP introuvable")
    if (not isinstance(secret, str) or not secret.isascii() or not secret.isprintable()
            or any(caractere.isspace() for caractere in secret)):
        raise SecretRefuse("secret OTLP mal formé")
    return secret


def _erreur_http(erreur: urllib.error.HTTPError) -> ReponseHTTP:
    """Erreur HTTP typée, sans URL, en-tête ni jeton dans le message."""
    code = int(erreur.code)
    if 300 <= code < 400:
        return RedirectionRefusee(code, "source OTLP : redirection refusée")
    if code in (401, 403):
        return AccesRefuse(code, "source OTLP : jeton refusé")
    if code == 429:
        return ReponseHTTP(code, "source OTLP : quota atteint")
    return ReponseHTTP(code, f"source OTLP : HTTP {code}")


def tirer_otlp(url: str, secret_ref: Optional[str] = None,
               hotes_autorises: Optional[Iterable[str]] = None, timeout: float = DELAI,
               max_octets: int = MAX_OCTETS) -> dict:
    """Tire un export OTLP JSON depuis `url` (HTTPS, hôte autorisé) et rend le document décodé.

    Le secret, s'il est fourni par référence, devient `Authorization: Bearer …` ; il n'apparaît ni dans la valeur
    rendue ni dans une erreur. Une redirection, un refus du collecteur, une réponse trop grosse, un JSON invalide
    ou un document sans `resourceSpans` lèvent une `ErreurTirage` typée.
    """
    if not isinstance(max_octets, int) or isinstance(max_octets, bool) or max_octets < 0:
        raise ValueError("max_octets doit être un entier positif ou nul")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout doit être positif")
    _hote_autorise(url, hotes_autorises)
    secret = _secret(secret_ref)

    entetes = {"Accept": "application/json"}
    if secret:
        entetes["Authorization"] = f"Bearer {secret}"
    requete = urllib.request.Request(url, headers=entetes, method="GET")
    try:
        with _ouvrir(requete, timeout=timeout) as reponse:
            corps = reponse.read(max_octets + 1)
    except urllib.error.HTTPError as erreur:
        raise _erreur_http(erreur) from None
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        raise SourceInjoignable("source OTLP injoignable") from None

    if isinstance(corps, str):
        corps = corps.encode("utf-8")
    if len(corps) > max_octets:
        raise ReponseTropGrande(f"réponse OTLP trop volumineuse (maximum {max_octets} octets)")
    try:
        donnees = json.loads(corps.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise JSONInvalide("source OTLP : JSON invalide") from None
    if not isinstance(donnees, dict) or not isinstance(donnees.get("resourceSpans"), list):
        raise SchemaOTLP("source OTLP : resourceSpans attendu")
    return donnees


def depuis_url(application_id: str, url: str, secret_ref: Optional[str] = None,
               environment: str = "inconnu", source: str = "apm",
               hotes_autorises: Optional[Iterable[str]] = None, timeout: float = DELAI,
               max_octets: int = MAX_OCTETS):
    """Tire `url`, parse l'export OTLP et rend un `InterfaceGraph` observé (aucune écriture)."""
    payload = tirer_otlp(url, secret_ref=secret_ref, hotes_autorises=hotes_autorises,
                         timeout=timeout, max_octets=max_octets)
    return depuis_otlp(application_id, payload, environment, source)


def main(argv=None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="python -m meridian.adapters.outbound.connectors.connecteurs_runtime_pull",
        description="Tirer un export OTLP d'un collecteur autorisé et imprimer le graphe observé en JSON.")
    analyseur.add_argument("url")
    analyseur.add_argument("application_id")
    analyseur.add_argument("--secret-ref")
    analyseur.add_argument("--environment", default="inconnu")
    analyseur.add_argument("--source", default="apm")
    arguments = analyseur.parse_args(argv)
    try:
        graph = depuis_url(arguments.application_id, arguments.url, arguments.secret_ref,
                           arguments.environment, arguments.source)
    except (ValueError, OSError) as erreur:
        print(f"tirage impossible : {erreur}", file=sys.stderr)
        return 2
    print(json.dumps(graph.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
