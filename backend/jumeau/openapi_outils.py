"""Génération de manifestes d'outils depuis OpenAPI (ADR-0004).

Chaque opération d'un document OpenAPI devient un manifeste déclaratif. GET et HEAD sont des lectures
(`observer`, `lecture_seule=True`) ; toute autre méthode est une écriture (`agir`, `lecture_seule=False`,
effets de bord déclarés). Le module ne produit ni URL d'exécution, ni secret, ni adaptateur, et ne charge
aucun code : les schémas sont réduits aux seules clés structurelles lisibles.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import Any

from jumeau import interfaces
from jumeau.capacites import ManifesteOutil, RegistreCapacites

_METHODES_LECTURE = frozenset({"GET", "HEAD"})
_TYPES_JSON = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
_CLES_SCHEMA = (
    "type", "format", "properties", "required", "items", "additionalProperties",
    "nullable", "oneOf", "anyOf", "allOf",
)
_BORNES_SCHEMA = ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems")
_RE_URL = re.compile(r"(?i)(?:[a-z][a-z0-9+.\-]*://|(?<![\w.])www\.[a-z0-9])")
_RE_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_RE_AFFECTATION_SENSIBLE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_./+~-]{6,}"
)
_RE_JETON_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}")
_RE_NON_NOM = re.compile(r"[^a-z0-9_]+")
_RE_SEPARATEURS = re.compile(r"[-_]{2,}")
_RE_FORMAT = re.compile(r"^[A-Za-z0-9_.-]+$")

_PROFONDEUR_MAX = 32
_LONGUEUR_NOM_MAX = 80


class ErreurOpenAPI(ValueError):
    """Le document ne contient aucune opération exploitable et les diagnostics expliquent pourquoi."""


def _segment(valeur: Any) -> str:
    """Un fragment de nom stable : minuscules, chiffres et séparateurs simples."""
    brut = unicodedata.normalize("NFKD", str(valeur or ""))
    brut = "".join(caractere for caractere in brut if not unicodedata.combining(caractere)).lower()
    brut = _RE_NON_NOM.sub("-", brut)
    brut = _RE_SEPARATEURS.sub("-", brut).strip("_-")
    return brut


def _slug_application(application_id: str) -> str:
    segment = _segment(application_id) or "application"
    if not segment[0].isalpha():
        segment = f"a-{segment}"
    return segment


def _nom_base(application_id: str, operation: Any, detail: dict) -> str:
    operation_id = detail.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        partie = _segment(operation_id) or "operation"
    else:
        partie = f"{operation.method.lower()}.{_segment(operation.path) or 'operation'}"
    return f"{_slug_application(application_id)}.{partie}"


def _nom_unique(base: str, method: str, path: str, utilises: set[str]) -> str:
    if base not in utilises and len(base) <= _LONGUEUR_NOM_MAX:
        return base
    empreinte = hashlib.sha256(f"{method} {path}".encode("utf-8")).hexdigest()[:8]
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


def _texte_sur(valeur: Any, longueur_max: int = 4000) -> str | None:
    """Un texte utilisable dans un manifeste : ni URL, ni HTML, ni affectation de secret."""
    if not isinstance(valeur, str):
        return None
    texte = valeur.strip()
    if not texte or len(texte) > longueur_max:
        return None
    if _RE_URL.search(texte) or _RE_HTML.search(texte):
        return None
    if _RE_AFFECTATION_SENSIBLE.search(texte) or _RE_JETON_BEARER.search(texte):
        return None
    return texte


def _description(detail: dict, method: str, path: str, application_id: str) -> str:
    for cle in ("summary", "description"):
        texte = _texte_sur(detail.get(cle))
        if texte is not None:
            return texte
    secours = _texte_sur(f"{method} {path} — opération OpenAPI de {application_id}")
    return secours or "Opération OpenAPI importée"


def _resoudre(noeud: Any, document: dict, vus: tuple[str, ...] = ()) -> Any:
    """Résout uniquement les références locales `#/...` ; une référence externe n'est jamais suivie."""
    if not isinstance(noeud, dict):
        return noeud
    reference = noeud.get("$ref")
    if not isinstance(reference, str):
        return noeud
    if reference in vus or len(vus) >= _PROFONDEUR_MAX or not reference.startswith("#/"):
        return None
    cible: Any = document
    for morceau in reference[2:].split("/"):
        morceau = morceau.replace("~1", "/").replace("~0", "~")
        if not isinstance(cible, dict) or morceau not in cible:
            return None
        cible = cible[morceau]
    return _resoudre(cible, document, (*vus, reference))


def _schema_sur(valeur: Any, document: dict, profondeur: int = 0) -> Any:
    """Réduit un schéma OpenAPI à ses clés structurelles, sans annotation ni exemple porteur de secret."""
    if profondeur > _PROFONDEUR_MAX:
        return None
    if isinstance(valeur, bool):
        return valeur
    if not isinstance(valeur, dict):
        return None
    resolu = _resoudre(valeur, document)
    if not isinstance(resolu, dict):
        return None

    sortie: dict[str, Any] = {}
    type_brut = resolu.get("type")
    if isinstance(type_brut, str) and type_brut.lower() in _TYPES_JSON:
        sortie["type"] = type_brut.lower()
    elif isinstance(type_brut, list):
        types = [t.lower() for t in type_brut if isinstance(t, str) and t.lower() in _TYPES_JSON]
        if types:
            sortie["type"] = types

    format_brut = resolu.get("format")
    if isinstance(format_brut, str) and _RE_FORMAT.fullmatch(format_brut):
        sortie["format"] = format_brut

    proprietes = resolu.get("properties")
    if isinstance(proprietes, dict):
        propres: dict[str, Any] = {}
        for cle, sous_schema in proprietes.items():
            nom = _texte_sur(cle, 256)
            if nom is None:
                continue
            reduit = _schema_sur(sous_schema, document, profondeur + 1)
            if reduit is not None:
                propres[nom] = reduit
        if propres:
            sortie["properties"] = propres

    requis = resolu.get("required")
    if isinstance(requis, list):
        noms: list[str] = []
        for element in requis:
            nom = _texte_sur(element, 256)
            if nom is not None and nom not in noms:
                noms.append(nom)
        if noms:
            sortie["required"] = noms

    for cle in ("oneOf", "anyOf", "allOf"):
        variantes = resolu.get(cle)
        if isinstance(variantes, list):
            reduites = [_schema_sur(variante, document, profondeur + 1) for variante in variantes]
            reduites = [variante for variante in reduites if variante is not None]
            if reduites:
                sortie[cle] = reduites

    if "items" in resolu:
        items = _schema_sur(resolu.get("items"), document, profondeur + 1)
        if items is not None:
            sortie["items"] = items

    if "additionalProperties" in resolu:
        supplement = resolu.get("additionalProperties")
        if isinstance(supplement, bool):
            sortie["additionalProperties"] = supplement
        else:
            reduit = _schema_sur(supplement, document, profondeur + 1)
            if reduit is not None:
                sortie["additionalProperties"] = reduit

    if isinstance(resolu.get("nullable"), bool):
        sortie["nullable"] = resolu["nullable"]

    for cle in _BORNES_SCHEMA:
        borne = resolu.get(cle)
        if isinstance(borne, (int, float)) and not isinstance(borne, bool) and math.isfinite(float(borne)):
            sortie[cle] = borne

    if isinstance(resolu.get("uniqueItems"), bool):
        sortie["uniqueItems"] = resolu["uniqueItems"]

    return {cle: sortie[cle] for cle in _CLES_SCHEMA if cle in sortie} | {
        cle: sortie[cle] for cle in (*_BORNES_SCHEMA, "uniqueItems") if cle in sortie
    }


def _schema_parametre(parametre: dict, document: dict) -> Any:
    schema = parametre.get("schema")
    if schema is None:
        contenu = parametre.get("content")
        if isinstance(contenu, dict):
            for media in contenu.values():
                if isinstance(media, dict) and "schema" in media:
                    schema = media.get("schema")
                    break
    if schema is None:
        return {}
    reduit = _schema_sur(schema, document)
    return {} if reduit is None else reduit


def _schema_corps(corps: dict, document: dict) -> Any:
    contenu = corps.get("content")
    if not isinstance(contenu, dict) or not contenu:
        if "schema" in corps:
            return _schema_sur(corps.get("schema"), document)
        return None
    ordre = sorted(contenu, key=lambda media: 0 if isinstance(media, str) and "json" in media.lower() else 1)
    for type_media in ordre:
        media = contenu.get(type_media)
        if isinstance(media, dict) and "schema" in media:
            return _schema_sur(media.get("schema"), document)
    return None


def _parametres(element: Any, detail: dict, document: dict) -> dict[tuple[str, str], dict]:
    trouves: dict[tuple[str, str], dict] = {}
    for source in (element, detail):
        if not isinstance(source, dict):
            continue
        parametres = source.get("parameters")
        if not isinstance(parametres, list):
            continue
        for brut in parametres:
            parametre = _resoudre(brut, document)
            if not isinstance(parametre, dict):
                continue
            emplacement = parametre.get("in")
            nom = parametre.get("name")
            if emplacement not in ("path", "query", "body"):
                continue
            if not isinstance(nom, str) or not nom.strip():
                continue
            trouves[(nom.strip(), emplacement)] = parametre
    return trouves


def _schema_entree(element: Any, detail: dict, document: dict) -> Any:
    proprietes: dict[str, Any] = {}
    requis: list[str] = []
    for (nom, emplacement), parametre in _parametres(element, detail, document).items():
        if emplacement == "body":
            schema_corps = _schema_parametre(parametre, document)
            cle = "body" if "body" not in proprietes else "corps"
            if _texte_sur(cle, 256) is None:
                continue
            proprietes[cle] = schema_corps
            if parametre.get("required") is True and cle not in requis:
                requis.append(cle)
            continue
        cle = nom if nom not in proprietes else f"{emplacement}_{nom}"
        if _texte_sur(cle, 256) is None:
            continue
        proprietes[cle] = _schema_parametre(parametre, document)
        if emplacement == "path" or parametre.get("required") is True:
            if cle not in requis:
                requis.append(cle)

    corps = _resoudre(detail.get("requestBody"), document)
    if isinstance(corps, dict):
        schema_corps = _schema_corps(corps, document)
        if schema_corps is not None:
            cle = "body" if "body" not in proprietes else "corps"
            if _texte_sur(cle, 256) is not None:
                proprietes[cle] = schema_corps
                if corps.get("required") is True and cle not in requis:
                    requis.append(cle)

    if not proprietes:
        return {}
    schema: dict[str, Any] = {"type": "object", "properties": proprietes}
    if requis:
        schema["required"] = requis
    return schema


def _detail(document: Any, operation: Any) -> tuple[Any, Any]:
    if not isinstance(document, dict):
        return None, None
    chemins = document.get("paths")
    if not isinstance(chemins, dict):
        return None, None
    element = chemins.get(operation.path)
    if not isinstance(element, dict):
        return None, None
    detail = element.get(operation.method.lower())
    return element, (detail if isinstance(detail, dict) else None)


def _document(texte: str) -> Any:
    if not texte.strip():
        return None
    donnees, erreur = interfaces._charger_document(texte)
    return donnees if erreur is None and isinstance(donnees, dict) else None


def manifests_depuis_openapi(
    application_id: str,
    texte: str,
    locator: str = "openapi",
    version: str = "1.0.0",
    tenant: Any = None,
    persona: Any = None,
    perimetre: Any = None,
) -> list[ManifesteOutil]:
    """Lit un document OpenAPI et rend un manifeste par opération, sans exécution ni secret.

    Un document illisible, vide ou sans aucune opération lève `ErreurOpenAPI` avec les diagnostics du
    parseur. Un document partiellement lisible rend les manifestes des opérations valides.
    """
    if not isinstance(application_id, str) or not application_id.strip():
        raise ErreurOpenAPI("application_id : chaîne non vide attendue")
    if not isinstance(texte, str):
        raise ErreurOpenAPI("texte : chaîne OpenAPI attendue")

    graphe = interfaces.parse_openapi(application_id, texte, locator)
    if not graphe.operations:
        if graphe.diagnostics:
            detail = "; ".join(graphe.diagnostics[:3])
            raise ErreurOpenAPI(f"document OpenAPI illisible ou sans opération : {detail}")
        return []

    document = _document(texte)
    manifestes: list[ManifesteOutil] = []
    noms: set[str] = set()
    for operation in graphe.operations:
        element, detail = _detail(document, operation)
        if detail is None:
            detail = {}
        base = _nom_base(application_id, operation, detail)
        nom = _nom_unique(base, operation.method, operation.path, noms)
        noms.add(nom)
        lecture_seule = operation.method in _METHODES_LECTURE
        manifestes.append(ManifesteOutil(
            nom=nom,
            version=version,
            description=_description(detail, operation.method, operation.path, application_id),
            capacite="observer" if lecture_seule else "agir",
            schema_entree=_schema_entree(element, detail, document) if isinstance(document, dict) else {},
            schema_sortie={},
            tenant=tenant,
            persona=persona,
            perimetre=perimetre,
            lecture_seule=lecture_seule,
            cout=0.0,
            timeout_ms=5000,
            mode_preuve="OBSERVED",
            effets_de_bord=() if lecture_seule else (f"ecriture_{operation.method.lower()}",),
            source="openapi",
        ))
    return manifestes


def charger_dans(
    registre: RegistreCapacites,
    application_id: str,
    texte: str,
    locator: str = "openapi",
    version: str = "1.0.0",
    tenant: Any = None,
    persona: Any = None,
    perimetre: Any = None,
) -> list[str]:
    """Génère puis enregistre les manifestes dans un `RegistreCapacites` ; rend leurs noms."""
    enregistrer = getattr(registre, "enregistrer", None)
    if not callable(enregistrer):
        raise TypeError("registre capacitaire attendu")
    manifestes = manifests_depuis_openapi(
        application_id, texte, locator, version, tenant, persona, perimetre)
    noms: list[str] = []
    for manifeste in manifestes:
        enregistrer(manifeste)
        noms.append(manifeste.nom)
    return noms


__all__ = ["ErreurOpenAPI", "charger_dans", "manifests_depuis_openapi"]
