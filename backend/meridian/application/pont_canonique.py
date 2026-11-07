"""Pont Travail → canonique : construction d'événements et mapping vers la boucle P1.

Ce module est **pur** : il ne lit ni Mongo ni Postgres. Il construit un document d'outbox
déterministe, le hash de son contenu et les objets canoniques correspondants. L'écriture est
faite par :mod:`meridian.adapters.outbound.postgres.pont_canonique` dans une seule transaction.

Règles structurantes :

- ADR-0008 : un `case` n'est pas un objet canonique. Seule sa `Situation` liée (`situations[0]`)
  peut produire des objets ; un case sans situation ne produit rien.
- un `init-*` sans décision humaine (`decision_id`/`decision_ref` ou `reponse.choix`) ne produit
  jamais d'Initiative : c'est la garde C0a, réappliquée au live.
- aucun Learning n'est fabriqué à partir d'une mesure : `enseignement` est obligatoire.
- les statuts legacy sont traduits vers le vocabulaire canonique ; les priorités sont bornées à
  HAUTE/MOYENNE/BASSE.
- `version` n'est jamais transmis : le dépôt canonique incrémente la version sur une mise à jour.

Le hash de contenu est posé dans ``donnees._pont.hash`` sur chaque objet canonique. Il permet au
worker de sauter une réécriture identique sans faire monter la version ni l'historique.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import copy
import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from meridian.domain import modele_entreprise as modele
from meridian.domain.tenant import TenantError, normaliser_slug

__all__ = [
    "ConflitCanonique",
    "ETATS",
    "OPERATION_CASE",
    "OPERATION_INITIATIVE",
    "OPERATION_LEARNING",
    "OPERATION_OBJETS",
    "OPERATION_OUTCOME",
    "OPERATION_SITUATION",
    "OPERATIONS",
    "ORIGINE_LEGACY",
    "PontInvalide",
    "TenantMismatch",
    "assainir",
    "backoff_secondes",
    "cle_idempotence",
    "construire_evenement",
    "construire_objets",
    "decision_case_id",
    "decision_initiative_id",
    "decision_situation_id",
    "evenement_case",
    "evenement_depuis_case",
    "evenement_depuis_initiative",
    "evenement_depuis_situation",
    "evenement_initiative",
    "evenement_learning",
    "evenement_outcome",
    "evenement_situation",
    "hash_contenu",
    "identifiant_evenement",
    "initiative_id",
    "investigation_id",
    "learning_id",
    "mapper_case",
    "mapper_initiative",
    "mapper_learning",
    "mapper_outcome",
    "mapper_situation",
    "normaliser_operation",
    "normaliser_tenant",
    "objets_depuis_evenement",
    "outcome_id",
    "priorite_canonique",
    "statut_canonique",
    "valider_tenant",
]

OPERATION_SITUATION = "situation.maj"
OPERATION_CASE = "case.maj"
OPERATION_INITIATIVE = "initiative.maj"
OPERATION_OUTCOME = "outcome.mesure"
OPERATION_LEARNING = "learning.capitalisation"
OPERATION_OBJETS = "objets.upsert"

OPERATIONS = (
    OPERATION_SITUATION,
    OPERATION_CASE,
    OPERATION_INITIATIVE,
    OPERATION_OUTCOME,
    OPERATION_LEARNING,
    OPERATION_OBJETS,
)
ETATS = ("pending", "done", "failed")
ORIGINE_LEGACY = "legacy"

_MARQUEURS_SECRETS = ("password", "passwd", "secret", "token", "credential", "authorization")
_CLES_SECRETES = frozenset({
    "pwd", "pass", "auth", "key", "apikey", "api_key", "api-key", "access_key", "accesskey",
    "private_key", "privatekey", "client_secret", "clientsecret", "bearer", "password", "passwd",
})
_CHAMPS_TABLE = frozenset({
    "id", "tenant_id", "famille", "type", "mode", "titre", "donnees", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
})
_ORDRE_TYPES = {
    "SITUATION": 0,
    "INVESTIGATION": 1,
    "DECISION": 2,
    "INITIATIVE": 3,
    "OUTCOME": 4,
    "LEARNING": 5,
}
_MODE_DEFAUT = {
    "SITUATION": "OBSERVED",
    "INVESTIGATION": "DECLARED",
    "DECISION": "DECLARED",
    "INITIATIVE": "DECLARED",
    "OUTCOME": "OBSERVED",
    "LEARNING": "INFERRED",
}

# Champs legacy recopiés dans `donnees` : liste fermée, jamais le document entier.
_CHAMPS_SITUATION = (
    "nature", "type", "verbe", "score", "detectee", "indicateurs", "decouverte_quoi",
    "decouverte_pourquoi", "reste_a_comprendre", "decisions_attendues", "chronologie",
    "hypotheses", "contributions", "preuves", "synthese", "actions_proposees", "opportunite",
    "decidee_le", "statut_legacy", "priorite_legacy",
)
_CHAMPS_CASE = (
    "objectif", "resume", "prochaine_etape", "type", "genre", "num", "responsable",
    "sensibilite", "portee", "origine", "veille",
)
_CHAMPS_INITIATIVE = (
    "raison", "urgence", "genre", "confiance", "declencheur", "source", "situation_id",
    "quand", "reponse", "travail_id",
)


class PontInvalide(ValueError):
    """Un événement ou un objet ne peut pas être construit sans inventer de sémantique."""


class TenantMismatch(PontInvalide):
    """Le document legacy n'appartient pas au tenant de l'événement."""


class ConflitCanonique(PontInvalide):
    """Un identifiant canonique existe déjà avec une origine non légacy : on n'écrase pas."""


# ---------------------------------------------------------------------------
# Identité, hash, tenant, assainissement
# ---------------------------------------------------------------------------


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _texte_legacy(valeur: Any) -> str:
    """Texte d'un champ legacy ; un conteneur n'est jamais stringifié (risque de secret)."""
    if valeur is None or isinstance(valeur, (bool, bytes, bytearray, Mapping,
                                             list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (str, Mapping)) or not isinstance(valeur, Iterable):
        return [valeur]
    return list(valeur)


def _textes(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = element.get("texte") or element.get("titre") or element.get("option")
        texte = _texte_legacy(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _ids(valeur: Any) -> list[str]:
    resultat: list[str] = []
    for element in _liste(valeur):
        if isinstance(element, Mapping):
            element = element.get("id") or element.get("twin_id") or element.get("situation_id")
        texte = _texte_legacy(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _mapping(valeur: Any) -> dict[str, Any]:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _cle(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def normaliser_tenant(tenant_id: Any) -> str:
    """Valide et canonise le tenant ; ne fabrique jamais de tenant par défaut."""
    if tenant_id is None or not _texte(tenant_id):
        raise PontInvalide("tenant_id obligatoire")
    try:
        return normaliser_slug(tenant_id)
    except TenantError as exc:
        raise PontInvalide(str(exc)) from exc


valider_tenant = normaliser_tenant


def _cle_sensible(cle: Any) -> bool:
    normalisee = unquote_plus(str(cle)).strip().lower()
    if normalisee.endswith(("_ref", "-ref", "_reference", "-reference")):
        return False
    compacte = normalisee.replace("-", "_")
    if compacte in _CLES_SECRETES:
        return True
    if compacte.endswith("_key"):
        return True
    return any(marque in compacte for marque in _MARQUEURS_SECRETS)


def _url_porte_un_secret(url: str) -> bool:
    try:
        parties = urlsplit(url)
    except (ValueError, UnicodeError):
        return True
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        return True
    return any(
        _cle_sensible(cle) and valeur not in ("", "***")
        for cle, valeur in parse_qsl(parties.query, keep_blank_values=True)
    )


def assainir(valeur: Any) -> Any:
    """Copie JSON stricte, sans clé sensible ni URL porteuse de secret.

    La fonction est volontairement récursive et fermée : un type inconnu devient sa forme
    textuelle, jamais un objet BSON opaque. Les documents legacy ne sont donc jamais copiés
    en entier dans l'outbox.
    """
    if valeur is None or isinstance(valeur, (bool, int, str)):
        if isinstance(valeur, str) and _url_porte_un_secret(valeur):
            return "[redacted]"
        return valeur
    if isinstance(valeur, float):
        if valeur != valeur or valeur in (float("inf"), float("-inf")):
            raise PontInvalide("nombre non fini")
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
            if str(cle) == "_id" or _cle_sensible(cle):
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
    """Hash stable (JSON trié) du contenu assaini ; sert à l'idempotence et au skip d'écriture."""
    charge = assainir(valeur)
    texte = json.dumps(charge, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def identifiant_evenement(tenant_id: Any, operation: Any, canonical_id: Any,
                          source_event_id: Any = None) -> str:
    """`sha256(tenant|operation|canonical_id|source_event_id)[:32]`."""
    tenant = normaliser_tenant(tenant_id)
    operation_texte = _texte(operation)
    identifiant = _texte(canonical_id)
    if not operation_texte:
        raise PontInvalide("operation obligatoire")
    if not identifiant:
        raise PontInvalide("canonical_id obligatoire")
    source = _iso(source_event_id) or _texte(source_event_id)
    graine = f"{tenant}|{operation_texte}|{identifiant}|{source}"
    return hashlib.sha256(graine.encode("utf-8")).hexdigest()[:32]


cle_idempotence = identifiant_evenement


def backoff_secondes(tentatives: Any, *, base: int = 5, maximum: int = 3600) -> int:
    """Backoff exponentiel borné : base, 2×base, 4×base… sans dépasser ``maximum``."""
    if isinstance(tentatives, bool):
        raise PontInvalide("tentatives doit être un entier positif")
    try:
        nombre = int(tentatives)
    except (TypeError, ValueError) as exc:
        raise PontInvalide("tentatives doit être un entier positif") from exc
    if nombre < 1:
        nombre = 1
    if nombre > 32:  # évite un entier géant pour un compteur corrompu
        return int(maximum)
    return min(int(maximum), int(base) * (2 ** (nombre - 1)))


def _slug_identifiant(valeur: Any, defaut: str = "na") -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = re.sub(r"[^a-z0-9_-]+", "-", texte).strip("-_")
    texte = re.sub(r"-{2,}", "-", texte)
    return texte or defaut


def investigation_id(situation_id: Any) -> str:
    return f"inv-{_texte(situation_id)}"


def decision_situation_id(situation_id: Any, n: int = 1) -> str:
    return f"dec-sit-{_texte(situation_id)}-{int(n)}"


def decision_case_id(case_id: Any, n: int = 1) -> str:
    return f"dec-case-{_texte(case_id)}-{int(n)}"


def decision_initiative_id(initiative_id_: Any) -> str:
    return f"dec-init-{_texte(initiative_id_)}"


def initiative_id(decision_id: Any) -> str:
    return f"ini-{_texte(decision_id)}"


def outcome_id(initiative_id_: Any, metrique: Any, periode: Any = "") -> str:
    return (f"out-{_texte(initiative_id_)}-{_slug_identifiant(metrique, 'metrique')}-"
            f"{_slug_identifiant(periode, 'sans-periode')}")


def learning_id(source_id: Any) -> str:
    return f"lea-{_texte(source_id)}"


# ---------------------------------------------------------------------------
# Statuts, priorités, dates
# ---------------------------------------------------------------------------

_STATUTS = {
    "active": "CANDIDATE",
    "candidate": "CANDIDATE",
    "en observation": "OBSERVING",
    "observing": "OBSERVING",
    "surveillee": "WATCHED",
    "watched": "WATCHED",
    "en investigation": "INVESTIGATING",
    "investigating": "INVESTIGATING",
    "qualifiee": "QUALIFIED",
    "qualified": "QUALIFIED",
    "decidee": "DECIDED",
    "decided": "DECIDED",
    "poursuivie": "DECIDED",
    "reportee": "DEFERRED",
    "deferred": "DEFERRED",
    "ecartee": "DISMISSED",
    "classee": "DISMISSED",
    "ignoree": "DISMISSED",
    "dismissed": "DISMISSED",
    "archivee": "ARCHIVED",
    "archived": "ARCHIVED",
}

_PRIORITES = {
    "critique": "HAUTE",
    "critical": "HAUTE",
    "haute": "HAUTE",
    "high": "HAUTE",
    "normale": "MOYENNE",
    "normal": "MOYENNE",
    "moyenne": "MOYENNE",
    "moyen": "MOYENNE",
    "medium": "MOYENNE",
    "basse": "BASSE",
    "bas": "BASSE",
    "low": "BASSE",
}


def statut_canonique(valeur: Any) -> str:
    """Traduit un statut legacy (accents/casse/espaces) vers le vocabulaire canonique."""
    cle = _cle(valeur)
    if not cle:
        return "CANDIDATE"
    if cle in _STATUTS:
        return _STATUTS[cle]
    # Un code déjà canonique traverse sans être réinterprété.
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", _texte(valeur)):
        return _texte(valeur)
    return "CANDIDATE"


def priorite_canonique(valeur: Any) -> str:
    cle = _cle(valeur)
    if not cle:
        return "MOYENNE"
    return _PRIORITES.get(cle, "MOYENNE")


def _iso(valeur: Any, defaut: str | None = None) -> str | None:
    if valeur is None:
        return defaut
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    texte = _texte(valeur)
    if not texte:
        return defaut
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return defaut


def _date_depuis(doc: Mapping[str, Any], cles: Iterable[str], defaut: str) -> str:
    for cle in cles:
        valeur = _iso(doc.get(cle))
        if valeur:
            return valeur
    return defaut


def _instant_reference(evenement: Mapping[str, Any] | None, maintenant: Any = None) -> str:
    return (_iso(maintenant)
            or _iso((evenement or {}).get("cree_le"))
            or datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _document(valeur: Any, role: str = "document") -> dict[str, Any]:
    """Accepte un mapping ou un objet canonique sérialisable ; refuse le reste."""
    if isinstance(valeur, Mapping):
        return dict(valeur)
    convertisseur = getattr(valeur, "to_dict", None) or getattr(valeur, "as_dict", None)
    if callable(convertisseur):
        converti = convertisseur()
        if isinstance(converti, Mapping):
            return dict(converti)
    raise PontInvalide(f"{role} : document attendu")


def _titre(doc: Mapping[str, Any], identifiant: str) -> str:
    for cle in ("titre", "resume", "nom", "name", "question"):
        texte = _texte_legacy(doc.get(cle))
        if texte:
            return texte
    return identifiant


def _copier_champs(doc: Mapping[str, Any], champs: Iterable[str]) -> dict[str, Any]:
    return {champ: copy.deepcopy(doc[champ]) for champ in champs if champ in doc}


# ---------------------------------------------------------------------------
# Sérialisation d'un objet canonique avec le sceau `_pont`
# ---------------------------------------------------------------------------


def _serialiser(objet: Any, evenement: Mapping[str, Any] | None = None,
                extra_donnees: Mapping[str, Any] | None = None,
                type_attendu: str | None = None) -> dict[str, Any]:
    if isinstance(objet, Mapping):
        data = copy.deepcopy(dict(objet))
    else:
        convertisseur = getattr(objet, "to_dict", None) or getattr(objet, "as_dict", None)
        data = copy.deepcopy(convertisseur() if callable(convertisseur) else asdict(objet))
    data.pop("version", None)
    data.pop("_id", None)

    donnees: dict[str, Any] = {}
    if isinstance(data.get("donnees"), Mapping):
        donnees.update(data["donnees"])
    for cle, valeur in data.items():
        if cle in _CHAMPS_TABLE or cle == "donnees":
            continue
        donnees[cle] = valeur
    if extra_donnees:
        donnees.update(extra_donnees)
    donnees.pop("_pont", None)
    donnees.pop("_historique", None)

    type_objet = _texte(data.get("type") or data.get("type_") or data.get("type_objet")
                        or type_attendu).upper()
    if type_objet not in _ORDRE_TYPES:
        raise PontInvalide(f"type hors boucle : {type_objet or 'inconnu'}")
    famille = _texte(data.get("famille"))
    if not famille:
        from meridian.domain.modele_entreprise import famille_de
        famille = famille_de(type_objet)
    mode = _texte(data.get("mode")).upper() or _MODE_DEFAUT[type_objet]

    payload = {
        "id": _texte(data.get("id")),
        "tenant_id": _texte(data.get("tenant_id")),
        "famille": famille,
        "type": type_objet,
        "mode": mode,
        "titre": _texte(data.get("titre")),
        "donnees": assainir(donnees),
    }
    if not payload["id"]:
        raise PontInvalide("id obligatoire")
    if not payload["tenant_id"]:
        raise PontInvalide("tenant_id obligatoire")
    for champ in ("observe_le", "valide_depuis", "valide_jusqua", "cree_le"):
        valeur = data.get(champ)
        if valeur:
            payload[champ] = _iso(valeur, _texte(valeur))

    payload["donnees"]["_pont"] = {
        "hash": hash_contenu(payload),
        "origine": ORIGINE_LEGACY,
        "event_id": _texte((evenement or {}).get("_id")),
        "operation": _texte((evenement or {}).get("operation")),
        "source": assainir((evenement or {}).get("source") or {}),
    }
    return payload


def _ordonner(objets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vus: set[str] = set()
    for objet in objets:
        identifiant = _texte(objet.get("id"))
        if identifiant in vus:
            raise PontInvalide(f"identifiant canonique dupliqué : {identifiant}")
        vus.add(identifiant)
    return sorted(objets, key=lambda objet: _ORDRE_TYPES.get(_texte(objet.get("type")), 99))


# ---------------------------------------------------------------------------
# Validation tenant des documents legacy
# ---------------------------------------------------------------------------


def _verifier_document(doc: Any, tenant: str, role: str) -> Mapping[str, Any]:
    if not isinstance(doc, Mapping):
        raise PontInvalide(f"{role} : document attendu")
    declare = _texte(doc.get("tenant_id"))
    if declare:
        if normaliser_tenant(declare) != tenant:
            raise TenantMismatch(
                f"{role} du tenant {declare!r}, attendu {tenant!r}")
    return doc


# ---------------------------------------------------------------------------
# Constructeurs d'objets canoniques (purs : aucun import d'adaptateur)
# ---------------------------------------------------------------------------


def _objet(type_objet: str, identifiant: Any, tenant: str, titre: Any,
           donnees: Mapping[str, Any], *, mode: str | None = None,
           cree_le: Any = None, observe_le: Any = None,
           valide_depuis: Any = None, valide_jusqua: Any = None) -> dict[str, Any]:
    """Forme canonique minimale, prête pour ``boucle.enregistrer_boucle``."""
    type_normalise = _texte(type_objet).upper()
    if type_normalise not in _ORDRE_TYPES:
        raise PontInvalide(f"type hors boucle : {type_normalise or 'inconnu'}")
    payload = {
        "id": _texte(identifiant),
        "tenant_id": normaliser_tenant(tenant),
        "famille": modele.famille_de(type_normalise),
        "type": type_normalise,
        "mode": _texte(mode).upper() or _MODE_DEFAUT[type_normalise],
        "titre": _texte(titre),
        "donnees": dict(donnees),
    }
    for champ, valeur in (("cree_le", cree_le), ("observe_le", observe_le),
                          ("valide_depuis", valide_depuis),
                          ("valide_jusqua", valide_jusqua)):
        if valeur:
            payload[champ] = _iso(valeur, _texte(valeur))
    return payload


def _dates(reference: str) -> dict[str, str]:
    return {"cree_le": reference, "observe_le": reference, "valide_depuis": reference}


def _valeur_mesure(mesure: Any) -> Any:
    if isinstance(mesure, Mapping):
        for cle in ("valeur_observee", "valeur", "observed_value", "value", "resultat",
                    "résultat"):
            if cle in mesure and mesure[cle] is not None:
                return mesure[cle]
        return None
    if isinstance(mesure, bool):
        return mesure
    if isinstance(mesure, (str, int, float)):
        return mesure
    return None


def _investigation_pour_decision(tenant: str, situation_id_: str,
                                 source: Mapping[str, Any], evenement: Mapping[str, Any] | None,
                                 reference: str, investigation: Any = None) -> Any:
    if isinstance(investigation, Mapping):
        return investigation
    if investigation is not None and getattr(investigation, "type", "") == "INVESTIGATION":
        return investigation
    titre = _texte(source.get("titre")) or f"Comprendre {situation_id_}"
    question = (_texte(source.get("question") or source.get("resume") or source.get("titre"))
                or f"Comprendre {situation_id_}")
    return _objet("INVESTIGATION", investigation_id(situation_id_), tenant, titre, {
        "situation_id": situation_id_,
        "titre": titre,
        "question": question,
        "resume": question,
        "statut": "OPEN",
        "incertitudes": [],
    }, mode="DECLARED", **_dates(reference))


def _decision_tranchee(investigation: Any, texte_decision: Any, options: Any, acteur: Any,
                       decide_le: Any, rationale: Any, identifiant: str,
                       evenement: Mapping[str, Any] | None, reference: str,
                       extra_donnees: Mapping[str, Any] | None = None) -> dict[str, Any]:
    texte = _texte_legacy(texte_decision)
    if not texte:
        raise PontInvalide("décision sans texte")
    options_normalisees = _textes(options)
    if not options_normalisees:
        options_normalisees = [texte]
    hors_options = not any(texte.casefold() == option.casefold()
                           for option in options_normalisees)
    if hors_options:
        options_normalisees.append(texte)

    tenant = _texte(_donnee(investigation, "tenant_id"))
    titre = _texte_legacy(_donnee(investigation, "titre")) or f"Décider — {identifiant}"
    donnees = {
        "investigation_id": _texte(_donnee(investigation, "id")),
        "situation_id": _texte(_donnee(investigation, "situation_id")),
        "titre": titre,
        "resume": _texte_legacy(rationale),
        "options": options_normalisees,
        "criteres": [],
        "incertitudes": [],
        "statut": "DECIDED",
        "acteur": _texte_legacy(acteur) or ORIGINE_LEGACY,
        "choix": texte,
        "decide_le": _iso(decide_le, reference),
        "rationale": _texte_legacy(rationale),
    }
    donnees.update(extra_donnees or {})
    donnees["options"] = options_normalisees
    donnees["choix_hors_options"] = hors_options
    decision = _objet("DECISION", identifiant, tenant, titre, donnees,
                      mode="DECLARED", **_dates(reference))
    return _serialiser(decision, evenement)


def _donnee(objet: Any, nom: str) -> Any:
    if isinstance(objet, Mapping):
        if nom in objet:
            return objet[nom]
        donnees = objet.get("donnees")
        return donnees.get(nom) if isinstance(donnees, Mapping) else None
    return getattr(objet, nom, None)


def _decisions_situation(doc: Mapping[str, Any], statut: str = "") -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    brut = doc.get("decisions")
    if isinstance(brut, (list, tuple)):
        for element in brut:
            if isinstance(element, Mapping):
                texte = element.get("texte") or element.get("decision")
                if _texte_legacy(texte):
                    decisions.append(dict(element))
            elif _texte_legacy(element):
                decisions.append({"texte": _texte_legacy(element)})
    # Un champ `decision` isolé n'est retenu que si la situation est réellement décidée :
    # une situation réactivée après archivage ne doit pas ressusciter une ancienne décision.
    decidee = statut in {"DECIDED", "DISMISSED"} or _cle(doc.get("statut")) in {
        "decidee", "poursuivie"}
    if not decisions and _texte_legacy(doc.get("decision")) and decidee:
        decisions.append({
            "texte": doc.get("decision"),
            "options": doc.get("options"),
            "par": doc.get("decidee_par"),
            "quand": doc.get("decidee_le"),
            "motif": doc.get("decision_motif"),
        })
    return decisions


def objets_depuis_situation(situation: Any, *, tenant_id: Any = None,
                            evenement: Mapping[str, Any] | None = None,
                            maintenant: Any = None) -> list[dict[str, Any]]:
    doc = _document(situation, "situation")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    doc = _verifier_document(doc, tenant, "situation")
    sid = _texte(doc.get("id"))
    if not sid:
        raise PontInvalide("situation sans id")
    reference = _instant_reference(evenement, maintenant)
    cree = _date_depuis(doc, ("cree_le", "detectee", "observe_le", "maj_le"), reference)
    observe = _date_depuis(doc, ("observe_le", "detectee", "cree_le", "maj_le"), cree)
    valide = _date_depuis(doc, ("valide_depuis", "detectee", "cree_le", "maj_le"), observe)
    titre = _titre(doc, sid)
    description = (_texte_legacy(doc.get("resume")) or _texte_legacy(doc.get("decouverte_quoi"))
                   or _texte_legacy(doc.get("question")) or titre)

    statut = statut_canonique(doc.get("statut"))
    priorite = priorite_canonique(doc.get("priorite"))
    twin_ids = _ids(doc.get("twin_ids") if doc.get("twin_ids") is not None else doc.get("jumeaux"))
    resume = _texte_legacy(doc.get("resume")) or description
    donnees_situation = {
        "titre": titre,
        "description": description,
        "resume": resume,
        "statut": statut,
        "priorite": priorite,
        "twin_ids": twin_ids,
        "signal_ids": _ids(doc.get("signal_ids")),
        "claim_ids": _ids(doc.get("claim_ids")),
        "opportunite_ids": _ids(doc.get("opportunite_ids")),
        "risk_ids": _ids(doc.get("risk_ids")),
        "inconnues": _textes(doc.get("reste_a_comprendre")),
    }
    donnees_situation.update(_copier_champs(doc, _CHAMPS_SITUATION))
    donnees_situation["statut_legacy"] = _texte(doc.get("statut"))
    donnees_situation["priorite_legacy"] = _texte(doc.get("priorite"))
    donnees_situation["jumeaux"] = list(twin_ids)
    situation_canonique = _objet(
        "SITUATION", sid, tenant, titre, donnees_situation, mode="DECLARED",
        cree_le=cree, observe_le=observe, valide_depuis=valide)
    objets = [_serialiser(situation_canonique, evenement)]

    question = _texte_legacy(doc.get("question")) or description
    investigation = _objet(
        "INVESTIGATION", investigation_id(sid), tenant, titre, {
            "situation_id": sid,
            "titre": titre,
            "question": question,
            "resume": resume,
            "statut": "CLOSED" if statut in {"DISMISSED", "ARCHIVED"} else "OPEN",
            "incertitudes": [],
        }, mode="DECLARED", cree_le=cree, observe_le=observe, valide_depuis=valide)
    objets.append(_serialiser(investigation, evenement))

    decisions: list[dict[str, Any]] = []
    for rang, decision_doc in enumerate(_decisions_situation(doc, statut), 1):
        identifiant = decision_situation_id(sid, rang)
        decision = _decision_tranchee(
            investigation,
            decision_doc.get("texte") or decision_doc.get("decision"),
            decision_doc.get("options") if decision_doc.get("options") is not None else doc.get("options"),
            decision_doc.get("par") or doc.get("decidee_par"),
            decision_doc.get("quand") or doc.get("decidee_le"),
            decision_doc.get("motif") or doc.get("decision_motif") or doc.get("resume"),
            identifiant, evenement, reference,
            extra_donnees={"situation_id": sid, "investigation_id": investigation_id(sid),
                           "rang": rang},
        )
        objets.append(decision)
        decisions.append(decision)

    if _cle(doc.get("statut")) == "poursuivie" and decisions:
        decision_source = decisions[-1]
        titre_initiative = (_texte(doc.get("initiative_titre"))
                            or f"Mettre en œuvre — {titre}")
        initiative = _objet(
            "INITIATIVE", initiative_id(decision_source["id"]), tenant,
            titre_initiative, {
                "decision_id": decision_source["id"],
                "situation_id": sid,
                "titre": titre_initiative,
                "resume": _texte(doc.get("initiative_resume")) or _texte(doc.get("resume")),
                "statut": "PLANNED",
                "outcome_attendu_ids": [],
            }, mode="DECLARED", cree_le=cree, observe_le=observe, valide_depuis=valide)
        objets.append(_serialiser(initiative, evenement))

    return _ordonner(objets)


def _premier_id(valeur: Any) -> str:
    elements = _liste(valeur)
    if not elements:
        return ""
    premier = elements[0]
    if isinstance(premier, Mapping):
        premier = premier.get("id") or premier.get("situation_id")
    return _texte(premier)


def objets_depuis_case(case: Any, *, tenant_id: Any = None,
                       situation: Any = None, investigation: Any = None,
                       evenement: Mapping[str, Any] | None = None,
                       maintenant: Any = None) -> list[dict[str, Any]]:
    doc = _document(case, "case")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    doc = _verifier_document(doc, tenant, "case")
    cid = _texte(doc.get("id"))
    if not cid:
        raise PontInvalide("case sans id")
    sid = _premier_id(doc.get("situations"))
    if not sid:
        # ADR-0008 : un case sans Situation liée ne produit aucun objet canonique.
        return []
    reference = _instant_reference(evenement, maintenant)

    objets: list[dict[str, Any]] = []
    investigation_pour_decision = investigation
    if situation is not None:
        contexte = objets_depuis_situation(
            situation, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
        # Le case apporte sa propre décision : la situation liée ne sert que d'ancre.
        objets.extend(objet for objet in contexte
                      if objet.get("type") in {"SITUATION", "INVESTIGATION"})
        investigation_pour_decision = next(
            (objet for objet in objets
             if objet.get("type") == "INVESTIGATION"
             and objet.get("id") == investigation_id(sid)),
            None,
        )
    if investigation_pour_decision is None:
        investigation_pour_decision = _investigation_pour_decision(
            tenant, sid, doc, evenement, reference)

    options_case = [element.get("titre") if isinstance(element, Mapping) else element
                    for element in _liste(doc.get("options"))]
    for rang, decision_doc in enumerate(_liste(doc.get("decisions")), 1):
        if isinstance(decision_doc, Mapping):
            texte = decision_doc.get("texte") or decision_doc.get("decision")
            options = decision_doc.get("options") if decision_doc.get("options") is not None else options_case
            acteur = decision_doc.get("par") or doc.get("responsable")
            quand = decision_doc.get("quand") or doc.get("maj_le") or doc.get("cree_le")
            motif = decision_doc.get("motif") or doc.get("objectif")
            type_decision = decision_doc.get("type")
        else:
            texte, options, acteur, quand = decision_doc, options_case, doc.get("responsable"), doc.get("cree_le")
            motif, type_decision = doc.get("objectif"), None
        if not _texte(texte):
            continue
        identifiant = decision_case_id(cid, rang)
        objets.append(_decision_tranchee(
            investigation_pour_decision, texte, options, acteur, quand, motif,
            identifiant, evenement, reference,
            extra_donnees={"case_id": cid, "situation_id": sid,
                           "investigation_id": investigation_id(sid),
                           "decision_type": _texte_legacy(type_decision), "rang": rang},
        ))
    return _ordonner(objets)


def objets_depuis_initiative(initiative: Any, *, tenant_id: Any = None,
                             situation: Any = None, investigation: Any = None,
                             evenement: Mapping[str, Any] | None = None,
                             maintenant: Any = None) -> list[dict[str, Any]]:
    doc = _document(initiative, "initiative")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    doc = _verifier_document(doc, tenant, "initiative")
    iid = _texte(doc.get("id"))
    if not iid:
        raise PontInvalide("initiative sans id")
    reference = _instant_reference(evenement, maintenant)
    statut = _cle(doc.get("statut"))
    reponse = _mapping(doc.get("reponse"))
    choix = _texte_legacy(reponse.get("choix"))
    decision_declaree = _texte_legacy(doc.get("decision_id") or doc.get("decision_ref"))

    acceptee = statut in {"acceptee", "accepte", "suivi", "suivie", "acceptee avec travail"}
    refusee = statut in {"refusee", "refuse", "rejetee", "rejetee"}
    if not acceptee and not refusee:
        return []

    if decision_declaree:
        if not acceptee:
            return []
        cree = _date_depuis(doc, ("cree_le", "quand", "maj_le"), reference)
        observe = _date_depuis(doc, ("observe_le", "quand", "cree_le", "maj_le"), cree)
        valide = _date_depuis(doc, ("valide_depuis", "quand", "cree_le", "maj_le"), observe)
        titre = _titre(doc, iid)
        objets: list[dict[str, Any]] = []
        if situation is not None:
            contexte = objets_depuis_situation(
                situation, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
            objets.extend(objet for objet in contexte
                          if objet.get("type") in {"SITUATION", "INVESTIGATION"})
        initiative_canonique = _objet(
            "INITIATIVE", initiative_id(decision_declaree), tenant, titre, {
                "decision_id": decision_declaree,
                "titre": titre,
                "resume": _texte_legacy(doc.get("raison")) or _titre(doc, iid),
                "statut": "PLANNED",
                "outcome_attendu_ids": [],
                "initiative_source_id": iid,
            }, mode="DECLARED", cree_le=cree, observe_le=observe, valide_depuis=valide)
        objets.append(_serialiser(initiative_canonique, evenement))
        return _ordonner(objets)

    # Garde C0a : sans décision humaine, une proposition `init-*` ne devient pas une Initiative.
    if not choix:
        return []

    objets: list[dict[str, Any]] = []
    investigation_pour_decision = investigation
    sid = _texte(doc.get("situation_id"))
    if situation is not None:
        contexte = objets_depuis_situation(
            situation, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
        # La réponse à une proposition apporte sa propre décision : l'ancre ne la duplique pas.
        objets.extend(objet for objet in contexte
                      if objet.get("type") in {"SITUATION", "INVESTIGATION"})
        if not sid:
            sid = _texte((situation or {}).get("id"))
        investigation_pour_decision = next(
            (objet for objet in objets
             if objet.get("type") == "INVESTIGATION"
             and objet.get("id") == investigation_id(sid)),
            None,
        )
    if investigation_pour_decision is None:
        if not sid:
            return []
        investigation_pour_decision = _investigation_pour_decision(
            tenant, sid, doc, evenement, reference)

    identifiant_decision = decision_initiative_id(iid)
    decision = _decision_tranchee(
        investigation_pour_decision, choix, [choix], reponse.get("par")
        or doc.get("decidee_par"), reponse.get("quand") or doc.get("quand"),
        doc.get("raison"), identifiant_decision, evenement, reference,
        extra_donnees={"initiative_source_id": iid, "situation_id": sid,
                       "decision_source": "initiative"},
    )
    objets.append(decision)

    if acceptee:
        titre = _titre(doc, iid)
        initiative_canonique = _objet(
            "INITIATIVE", initiative_id(decision["id"]), tenant, titre, {
                "decision_id": decision["id"],
                "situation_id": sid,
                "titre": titre,
                "resume": _texte_legacy(doc.get("raison")),
                "statut": "PLANNED",
                "outcome_attendu_ids": [],
                "initiative_source_id": iid,
            }, mode="DECLARED", **_dates(reference))
        objets.append(_serialiser(initiative_canonique, evenement))
    return _ordonner(objets)


def _metrique_mesure(mesure: Any) -> str:
    if isinstance(mesure, Mapping):
        for cle in ("metrique", "metric", "indicateur"):
            texte = _texte(mesure.get(cle))
            if texte:
                return texte
    return ""


def objets_depuis_outcome(payload: Any, *, tenant_id: Any = None,
                          evenement: Mapping[str, Any] | None = None,
                          maintenant: Any = None) -> list[dict[str, Any]]:
    donnees = _mapping(payload)
    tenant = normaliser_tenant(tenant_id)
    initiative = _texte(donnees.get("initiative_id"))
    mesure = donnees.get("mesure")
    if not initiative:
        raise PontInvalide("initiative_id obligatoire pour un Outcome")
    if mesure in (None, "", [], {}):
        raise PontInvalide("mesure obligatoire pour un Outcome")
    reference = _instant_reference(evenement, maintenant)
    metrique = _texte(donnees.get("metrique")) or _metrique_mesure(mesure)
    periode = _texte(donnees.get("periode"))
    identifiant = outcome_id(initiative, metrique, periode)
    outcome = _objet(
        "OUTCOME", identifiant, tenant, metrique or "Outcome", {
            "initiative_id": initiative,
            "titre": metrique or "Outcome",
            "resume": _texte(donnees.get("interpretation")),
            "mesure": mesure,
            "metrique": metrique,
            "valeur_attendue": donnees.get("valeur_attendue"),
            "valeur_observee": _valeur_mesure(mesure),
            "interpretation": _texte(donnees.get("interpretation")),
            "statut": "OBSERVED",
            "periode": periode,
            "mesure_le": _iso(donnees.get("mesure_le"), reference),
        }, mode="OBSERVED", **_dates(reference))
    return [_serialiser(outcome, evenement)]


def objets_depuis_learning(payload: Any, *, tenant_id: Any = None,
                           evenement: Mapping[str, Any] | None = None,
                           maintenant: Any = None) -> list[dict[str, Any]]:
    donnees = _mapping(payload)
    tenant = normaliser_tenant(tenant_id)
    enseignement = _texte(donnees.get("enseignement"))
    if not enseignement:
        raise PontInvalide(
            "enseignement obligatoire : aucune leçon ne peut être déduite d'une mesure")
    source_id = _texte(donnees.get("source_id"))
    if not source_id:
        raise PontInvalide("source_id obligatoire pour un Learning")
    source_type = _texte(donnees.get("source_type")).upper() or "OUTCOME"
    reference = _instant_reference(evenement, maintenant)

    if source_type == "OUTCOME":
        # La mesure est portée par l'Outcome déjà persisté ; ``enregistrer_boucle`` la vérifie.
        outcome_ids = [source_id]
        investigation_ids: list[str] = []
    elif source_type == "INVESTIGATION":
        outcome_ids = []
        investigation_ids = [source_id]
    else:
        raise PontInvalide(f"source de Learning inconnue : {source_type or 'inconnue'}")
    conditions = _textes(donnees.get("conditions_applicabilite"))
    learning = _objet(
        "LEARNING", learning_id(source_id), tenant, enseignement, {
            "titre": enseignement,
            "resume": enseignement,
            "enonce": enseignement,
            "scope": _texte(donnees.get("scope")),
            "outcome_ids": outcome_ids,
            "investigation_ids": investigation_ids,
            "source_outcome_refs": list(outcome_ids),
            "source_investigation_refs": list(investigation_ids),
            "conditions_applicabilite": conditions,
            "statut": "PROPOSED",
            "source_id": source_id,
            "source_type": source_type,
        }, mode="INFERRED", **_dates(reference))
    return [_serialiser(learning, evenement)]


def objets_depuis_objets(payload: Any, *, tenant_id: Any = None,
                         evenement: Mapping[str, Any] | None = None,
                         maintenant: Any = None) -> list[dict[str, Any]]:
    donnees = _mapping(payload)
    objets = donnees.get("objets")
    if not isinstance(objets, (list, tuple)):
        raise PontInvalide("objets : liste attendue")
    tenant = normaliser_tenant(tenant_id)
    resultat: list[dict[str, Any]] = []
    for objet in objets:
        if not isinstance(objet, Mapping):
            raise PontInvalide("objet canonique attendu")
        if _texte(objet.get("tenant_id")) and normaliser_tenant(objet["tenant_id"]) != tenant:
            raise TenantMismatch("objet canonique hors du tenant de l'événement")
        candidat = copy.deepcopy(dict(objet))
        candidat["tenant_id"] = tenant
        resultat.append(_serialiser(candidat, evenement))
    return _ordonner(resultat)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _operation_normalisee(operation: Any) -> str:
    texte = _texte(operation).lower()
    if texte in {OPERATION_SITUATION, "situation.upsert", "situation.mise_a_jour"}:
        return OPERATION_SITUATION
    if texte in {OPERATION_CASE, "case.decision", "case.mise_a_jour"}:
        return OPERATION_CASE
    if texte in {OPERATION_INITIATIVE, "initiative.reponse", "initiative.upsert"}:
        return OPERATION_INITIATIVE
    if texte in {OPERATION_OUTCOME, "outcome.creation", "outcome.maj"}:
        return OPERATION_OUTCOME
    if texte in {OPERATION_LEARNING, "learning.creation", "learning.capitaliser"}:
        return OPERATION_LEARNING
    if texte in {OPERATION_OBJETS, "objets", "canonique.upsert"}:
        return OPERATION_OBJETS
    raise PontInvalide(f"opération de pont inconnue : {operation!r}")


normaliser_operation = _operation_normalisee


def objets_depuis_evenement(evenement: Any, *, tenant_id: Any = None,
                            maintenant: Any = None) -> list[dict[str, Any]]:
    """Construit la liste ordonnée des objets canoniques d'un événement d'outbox."""
    if not isinstance(evenement, Mapping):
        raise PontInvalide("événement attendu")
    tenant = normaliser_tenant(tenant_id or evenement.get("tenant_id"))
    if tenant_id is not None and _texte(evenement.get("tenant_id")):
        if normaliser_tenant(evenement["tenant_id"]) != tenant:
            raise TenantMismatch(
                f"événement du tenant {evenement['tenant_id']!r}, attendu {tenant!r}")
    operation = _operation_normalisee(evenement.get("operation"))
    payload = evenement.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PontInvalide("payload : objet attendu")

    if operation == OPERATION_SITUATION:
        objets = objets_depuis_situation(
            payload.get("situation"), tenant_id=tenant, evenement=evenement,
            maintenant=maintenant)
    elif operation == OPERATION_CASE:
        objets = objets_depuis_case(
            payload.get("case"), tenant_id=tenant, situation=payload.get("situation"),
            investigation=payload.get("investigation"), evenement=evenement,
            maintenant=maintenant)
    elif operation == OPERATION_INITIATIVE:
        objets = objets_depuis_initiative(
            payload.get("initiative"), tenant_id=tenant, situation=payload.get("situation"),
            investigation=payload.get("investigation"), evenement=evenement,
            maintenant=maintenant)
    elif operation == OPERATION_OUTCOME:
        objets = objets_depuis_outcome(
            payload, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
    elif operation == OPERATION_LEARNING:
        objets = objets_depuis_learning(
            payload, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
    else:
        objets = objets_depuis_objets(
            payload, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
    return _ordonner(objets)


construire_objets = objets_depuis_evenement


# ---------------------------------------------------------------------------
# Construction des événements
# ---------------------------------------------------------------------------


def _source_event_id(doc: Mapping[str, Any], explicite: Any = None) -> str:
    return (_texte(explicite) or _texte(doc.get("maj_le")) or _texte(doc.get("cree_le"))
            or _texte(doc.get("quand")) or hash_contenu(doc)[:16])


def construire_evenement(operation: Any, tenant_id: Any, canonical_id: Any, payload: Any, *,
                         source: Mapping[str, Any] | None = None,
                         source_event_id: Any = None,
                         canonical_ids: Iterable[str] | None = None,
                         maintenant: Any = None) -> dict[str, Any]:
    """Construit un document d'outbox complet, avec identifiant et canonical_ids déterministes."""
    tenant = normaliser_tenant(tenant_id)
    operation_texte = _operation_normalisee(operation)
    identifiant = identifiant_evenement(tenant, operation_texte, canonical_id, source_event_id)
    instant = _instant_reference(None, maintenant)
    evenement: dict[str, Any] = {
        "_id": identifiant,
        "tenant_id": tenant,
        "operation": operation_texte,
        "canonical_id": _texte(canonical_id),
        "canonical_ids": [],
        "source_event_id": _iso(source_event_id) or _texte(source_event_id),
        "payload": assainir(payload),
        "source": assainir(source or {}),
        "etat": "pending",
        "tentatives": 0,
        "prochaine_tentative": None,
        "derniere_erreur": None,
        "cree_le": instant,
        "maj_le": instant,
        "locked_until": None,
        "lock_token": None,
        "fencing_token": 0,
    }
    objets = objets_depuis_evenement(evenement, tenant_id=tenant, maintenant=instant)
    if canonical_ids is None:
        evenement["canonical_ids"] = [objet["id"] for objet in objets]
    else:
        evenement["canonical_ids"] = (
            [canonical_ids] if isinstance(canonical_ids, str) else list(canonical_ids))
    evenement["hash"] = hash_contenu(evenement["payload"])
    return evenement


def evenement_depuis_situation(situation: Any, *, tenant_id: Any = None,
                               source_event_id: Any = None,
                               maintenant: Any = None,
                               source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    doc = _document(situation, "situation")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    sid = _texte(doc.get("id"))
    return construire_evenement(
        OPERATION_SITUATION, tenant, sid, {"situation": doc},
        source=source or {"collection": "situations", "id": sid},
        source_event_id=_source_event_id(doc, source_event_id),
        maintenant=maintenant,
    )


def evenement_depuis_case(case: Any, *, tenant_id: Any = None, situation: Any = None,
                          investigation: Any = None, source_event_id: Any = None,
                          maintenant: Any = None,
                          source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    doc = _document(case, "case")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    cid = _texte(doc.get("id"))
    payload: dict[str, Any] = {"case": doc}
    if situation is not None:
        payload["situation"] = situation
    if investigation is not None:
        payload["investigation"] = investigation
    return construire_evenement(
        OPERATION_CASE, tenant, cid, payload,
        source=source or {"collection": "cases", "id": cid},
        source_event_id=_source_event_id(doc, source_event_id),
        maintenant=maintenant,
    )


def evenement_depuis_initiative(initiative: Any, *, tenant_id: Any = None,
                                situation: Any = None, investigation: Any = None,
                                source_event_id: Any = None, maintenant: Any = None,
                                source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    doc = _document(initiative, "initiative")
    tenant = normaliser_tenant(tenant_id or doc.get("tenant_id"))
    iid = _texte(doc.get("id"))
    payload: dict[str, Any] = {"initiative": doc}
    if situation is not None:
        payload["situation"] = situation
    if investigation is not None:
        payload["investigation"] = investigation
    return construire_evenement(
        OPERATION_INITIATIVE, tenant, iid, payload,
        source=source or {"collection": "initiatives", "id": iid},
        source_event_id=_source_event_id(doc, source_event_id),
        maintenant=maintenant,
    )


def evenement_outcome(*, tenant_id: Any, initiative_id: Any, mesure: Any,
                      metrique: Any = None, periode: Any = "",
                      valeur_attendue: Any = None, interpretation: Any = None,
                      mesure_le: Any = None, decision_id: Any = None,
                      source_event_id: Any = None, maintenant: Any = None,
                      source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tenant = normaliser_tenant(tenant_id)
    metrique_finale = _texte(metrique) or _metrique_mesure(mesure)
    identifiant = outcome_id(initiative_id, metrique_finale, periode)
    payload = {
        "initiative_id": _texte(initiative_id),
        "mesure": mesure,
        "metrique": metrique_finale,
        "periode": _texte(periode),
        "valeur_attendue": valeur_attendue,
        "interpretation": interpretation,
        "mesure_le": mesure_le,
        "decision_id": decision_id,
    }
    return construire_evenement(
        OPERATION_OUTCOME, tenant, identifiant, payload,
        source=source or {"collection": "pont", "id": identifiant},
        source_event_id=source_event_id or hash_contenu(payload)[:16],
        maintenant=maintenant,
    )


def evenement_learning(*, tenant_id: Any, source_id: Any, enseignement: Any,
                       source_type: Any = "OUTCOME", mesure: Any = None,
                       initiative_id: Any = None, situation_id: Any = None,
                       scope: Any = "", conditions_applicabilite: Any = (),
                       source_event_id: Any = None, maintenant: Any = None,
                       source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tenant = normaliser_tenant(tenant_id)
    if not _texte(enseignement):
        raise PontInvalide(
            "enseignement obligatoire : aucune leçon ne peut être déduite d'une mesure")
    identifiant = learning_id(source_id)
    payload = {
        "source_id": _texte(source_id),
        "source_type": _texte(source_type).upper() or "OUTCOME",
        "enseignement": _texte(enseignement),
        "initiative_id": initiative_id,
        "situation_id": situation_id,
        "scope": _texte(scope),
        "conditions_applicabilite": list(_liste(conditions_applicabilite)),
    }
    if mesure is not None:
        payload["mesure"] = mesure
    return construire_evenement(
        OPERATION_LEARNING, tenant, identifiant, payload,
        source=source or {"collection": "pont", "id": identifiant},
        source_event_id=source_event_id or hash_contenu(payload)[:16],
        maintenant=maintenant,
    )


# Alias courts, utiles aux routes C2/C3 et aux lecteurs du contrat outbox.
evenement_situation = evenement_depuis_situation
evenement_case = evenement_depuis_case
evenement_initiative = evenement_depuis_initiative
mapper_situation = objets_depuis_situation
mapper_case = objets_depuis_case
mapper_initiative = objets_depuis_initiative
mapper_outcome = objets_depuis_outcome
mapper_learning = objets_depuis_learning
