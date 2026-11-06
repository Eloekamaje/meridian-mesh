"""Helpers partagés par les extracteurs de liens.

Aucun parseur ici : seulement la normalisation de chemins, les preuves et la
construction d'un appel HTTP. Les extracteurs spécialisés importent ce module au lieu
de recopier les mêmes règles.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlsplit

from meridian.domain.liens_composants import Appel, Preuve

_RE_PROPRIETE = re.compile(r"^\$\{([^}]+)\}$")
_RE_JNDI = re.compile(r"^(java:|jms/|jdbc/|eis/|queue/|topic/)", re.I)
_RE_SECRET = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|api[_-]?key|apikey|"
    r"access[_-]?key|private[_-]?key|client[_-]?secret)", re.I)
_CLES_SECRETES_URL = frozenset({
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "apikey", "access_key", "private_key", "client_secret",
})


def _texte(valeur, maximum=1000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def est_secret(cle: str) -> bool:
    return bool(_RE_SECRET.search(str(cle or "")))


def jndi_cible(attributes: Mapping) -> str:
    """Nom JNDI d'une injection `@Resource`/`@EJB`, ou chaîne vide si ce n'en est pas un."""
    valeur = str(
        attributes.get("lookup") or attributes.get("mappedName")
        or attributes.get("name") or "").strip().strip("\"'")
    return valeur if _RE_JNDI.match(valeur) else ""


def nom_propriete(cible: str) -> str:
    trouve = _RE_PROPRIETE.match(str(cible or "").strip())
    return trouve.group(1).strip() if trouve else str(cible or "").strip()


def sans_identifiants(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except ValueError:
        return False
    if parties.username or parties.password or "@" in parties.netloc:
        return False
    return not any(cle.strip().lower() in _CLES_SECRETES_URL
                   for cle, _ in parse_qsl(parties.query, keep_blank_values=True))


def chemin(*parties) -> str:
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


def nom_hote(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def ligne(texte: str, position: int) -> int:
    return texte.count("\n", 0, max(0, position)) + 1


def preuve(source: str, locator: str, detail: str = "", mode: str = "DECLARE",
           confidence: float = 0.85) -> Preuve:
    return Preuve(source=source, locator=locator, detail=detail, mode=mode,
                  confidence=confidence)


def appel_http(composant: str, application: str, fichier: str, numero_ligne: int,
               methode: str, cible: str, source_kind: str, environment: str,
               detail: str = "") -> Appel | None:
    cible = str(cible or "").strip()
    if not cible:
        return None
    if cible.startswith(("${", "{{")):
        cible_type, route = "PROPRIETE", ""
    elif "://" in cible:
        if not sans_identifiants(cible):
            return None
        cible_type, route = "URL", chemin(urlsplit(cible).path)
    elif cible.startswith("/"):
        cible_type, route = "CHEMIN", chemin(cible)
    else:
        cible_type, route = "SERVICE", chemin(urlsplit(cible).path)
    operation = f"{methode} {route}".strip() if route else methode
    return Appel(
        composant_id=composant, application_id=application, protocole="HTTP",
        cible=cible, cible_type=cible_type, methode=methode, chemin=route,
        operation=operation, environment=environment, source_kind=source_kind,
        preuves=(preuve(source_kind, f"{fichier}:{numero_ligne}",
                        detail or f"{methode} {route or cible}", confidence=0.9),),
    )


def arguments_annotation(attributes: Mapping, nom: str) -> dict:
    details = attributes.get("annotation_details") or {}
    valeur = details.get(nom) if isinstance(details, Mapping) else None
    return valeur if isinstance(valeur, dict) else {}


def valeur_annotation(details: Mapping, *noms) -> str:
    for nom in noms:
        valeur = details.get(nom)
        if isinstance(valeur, (list, tuple)):
            valeur = valeur[0] if valeur else ""
        if valeur not in (None, ""):
            return str(valeur).strip()
    return ""


def valeurs_annotation(details: Mapping, *noms) -> list[str]:
    resultat = []
    for nom in noms:
        valeur = details.get(nom)
        elements = valeur if isinstance(valeur, (list, tuple)) else (valeur,)
        for element in elements:
            texte = str(element or "").strip()
            if texte and texte not in resultat:
                resultat.append(texte)
    return resultat
