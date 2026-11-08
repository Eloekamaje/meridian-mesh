"""Sécurité et assainissement partagés du pont Travail → canonique.

Ce module est pur (stdlib uniquement). Il centralise :

- la clé HMAC `PONT_KEY` et la signature des événements d'outbox ;
- le hash de contenu stable ;
- le scrubber de secrets (camelCase, `key_id`, `keyId`, URLs à credentials).

Les événements signés empêchent un écrivain Mongo de forger un objet canonique ou de changer
de tenant. Le scrubber est utilisé par le pont, la migration legacy et le dépôt canonique pour
que la politique de secrets soit unique.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import hmac
import json
import re
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlsplit

__all__ = [
    "PONT_KEY_ENV",
    "PONT_KEY_INTERNE_ENV",
    "SECRET_MARKERS",
    "SignatureInvalide",
    "assainir",
    "charger_cle",
    "charger_cle_interne",
    "cle_interne",
    "cle_pont",
    "cle_sensible",
    "hash_contenu",
    "jeton_sensible",
    "rediger_message",
    "signer_evenement",
    "signature",
    "url_porte_un_secret",
    "verifier_evenement",
]

PONT_KEY_ENV = "PONT_KEY"
PONT_KEY_INTERNE_ENV = "PONT_KEY_INTERNE"
SECRET_MARKERS = ("password", "passwd", "secret", "token", "credential", "authorization")
# Métadonnées de claim/retry : mutables sans invalider la signature du contenu.
CHAMPS_MUTABLES = frozenset({
    "signature", "etat", "tentatives", "disponible_le", "prochaine_tentative",
    "derniere_erreur", "locked_until", "lock_token", "fencing_token", "maj_le",
    "done_le", "dead_le", "resultat",
})
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password",
    "passwd", "key", "key_id", "keyid", "access_key_id", "accesskeyid",
})


class SignatureInvalide(ValueError):
    """Signature HMAC absente, invalide ou clé `PONT_KEY` indisponible."""


def _camel_vers_snake(cle: str) -> str:
    """`accessKeyId` → `access_key_id`, sans casser les clés déjà en snake_case."""
    texte = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(cle))
    texte = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", texte)
    return texte.lower()


_SEGMENTS_SECRETS_FINAUX = frozenset({
    "token", "secret", "password", "passwd", "credential", "authorization", "bearer",
    "auth", "pwd", "pass",
})
_SEGMENTS_SECRETS_INITIAUX = frozenset({"secret", "password", "passwd", "credential"})


def cle_sensible(cle: Any) -> bool:
    """Vrai pour une clé qui peut porter un secret, sans sur-rédiger `token_count`."""
    normalisee = unquote_plus(str(cle)).strip()
    if not normalisee:
        return False
    if normalisee.lower().endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    snake = _camel_vers_snake(normalisee).replace("-", "_")
    compacte = snake.replace("_", "")
    segments = [segment for segment in snake.split("_") if segment]
    if compacte in _CLES_SECRETES or snake in _CLES_SECRETES:
        return True
    if "key" in segments or "keyid" in segments or snake.endswith(("_key", "_key_id")):
        return True
    if segments and segments[-1] in _SEGMENTS_SECRETS_FINAUX:
        return True
    if (segments and segments[0] == "authorization"
            and segments[-1] not in {"status", "type", "name"}):
        return True
    return bool(segments and len(segments) > 1
                and segments[0] in _SEGMENTS_SECRETS_INITIAUX)


def url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(
        cle_sensible(cle) and valeur not in ("", "***")
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
    )


# Détection stricte des jetons bruts, distincte de la prose légitime. Elle sert à la
# fois au refus d'écriture et au masquage HTTP :
# - JWT `eyJ…` ;
# - jetons GitHub `gh?_`/`github_pat_` ;
# - clés `sk-`/`sk-proj-` longues contenant au moins un chiffre (`sk-learn-tutorial`
#   reste accepté) ;
# - jetons Slack `xox?-` ;
# - clés AWS `AKIA…` ;
# - `Bearer <jeton>` sauf les mots de prose courants (authentication, authorization…).
MOTIF_JETON_SENSIBLE = re.compile(
    r"(?i)(?:"
    r"\beyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+){0,2}"
    r"|\bgh[pousr]_[A-Za-z0-9]{10,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bsk-(?:proj-)?(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{16,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
    r"|\bAKIA[0-9A-Z]{16}"
    r")"
)

_MOTIF_BEARER = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._~+/=-]{12,})")

# Liste volontairement courte : elle couvre les mots techniques fréquents, mais la
# décision principale est morphologique (suffixe technique), pas une liste fermée.
_MOTS_PROSE_BEARER = frozenset({
    "authentication", "authorization", "token", "tokens", "scheme", "header",
    "headers", "flow", "type", "credentials", "access", "request", "response",
    "client", "server", "resource", "endpoint", "method", "framework", "library",
    "interface", "application", "service", "system", "security", "support", "usage",
    "mode", "policy", "standard", "protocol", "format",
})
_SUFFIXES_PROSE_BEARER = (
    "tion", "sion", "ment", "ity", "ance", "ence", "ing", "ed", "al", "ive",
    "ous", "able", "ible", "er", "or", "ics", "ology", "graphy", "ness", "ship",
    "hood", "ism", "ist", "ize", "ise",
)


def _bearer_est_prose(jeton: str) -> bool:
    """Un mot alphabétique minuscule à suffixe technique est de la prose, pas un jeton."""
    minuscule = jeton.lower()
    if minuscule in _MOTS_PROSE_BEARER:
        return True
    return (
        re.fullmatch(r"[a-z]+", minuscule) is not None
        and minuscule.endswith(_SUFFIXES_PROSE_BEARER)
    )


def jeton_sensible(valeur: Any) -> bool:
    """Vrai pour une chaîne contenant un jeton brut au sens de la détection stricte."""
    if not isinstance(valeur, str):
        return False
    if MOTIF_JETON_SENSIBLE.search(valeur):
        return True
    return any(
        not _bearer_est_prose(match.group(1))
        for match in _MOTIF_BEARER.finditer(valeur)
    )


_URL_EMBEDDEE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s<>'\"]+")
_PARAMETRE = re.compile(r"(?i)([?&])([^=&\s#]+)=([^&\s#]*)")


def rediger_message(valeur: Any, limite: int = 300) -> str:
    """Message borné et expurgé pour les logs best-effort.

    Les URLs à credentials ou à paramètre sensible sont retirées entières ; les
    paramètres de requête sensibles (`password`, `token`, …) sont masqués même sans
    schéma d'URL. `token_count` n'est pas un secret et reste lisible.
    """
    texte = "" if valeur is None else str(valeur).strip()
    if not texte:
        texte = type(valeur).__name__

    def _url(match: re.Match[str]) -> str:
        url = match.group(0)
        return "[redacted]" if url_porte_un_secret(url) else url

    texte = _URL_EMBEDDEE.sub(_url, texte)

    def _parametre(match: re.Match[str]) -> str:
        prefixe, cle, valeur_brute = match.groups()
        if cle_sensible(cle) and valeur_brute not in ("", "***"):
            return f"{prefixe}{cle}=[redacted]"
        return match.group(0)

    texte = _PARAMETRE.sub(_parametre, texte)
    return texte[:max(1, int(limite))]


def assainir(valeur: Any) -> Any:
    """Copie JSON stricte, sans clé sensible ni URL porteuse de secret."""
    if valeur is None or isinstance(valeur, (bool, int, str)):
        if isinstance(valeur, str) and url_porte_un_secret(valeur):
            return "[redacted]"
        return valeur
    if isinstance(valeur, float):
        if valeur != valeur or valeur in (float("inf"), float("-inf")):
            raise ValueError("nombre non fini")
        return valeur
    if isinstance(valeur, Decimal):
        if not valeur.is_finite():
            raise ValueError("Decimal non fini")
        return float(valeur)
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Enum):
        return assainir(valeur.value)
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return assainir(asdict(valeur))
    if isinstance(valeur, Mapping):
        sortie: dict[str, Any] = {}
        for cle, element in valeur.items():
            if str(cle) == "_id" or cle_sensible(cle):
                continue
            sortie[str(cle)] = assainir(element)
        return sortie
    if isinstance(valeur, (list, tuple)):
        return [assainir(element) for element in valeur]
    if isinstance(valeur, (set, frozenset)):
        elements = [assainir(element) for element in valeur]
        return sorted(elements, key=lambda element: json.dumps(
            element, ensure_ascii=False, sort_keys=True, default=str))
    if isinstance(valeur, (bytes, bytearray)):
        return valeur.decode("utf-8", errors="replace")
    return str(valeur)


def hash_contenu(valeur: Any) -> str:
    """Hash stable (JSON trié) du contenu assaini."""
    charge = assainir(valeur)
    texte = json.dumps(charge, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def charger_cle(cle: Any = None) -> str:
    """Clé HMAC explicite ou `PONT_KEY` ; refuse une clé absente/trop courte."""
    texte = str(cle or "").strip()
    if not texte:
        import os
        texte = str(os.environ.get(PONT_KEY_ENV) or "").strip()
    if len(texte) < 16:
        raise SignatureInvalide(
            f"{PONT_KEY_ENV} absent ou trop court (16 caractères minimum)")
    return texte


cle_pont = charger_cle


def charger_cle_interne(cle: Any = None) -> str:
    """Clé HMAC du producteur interne `objets.upsert`, distincte de la clé legacy."""
    texte = str(cle or "").strip()
    if not texte:
        import os
        texte = str(os.environ.get(PONT_KEY_INTERNE_ENV) or "").strip()
    if len(texte) < 16:
        raise SignatureInvalide(
            f"{PONT_KEY_INTERNE_ENV} absent ou trop court (16 caractères minimum)")
    return texte


cle_interne = charger_cle_interne


def _charge_signable(evenement: Mapping[str, Any]) -> dict[str, Any]:
    charge = dict(evenement)
    identifiant = charge.pop("_id", None)
    contenu = {cle: valeur for cle, valeur in charge.items()
               if cle not in CHAMPS_MUTABLES}
    # `assainir` supprime `_id` : on canonicalise donc explicitement l'identifiant
    # d'événement dans une enveloppe dédiée, sinon il ne serait pas authentifié.
    return {
        "id_evenement": None if identifiant is None else str(identifiant),
        "contenu": assainir(contenu),
    }


def signature(evenement: Mapping[str, Any], cle: Any = None) -> str:
    """HMAC-SHA256 hexadécimal du document d'événement, signature exclue."""
    if not isinstance(evenement, Mapping):
        raise SignatureInvalide("événement attendu pour la signature")
    secret = charger_cle(cle)
    charge = _charge_signable(evenement)
    texte = json.dumps(charge, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False)
    return hmac.new(secret.encode("utf-8"), texte.encode("utf-8"), hashlib.sha256).hexdigest()


def signer_evenement(evenement: Mapping[str, Any], cle: Any = None) -> dict[str, Any]:
    """Rend une copie signée de l'événement ; la signature couvre tout le document."""
    resultat = dict(evenement)
    resultat.pop("signature", None)
    resultat["signature"] = signature(resultat, cle)
    return resultat


def verifier_evenement(evenement: Mapping[str, Any], cle: Any = None) -> dict[str, Any]:
    """Vérifie la signature ; rend l'événement tel quel ou lève `SignatureInvalide`."""
    if not isinstance(evenement, Mapping):
        raise SignatureInvalide("événement attendu")
    fournie = str(evenement.get("signature") or "").strip()
    if not fournie:
        raise SignatureInvalide("signature absente")
    attendue = signature(evenement, cle)
    if not hmac.compare_digest(fournie, attendue):
        raise SignatureInvalide("signature invalide")
    return dict(evenement)
