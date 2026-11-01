"""Import d'identité de commande depuis une CMDB ou un manifeste JSON/CSV.

Aucune source n'est interrogée ici : le contenu fourni est une donnée. Le parseur ne conserve que
l'identité de l'application et une liste de sources normalisées ; les secrets restent des références.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Mapping

APPLICATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


class ImportInvalide(ValueError):
    """Contenu d'import absent, illisible ou incomplet."""


def _texte(valeur: Any) -> str:
    return str(valeur or "").strip()


def _premier(objet: Mapping, cles: tuple[str, ...]) -> str:
    for cle in cles:
        valeur = _texte(objet.get(cle))
        if valeur:
            return valeur
    return ""


def _lignes(contenu: Any) -> list[dict]:
    if isinstance(contenu, list):
        return [dict(x) for x in contenu if isinstance(x, Mapping)]
    if isinstance(contenu, Mapping):
        jumeau = contenu.get("jumeau")
        if isinstance(jumeau, Mapping):
            return [{**dict(jumeau), "sources": contenu.get("sources") or []}]
        return [dict(contenu)]
    if not isinstance(contenu, str) or not contenu.strip():
        raise ImportInvalide("contenu d'import requis")
    texte = contenu.strip()
    try:
        charge = json.loads(texte)
    except ValueError:
        charge = None
    if isinstance(charge, list):
        return [dict(x) for x in charge if isinstance(x, Mapping)]
    if isinstance(charge, Mapping):
        jumeau = charge.get("jumeau")
        if isinstance(jumeau, Mapping):
            return [{**dict(jumeau), "sources": charge.get("sources") or []}]
        return [dict(charge)]
    lecteur = csv.DictReader(io.StringIO(texte))
    lignes = [dict(ligne) for ligne in lecteur]
    if not lignes:
        raise ImportInvalide("aucune ligne d'import")
    return lignes


CHAMPS_SECRETS = {"secret", "token", "jeton", "password", "passwd", "mot_de_passe",
                  "api_key", "apikey", "authorization", "bearer"}


def _config_sure(valeur: Any) -> Any:
    """Un import ne transporte que des références : aucune valeur secrète n'est reprise."""
    if isinstance(valeur, Mapping):
        return {cle: _config_sure(v) for cle, v in valeur.items()
                if str(cle).strip().lower() not in CHAMPS_SECRETS}
    if isinstance(valeur, list):
        return [_config_sure(v) for v in valeur]
    return valeur


def _source(source: Mapping) -> dict:
    connecteur = _texte(source.get("connecteur") or source.get("connector"))
    if not connecteur:
        raise ImportInvalide("source sans connecteur")
    config = source.get("config") if isinstance(source.get("config"), Mapping) else {}
    return {
        "connecteur": connecteur,
        "nom": _texte(source.get("nom")) or connecteur,
        "environnement": _texte(source.get("environnement")) or "production",
        "perimetre": _texte(source.get("perimetre")),
        "proprietaire": _texte(source.get("proprietaire")),
        "config": _config_sure(dict(config)),
    }


def _cle_source(source: Mapping) -> tuple[str, str]:
    return (_texte(source.get("connecteur")).lower(), _texte(source.get("nom")).lower())


def preparer(contenu: Any, mode: str = "cmdb", existantes=(), connus=None) -> dict:
    """Prépare l'import d'une commande : une identité, sources nouvelles et doublons séparés."""
    entrees = analyser(contenu, mode)
    if len(entrees) != 1:
        raise ImportInvalide(
            "Une commande ne peut importer qu'une seule identité ; découpez l'export par application."
        )
    entree = entrees[0]
    if connus is not None:
        inconnus = sorted({s["connecteur"] for s in entree["sources"] if s["connecteur"] not in connus})
        if inconnus:
            raise ImportInvalide("connecteur(s) non branché(s) ou inconnu(s) : " + ", ".join(inconnus))
    deja = {(_texte(connecteur).lower(), _texte(nom).lower()) for connecteur, nom in existantes}
    nouvelles, ignorees = [], []
    for source in entree["sources"]:
        cle = _cle_source(source)
        if cle in deja:
            ignorees.append(source)
        else:
            nouvelles.append(source)
            deja.add(cle)
    return {
        "identite": {cle: entree[cle] for cle in ("application_id", "nom", "proprietaire")},
        "nouvelles": nouvelles,
        "ignorees": ignorees,
    }


def analyser(contenu: Any, mode: str = "cmdb") -> list[dict]:
    """Rend des entrées normalisées : application_id, nom, proprietaire et sources."""
    if mode not in {"cmdb", "manifeste", "fichier", "inventaire"}:
        raise ImportInvalide(f"mode d'import inconnu : {mode}")
    entrees = []
    for ligne in _lignes(contenu):
        application_id = _premier(ligne, ("application_id", "applicationId", "app_id", "app", "id"))
        if not application_id:
            raise ImportInvalide("application_id requis")
        application_id = application_id.strip().lower()
        if not APPLICATION_ID.fullmatch(application_id):
            raise ImportInvalide(f"application_id invalide : {application_id}")
        nom = _premier(ligne, ("nom", "name", "libelle", "label")) or application_id
        proprietaire = _premier(ligne, ("proprietaire", "propriétaire", "owner", "responsable"))
        if not proprietaire:
            raise ImportInvalide(f"propriétaire requis pour {application_id}")
        sources = ligne.get("sources") or []
        if isinstance(sources, Mapping):
            sources = [sources]
        if not isinstance(sources, list):
            raise ImportInvalide("sources : liste attendue")
        entrees.append({
            "application_id": application_id,
            "nom": nom,
            "proprietaire": proprietaire,
            "sources": [_source(s) for s in sources if isinstance(s, Mapping)],
        })
    return entrees
