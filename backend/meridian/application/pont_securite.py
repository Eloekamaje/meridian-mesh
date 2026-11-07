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
    "SECRET_MARKERS",
    "SignatureInvalide",
    "assainir",
    "charger_cle",
    "cle_pont",
    "cle_sensible",
    "hash_contenu",
    "signer_evenement",
    "signature",
    "url_porte_un_secret",
    "verifier_evenement",
]

PONT_KEY_ENV = "PONT_KEY"
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


def cle_sensible(cle: Any) -> bool:
    """Vrai pour une clé qui peut porter un secret, y compris camelCase et `key_id`."""
    normalisee = unquote_plus(str(cle)).strip()
    if not normalisee:
        return False
    if normalisee.lower().endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    snake = _camel_vers_snake(normalisee).replace("-", "_")
    compacte = snake.replace("_", "")
    if compacte in _CLES_SECRETES or snake in _CLES_SECRETES:
        return True
    if "key" in snake.split("_") or snake.endswith("_key") or snake.endswith("_key_id"):
        return True
    return any(marque in snake for marque in SECRET_MARKERS)


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


def _charge_signable(evenement: Mapping[str, Any]) -> dict[str, Any]:
    charge = {cle: valeur for cle, valeur in evenement.items()
              if cle not in CHAMPS_MUTABLES}
    return assainir(charge)


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
