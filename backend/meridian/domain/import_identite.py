"""Import d'identité de commande depuis une CMDB ou un manifeste JSON/CSV.

Aucune source n'est interrogée ici : le contenu fourni est une donnée. Le parseur ne conserve que
l'identité typée du jumeau (twin_id stable, application_id optionnel, identifiants externes) et une
liste de sources normalisées ; les secrets restent des références.
"""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
import unicodedata
from typing import Any, Mapping

APPLICATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
TWIN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

TYPES_TWIN = ("APPLICATION", "TEAM", "RESOURCE", "SUPPLIER", "ECOSYSTEM")
TYPE_TWIN_DEFAUT = "APPLICATION"
TYPES_SANS_APPLICATION_ID = frozenset({"TEAM", "ECOSYSTEM"})

PREFIXES_TWIN_ID = {
    "APPLICATION": "app",
    "TEAM": "team",
    "RESOURCE": "resource",
    "SUPPLIER": "supplier",
    "ECOSYSTEM": "ecosystem",
}

IDENTIFIANTS_EXTERNES = {
    "APPLICATION": ("application_id", "app_id"),
    "TEAM": ("team_id", "equipe_id"),
    "RESOURCE": ("resource_id", "ressource_id", "ci", "asset_id"),
    "SUPPLIER": ("supplier_id", "fournisseur_id", "supplier_code", "code_fournisseur"),
    "ECOSYSTEM": ("ecosystem_id", "ecosysteme_id"),
}


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


def slug_perimetre(valeur: Any) -> str:
    """Identifiant de périmètre : accents retirés, minuscules, séparateurs `-` (jamais le texte affiché)."""
    texte = unicodedata.normalize("NFKD", _texte(valeur))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", texte.lower()).strip("-")


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


def normaliser_type_twin(valeur: Any = None) -> str:
    """Le type de Twin est explicite ; APPLICATION reste le défaut des anciens documents."""
    type_twin = _texte(valeur).upper() or TYPE_TWIN_DEFAUT
    if type_twin not in TYPES_TWIN:
        raise ImportInvalide(
            f"type de twin inconnu : {type_twin} (attendus : {', '.join(TYPES_TWIN)})"
        )
    return type_twin


def normaliser_identifiants(valeur: Any) -> dict[str, Any]:
    """Les identifiants métier restent des données indexables ; aucun secret n'est conservé."""
    if valeur in (None, ""):
        return {}
    if not isinstance(valeur, Mapping):
        raise ImportInvalide("identifiants : objet attendu")
    propres: dict[str, Any] = {}
    for cle, contenu in valeur.items():
        nom = _texte(cle)
        if not nom or nom.lower() in CHAMPS_SECRETS:
            continue
        propres[nom] = _config_sure(contenu)
    return propres


def _externe(type_twin: str, identifiants: Mapping[str, Any]) -> str:
    for cle in IDENTIFIANTS_EXTERNES.get(type_twin, ()):
        valeur = _texte(identifiants.get(cle))
        if valeur:
            return valeur
    return ""


def generer_twin_id(type_twin: str) -> str:
    """Aucun nom ni application_id n'est inventé : l'identité interne est générée puis stable."""
    prefixe = PREFIXES_TWIN_ID.get(type_twin, "twin")
    return f"{prefixe}-{secrets.token_hex(6)}"


def construire_identite(
    type_twin: Any = None,
    *,
    twin_id: Any = "",
    application_id: Any = "",
    perimetre: Any = "",
    perimetre_id: Any = "",
    identifiants: Any = None,
    candidat: bool = False,
) -> dict[str, Any]:
    """Valide une identité typée et rend les champs persistés dans la commande et le jumeau.

    APPLICATION exige un application_id ou un mode candidat explicite ; TEAM et ECOSYSTEM n'en
    portent pas. RESOURCE et SUPPLIER s'appuient sur un identifiant externe ou un twin_id généré.
    """
    type_norm = normaliser_type_twin(type_twin)
    app = _texte(application_id).lower()
    if app and not APPLICATION_ID.fullmatch(app):
        raise ImportInvalide(f"application_id invalide : {application_id}")
    ids = normaliser_identifiants(identifiants)
    if type_norm in TYPES_SANS_APPLICATION_ID and app:
        raise ImportInvalide(f"application_id interdit pour un twin {type_norm}")
    if type_norm == "APPLICATION" and not app and not candidat:
        raise ImportInvalide(
            "application_id requis pour un twin APPLICATION (ou mode candidat explicite)"
        )

    tid = _texte(twin_id).lower()
    if tid and not TWIN_ID.fullmatch(tid):
        raise ImportInvalide(f"twin_id invalide : {twin_id}")
    if not tid:
        candidat_id = app if type_norm == "APPLICATION" else _externe(type_norm, ids)
        candidat_id = candidat_id.lower()
        if candidat_id and TWIN_ID.fullmatch(candidat_id):
            tid = candidat_id
    if not tid:
        tid = generer_twin_id(type_norm)

    perimetre_texte = _texte(perimetre)
    return {
        "type_twin": type_norm,
        "twin_id": tid,
        "application_id": app,
        "perimetre": perimetre_texte,
        "perimetre_id": _texte(perimetre_id) or slug_perimetre(perimetre_texte),
        "identifiants": ids,
        "candidat": bool(candidat and not app),
    }


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
        "identite": {
            cle: entree[cle]
            for cle in ("type_twin", "twin_id", "application_id", "nom", "proprietaire",
                        "perimetre", "perimetre_id", "identifiants")
        },
        "nouvelles": nouvelles,
        "ignorees": ignorees,
    }


def _candidat(ligne: Mapping) -> bool:
    marqueur = _texte(ligne.get("candidat") or ligne.get("candidate")).lower()
    mode = _texte(ligne.get("mode_identite") or ligne.get("mode")).lower()
    return marqueur in {"1", "true", "oui", "yes", "candidat", "candidate"} or mode in {
        "candidat", "candidate",
    }


def _identifiants_ligne(ligne: Mapping, type_twin: str) -> dict[str, Any]:
    identifiants = normaliser_identifiants(ligne.get("identifiants"))
    for cle in IDENTIFIANTS_EXTERNES.get(type_twin, ()):
        if cle not in identifiants and _texte(ligne.get(cle)):
            identifiants[cle] = _texte(ligne.get(cle))
    return identifiants


def analyser(contenu: Any, mode: str = "cmdb") -> list[dict]:
    """Rend des entrées normalisées : type, twin_id, application_id, nom, propriétaire, sources."""
    if mode not in {"cmdb", "manifeste", "fichier", "inventaire"}:
        raise ImportInvalide(f"mode d'import inconnu : {mode}")
    entrees = []
    for ligne in _lignes(contenu):
        type_twin = normaliser_type_twin(
            _premier(ligne, ("type_twin", "typeTwin", "type"))
        )
        application_id = _premier(
            ligne, ("application_id", "applicationId", "app_id", "app")
        )
        if type_twin == "APPLICATION" and not application_id:
            application_id = _premier(ligne, ("id",))
        twin_id = _premier(ligne, ("twin_id", "twinId"))
        if type_twin != "APPLICATION" and not twin_id:
            twin_id = _premier(ligne, ("id",))
        candidat = _candidat(ligne)
        if type_twin == "APPLICATION" and not application_id and not candidat:
            raise ImportInvalide("application_id requis")
        identifiants = _identifiants_ligne(ligne, type_twin)
        identite = construire_identite(
            type_twin,
            twin_id=twin_id,
            application_id=application_id,
            perimetre=_premier(ligne, ("perimetre", "périmètre", "scope")),
            perimetre_id=_premier(ligne, ("perimetre_id", "perimetreId", "scope_id")),
            identifiants=identifiants,
            candidat=candidat,
        )
        nom = _premier(ligne, ("nom", "name", "libelle", "label")) or identite["twin_id"]
        proprietaire = _premier(ligne, ("proprietaire", "propriétaire", "owner", "responsable"))
        if not proprietaire:
            raise ImportInvalide(f"propriétaire requis pour {identite['twin_id']}")
        sources = ligne.get("sources") or []
        if isinstance(sources, Mapping):
            sources = [sources]
        if not isinstance(sources, list):
            raise ImportInvalide("sources : liste attendue")
        entrees.append({
            **identite,
            "nom": nom,
            "proprietaire": proprietaire,
            "sources": [_source(s) for s in sources if isinstance(s, Mapping)],
        })
    return entrees
