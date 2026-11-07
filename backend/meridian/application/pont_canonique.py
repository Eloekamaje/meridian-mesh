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
from dataclasses import asdict
from datetime import date, datetime, timezone
import copy
import hashlib
import re
import unicodedata
from typing import Any

from meridian.application import mapping_legacy as mapping
from meridian.application import pont_securite as securite
from meridian.domain import modele_entreprise as modele
from meridian.domain.tenant import TenantError, normaliser_slug

__all__ = [
    "ConflitCanonique",
    "ETATS",
    "OPERATION_CASE",
    "PONT_KEY_ENV",
    "OPERATION_INITIATIVE",
    "OPERATION_LEARNING",
    "OPERATION_OBJETS",
    "OPERATION_OUTCOME",
    "OPERATION_SITUATION",
    "OPERATIONS",
    "ORIGINE_EXPLOITATION",
    "ORIGINE_LEGACY",
    "PONT_KEY_INTERNE_ENV",
    "PontInvalide",
    "SignatureInvalide",
    "TenantMismatch",
    "assainir",
    "backoff_secondes",
    "cle_idempotence",
    "cle_pour_evenement",
    "cle_sensible",
    "collection_attendue",
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
    "signature",
    "signer_evenement",
    "source_maj_le",
    "statut_canonique",
    "statut_initiative_canonique",
    "valider_tenant",
    "verifier_evenement",
    "verifier_source_evenement",
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
ETATS = ("pending", "done", "failed", "dead")
ORIGINE_LEGACY = "legacy"
ORIGINE_MIGRATION = "migration"
ORIGINE_EXPLOITATION = "exploitation"
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

# Champs legacy recopiés dans `donnees` : liste fermée, partagée avec la migration.
_CHAMPS_SITUATION = mapping.CHAMPS_SITUATION
_CHAMPS_CASE = (
    "objectif", "resume", "prochaine_etape", "type", "genre", "num", "responsable",
    "sensibilite", "portee", "origine", "veille",
)
_CHAMPS_INITIATIVE = mapping.CHAMPS_INITIATIVE


class PontInvalide(ValueError):
    """Un événement ou un objet ne peut pas être construit sans inventer de sémantique."""


class TenantMismatch(PontInvalide):
    """Le document legacy n'appartient pas au tenant de l'événement."""


class ConflitCanonique(PontInvalide):
    """Un identifiant canonique existe déjà avec une origine non légacy : on n'écrase pas."""


class SignatureInvalide(PontInvalide):
    """Signature HMAC absente ou invalide : l'événement n'est pas authentifié."""


PONT_KEY_ENV = securite.PONT_KEY_ENV
PONT_KEY_INTERNE_ENV = securite.PONT_KEY_INTERNE_ENV
cle_sensible = securite.cle_sensible


def assainir(valeur: Any) -> Any:
    try:
        return securite.assainir(valeur)
    except ValueError as exc:
        raise PontInvalide(str(exc)) from exc


def hash_contenu(valeur: Any) -> str:
    try:
        return securite.hash_contenu(valeur)
    except ValueError as exc:
        raise PontInvalide(str(exc)) from exc


def signer_evenement(evenement: Mapping[str, Any], cle: Any = None) -> dict[str, Any]:
    try:
        return securite.signer_evenement(evenement, cle)
    except securite.SignatureInvalide as exc:
        raise SignatureInvalide(str(exc)) from exc
    except ValueError as exc:
        raise SignatureInvalide(f"événement non signable : {exc}") from exc


def verifier_evenement(evenement: Mapping[str, Any], cle: Any = None) -> dict[str, Any]:
    try:
        return securite.verifier_evenement(evenement, cle)
    except securite.SignatureInvalide as exc:
        raise SignatureInvalide(str(exc)) from exc
    except ValueError as exc:
        raise SignatureInvalide(f"événement non vérifiable : {exc}") from exc


def signature(evenement: Mapping[str, Any], cle: Any = None) -> str:
    try:
        return securite.signature(evenement, cle)
    except securite.SignatureInvalide as exc:
        raise SignatureInvalide(str(exc)) from exc


def cle_pont(cle: Any = None) -> str:
    try:
        return securite.charger_cle(cle)
    except securite.SignatureInvalide as exc:
        raise SignatureInvalide(str(exc)) from exc


def cle_interne(cle: Any = None) -> str:
    try:
        return securite.charger_cle_interne(cle)
    except securite.SignatureInvalide as exc:
        raise SignatureInvalide(str(exc)) from exc


def cle_pour_evenement(evenement: Mapping[str, Any], cle_legacy: Any = None,
                       cle_interne_: Any = None) -> str:
    """Clé attendue selon l'opération : interne pour `objets.upsert`, legacy sinon."""
    try:
        operation = _operation_normalisee(evenement.get("operation"))
    except PontInvalide:
        # L'opération inconnue sera refusée par la validation de provenance ; la
        # pré-vérification de signature ne doit pas masquer ce diagnostic.
        return cle_pont(cle_legacy)
    return (cle_interne(cle_interne_) if operation == OPERATION_OBJETS
            else cle_pont(cle_legacy))


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
    return mapping.cle(valeur)


def normaliser_tenant(tenant_id: Any) -> str:
    """Valide et canonise le tenant ; ne fabrique jamais de tenant par défaut."""
    if tenant_id is None or not _texte(tenant_id):
        raise PontInvalide("tenant_id obligatoire")
    try:
        return normaliser_slug(tenant_id)
    except TenantError as exc:
        raise PontInvalide(str(exc)) from exc


valider_tenant = normaliser_tenant


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


def _est_futur(valeur: Any, reference: Any, tolerance_secondes: int = 300) -> bool:
    """Vrai si une date source dépasse la référence au-delà de la tolérance de clock skew."""
    gauche = _iso(valeur)
    droite = _iso(reference)
    if not gauche or not droite:
        return False
    try:
        return (datetime.fromisoformat(gauche.replace("Z", "+00:00")).timestamp()
                > datetime.fromisoformat(droite.replace("Z", "+00:00")).timestamp()
                + int(tolerance_secondes))
    except ValueError:
        return False


def backoff_secondes(tentatives: Any, *, base: int = 5, maximum: int = 3600,
                     jitter: float = 0.0) -> int:
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
    delai = min(int(maximum), int(base) * (2 ** (nombre - 1)))
    if jitter:
        import random
        amplitude = min(0.5, max(0.0, float(jitter)))
        delai = int(delai * (1.0 + random.uniform(-amplitude, amplitude)))
    return max(1, min(int(maximum), delai))


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


def outcome_id(initiative_id_: Any, metrique: Any, periode: Any = "",
               mesure_le: Any = None, empreinte: Any = None) -> str:
    if _texte(periode):
        suffixe = _slug_identifiant(periode, "sans-periode")
    else:
        # Sans période, deux mesures de la même métrique ne doivent pas partager le même ID.
        suffixe = ("sans-periode-" + _slug_identifiant(
            _texte(mesure_le) or _texte(empreinte) or "na"))
    return (f"out-{_texte(initiative_id_)}-{_slug_identifiant(metrique, 'metrique')}-"
            f"{suffixe}")


def learning_id(source_id: Any) -> str:
    return f"lea-{_texte(source_id)}"


# ---------------------------------------------------------------------------
# Statuts, priorités, dates
# ---------------------------------------------------------------------------

def statut_canonique(valeur: Any) -> str:
    """Traduit un statut de situation legacy vers le vocabulaire canonique partagé."""
    return mapping.statut_situation(valeur)


def statut_initiative_canonique(valeur: Any) -> str:
    """Traduit un statut d'initiative legacy vers le vocabulaire canonique partagé."""
    return mapping.statut_initiative(valeur)


def priorite_canonique(valeur: Any) -> str:
    return mapping.priorite(valeur)


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
                type_attendu: str | None = None, source_maj_le: Any = None,
                origine: str = ORIGINE_LEGACY,
                source_objet: Mapping[str, Any] | None = None) -> dict[str, Any]:
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

    source_maj = (_iso(source_maj_le)
                  or _iso((evenement or {}).get("source_maj_le"))
                  or _iso((evenement or {}).get("cree_le")))
    reference = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if source_maj and _est_futur(source_maj, reference):
        raise PontInvalide(
            f"source_maj_le {source_maj!r} dans le futur par rapport à {reference!r}")
    payload["donnees"]["_pont"] = {
        "hash": hash_contenu(payload),
        "origine": _texte(origine) or ORIGINE_LEGACY,
        "event_id": _texte((evenement or {}).get("_id")),
        "operation": _texte((evenement or {}).get("operation")),
        "source_maj_le": source_maj,
        "source": assainir(source_objet or (evenement or {}).get("source") or {}),
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


_STATUTS_DECISION_PROPOSEE = frozenset({
    "proposee", "propose", "proposed", "en attente", "a trancher", "a decider",
    "en examen", "pending",
})
_STATUTS_DECISION_TRANCHEE = frozenset({
    "decidee", "decide", "decided", "tranchee", "tranche", "arbitree", "arbitrage",
})


def _decision_tranchee(investigation: Any, texte_decision: Any, options: Any, acteur: Any,
                       decide_le: Any, rationale: Any, identifiant: str,
                       evenement: Mapping[str, Any] | None, reference: str,
                       extra_donnees: Mapping[str, Any] | None = None,
                       source_maj_le: Any = None,
                       statut_decision: Any = None,
                       source_objet: Mapping[str, Any] | None = None) -> dict[str, Any]:
    texte = _texte_legacy(texte_decision)
    acteur_texte = _texte_legacy(acteur)
    statut_brut = _cle(statut_decision)
    explicitement_proposee = statut_brut in _STATUTS_DECISION_PROPOSEE
    explicitement_tranchee = statut_brut in _STATUTS_DECISION_TRANCHEE
    choix_absent = not texte
    # Sans acteur humain ou sans choix explicite, la décision reste PROPOSED.
    proposee = explicitement_proposee or not acteur_texte or choix_absent
    if explicitement_tranchee and not acteur_texte:
        proposee = True
    if not texte and not _textes(options):
        raise PontInvalide("décision sans texte ni option")
    if not texte:
        texte = _textes(options)[0]
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
        "statut": "PROPOSED" if proposee else "DECIDED",
        "acteur": None if proposee else acteur_texte,
        "choix": None if proposee else texte,
        "decide_le": None if proposee else _iso(decide_le, reference),
        "rationale": _texte_legacy(rationale),
        "statut_legacy": _texte_legacy(statut_decision),
    }
    donnees.update(extra_donnees or {})
    donnees["options"] = options_normalisees
    donnees["choix_hors_options"] = bool(hors_options and not proposee)
    decision = _objet("DECISION", identifiant, tenant, titre, donnees,
                      mode="DECLARED", **_dates(reference))
    return _serialiser(decision, evenement, source_maj_le=source_maj_le,
                       source_objet=source_objet)


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
                if _texte_legacy(texte) or _textes(element.get("options")):
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
            "statut": doc.get("statut"),
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
    source_maj = _date_depuis(doc, ("maj_le", "cree_le", "detectee", "observe_le"), reference)
    source_situation = {"collection": "situations", "id": sid,
                        "hash": hash_contenu(doc)}
    titre = _titre(doc, sid)
    description_explicite = _texte_legacy(doc.get("description"))
    description = (description_explicite or _texte_legacy(doc.get("resume"))
                   or _texte_legacy(doc.get("decouverte_quoi"))
                   or _texte_legacy(doc.get("question")) or titre)

    statut = statut_canonique(doc.get("statut"))
    priorite = priorite_canonique(doc.get("priorite"))
    twin_ids = _ids(doc.get("twin_ids") if doc.get("twin_ids") is not None else doc.get("jumeaux"))
    resume = _texte_legacy(doc.get("resume")) or description
    donnees_situation = {"titre": titre, "resume": resume}
    if doc.get("statut") is not None:
        donnees_situation["statut"] = statut
    if doc.get("priorite") is not None:
        donnees_situation["priorite"] = priorite
    source_twins = doc.get("twin_ids") if doc.get("twin_ids") is not None else doc.get("jumeaux")
    if source_twins is not None:
        donnees_situation["twin_ids"] = twin_ids
    for champ, source in (("signal_ids", "signal_ids"), ("claim_ids", "claim_ids"),
                          ("opportunite_ids", "opportunite_ids"), ("risk_ids", "risk_ids"),
                          ("inconnues", "reste_a_comprendre")):
        if doc.get(source) is not None:
            donnees_situation[champ] = (_textes(doc.get(source)) if champ == "inconnues"
                                        else _ids(doc.get(source)))
    donnees_situation.update(_copier_champs(doc, _CHAMPS_SITUATION))
    # Les champs dérivés sont reposés après la copie : un `resume`/`description` legacy
    # non scalaire ne doit jamais remplacer la valeur texte calculée.
    donnees_situation["resume"] = resume
    question_explicite = _texte_legacy(doc.get("question"))
    if question_explicite:
        donnees_situation["question"] = question_explicite
    else:
        donnees_situation.pop("question", None)
    if description_explicite:
        donnees_situation["description"] = description_explicite
    else:
        donnees_situation.pop("description", None)
    if doc.get("statut") is not None:
        donnees_situation["statut_legacy"] = _texte(doc.get("statut"))
    if doc.get("priorite") is not None:
        donnees_situation["priorite_legacy"] = _texte(doc.get("priorite"))
    if source_twins is not None:
        donnees_situation["jumeaux"] = list(twin_ids)
    situation_canonique = _objet(
        "SITUATION", sid, tenant, titre, donnees_situation, mode="DECLARED",
        cree_le=cree, observe_le=observe, valide_depuis=valide)
    objets = [_serialiser(situation_canonique, evenement, source_maj_le=source_maj,
                          source_objet=source_situation)]

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
    objets.append(_serialiser(investigation, evenement, source_maj_le=source_maj,
                              source_objet=source_situation))

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
            source_maj_le=source_maj,
            statut_decision=decision_doc.get("statut") or decision_doc.get("etat"),
            source_objet=source_situation,
        )
        objets.append(decision)
        decisions.append(decision)

    decision_finale = decisions[-1] if decisions else None
    if (_cle(doc.get("statut")) == "poursuivie" and decision_finale
            and (decision_finale.get("donnees") or {}).get("statut") == "DECIDED"):
        decision_source = decision_finale
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
        objets.append(_serialiser(initiative, evenement, source_maj_le=source_maj,
                                  source_objet=source_situation))

    return _ordonner(objets)


def _exiger_snapshot_complet(situation: Any) -> dict[str, Any]:
    """Un snapshot embarqué doit être complet : pas de titre=id/statut=CANDIDATE par défaut."""
    doc = _document(situation, "situation")
    manquants = [champ for champ in ("titre", "statut", "priorite")
                 if not _texte_legacy(doc.get(champ))]
    if manquants:
        raise PontInvalide(
            f"snapshot de situation incomplet (manquants : {', '.join(manquants)})")
    return doc


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
    source_maj = _date_depuis(doc, ("maj_le", "cree_le"), reference)
    source_case = {"collection": "cases", "id": cid, "hash": hash_contenu(doc)}

    objets: list[dict[str, Any]] = []
    investigation_pour_decision = investigation
    if situation is not None:
        snapshot = _exiger_snapshot_complet(situation)
        if _texte(snapshot.get("id")) != sid:
            raise PontInvalide(
                f"snapshot de situation {snapshot.get('id')!r} incompatible avec situations[0] {sid!r}")
        contexte = objets_depuis_situation(
            snapshot, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
        # Le case apporte sa propre décision : la situation liée ne sert que d'ancre.
        objets.extend(objet for objet in contexte
                      if objet.get("type") in {"SITUATION", "INVESTIGATION"})
        investigation_pour_decision = next(
            (objet for objet in objets
             if objet.get("type") == "INVESTIGATION"
             and objet.get("id") == investigation_id(sid)),
            None,
        )
    if isinstance(investigation, Mapping):
        if _texte(investigation.get("id")) != investigation_id(sid):
            raise PontInvalide(
                f"investigation {investigation.get('id')!r} incompatible avec inv-{sid}")
        if _texte(investigation.get("situation_id")) not in ("", sid):
            raise PontInvalide("investigation liée à une autre situation")
    if investigation_pour_decision is None and situation is None:
        raise PontInvalide(
            "case avec situation liée sans snapshot de Situation ni Investigation : "
            "enqueue la Situation avant le case")

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
            statut_decision = decision_doc.get("statut") or decision_doc.get("etat")
        else:
            texte, options, acteur, quand = decision_doc, options_case, doc.get("responsable"), doc.get("cree_le")
            motif, type_decision, statut_decision = doc.get("objectif"), None, None
        if not _texte_legacy(texte) and not _textes(options):
            continue
        identifiant = decision_case_id(cid, rang)
        objets.append(_decision_tranchee(
            investigation_pour_decision, texte, options, acteur, quand, motif,
            identifiant, evenement, reference,
            extra_donnees={"case_id": cid, "situation_id": sid,
                           "investigation_id": investigation_id(sid),
                           "decision_type": _texte_legacy(type_decision), "rang": rang},
            source_maj_le=source_maj,
            statut_decision=statut_decision,
            source_objet=source_case,
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

    acceptee = statut in {"acceptee", "accepte", "suivi", "suivie",
                          "acceptee avec travail"}
    refusee = statut in {"refusee", "refuse", "rejetee", "rejete"}
    if not acceptee and not refusee:
        return []

    source_maj = _date_depuis(doc, ("maj_le", "quand", "cree_le"), reference)
    source_initiative = {"collection": "initiatives", "id": iid,
                         "hash": hash_contenu(doc)}
    sid = _texte(doc.get("situation_id"))

    if decision_declaree:
        if not acceptee:
            return []
        if situation is not None:
            snapshot = _exiger_snapshot_complet(situation)
            if sid and _texte(snapshot.get("id")) != sid:
                raise PontInvalide(
                    f"snapshot de situation incompatible avec situation_id {sid!r}")
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
        objets.append(_serialiser(initiative_canonique, evenement,
                                  source_maj_le=source_maj,
                                  source_objet=source_initiative))
        return _ordonner(objets)

    # Garde C0a : sans décision humaine, une proposition `init-*` ne devient pas une Initiative.
    if not choix:
        return []

    objets: list[dict[str, Any]] = []
    investigation_pour_decision = investigation
    if situation is not None:
        snapshot = _exiger_snapshot_complet(situation)
        if not sid:
            sid = _texte(snapshot.get("id"))
        if _texte(snapshot.get("id")) != sid:
            raise PontInvalide(
                f"snapshot de situation {snapshot.get('id')!r} incompatible avec {sid!r}")
        contexte = objets_depuis_situation(
            snapshot, tenant_id=tenant, evenement=evenement, maintenant=maintenant)
        # La réponse à une proposition apporte sa propre décision : l'ancre ne la duplique pas.
        objets.extend(objet for objet in contexte
                      if objet.get("type") in {"SITUATION", "INVESTIGATION"})
        investigation_pour_decision = next(
            (objet for objet in objets
             if objet.get("type") == "INVESTIGATION"
             and objet.get("id") == investigation_id(sid)),
            None,
        )
    if isinstance(investigation, Mapping):
        if _texte(investigation.get("id")) != investigation_id(sid):
            raise PontInvalide(
                f"investigation {investigation.get('id')!r} incompatible avec inv-{sid}")
        if _texte(investigation.get("situation_id")) not in ("", sid):
            raise PontInvalide("investigation liée à une autre situation")
    if investigation_pour_decision is None and situation is None:
        raise PontInvalide(
            "réponse d'initiative sans snapshot de Situation ni Investigation : "
            "enqueue la Situation avant l'initiative")
    if investigation_pour_decision is None:
        if not sid:
            raise PontInvalide("initiative sans situation_id ni snapshot")
        investigation_pour_decision = _investigation_pour_decision(
            tenant, sid, doc, evenement, reference)

    identifiant_decision = decision_initiative_id(iid)
    decision = _decision_tranchee(
        investigation_pour_decision, choix, [choix], reponse.get("par")
        or doc.get("decidee_par"), reponse.get("quand") or doc.get("quand"),
        doc.get("raison"), identifiant_decision, evenement, reference,
        extra_donnees={"initiative_source_id": iid, "situation_id": sid,
                       "decision_source": "initiative"},
        source_maj_le=source_maj,
        statut_decision="decidee",
        source_objet=source_initiative,
    )
    objets.append(decision)

    if acceptee and (decision.get("donnees") or {}).get("statut") == "DECIDED":
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
        objets.append(_serialiser(initiative_canonique, evenement,
                                  source_maj_le=source_maj,
                                  source_objet=source_initiative))
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
    if isinstance(mesure, bool) or mesure in (None, "", [], {}):
        raise PontInvalide("mesure obligatoire pour un Outcome (booléen refusé)")
    reference = _instant_reference(evenement, maintenant)
    metrique = _texte(donnees.get("metrique")) or _metrique_mesure(mesure)
    periode = _texte(donnees.get("periode"))
    mesure_le = _iso(donnees.get("mesure_le"))
    identifiant = outcome_id(initiative, metrique, periode, mesure_le=mesure_le,
                             empreinte=hash_contenu(mesure)[:8])
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
    return [_serialiser(outcome, evenement,
                        source_maj_le=mesure_le or (evenement or {}).get("source_maj_le"),
                        source_objet=(evenement or {}).get("source"))]


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
            "situation_id": _texte(donnees.get("situation_id")) or None,
            "initiative_id": _texte(donnees.get("initiative_id")) or None,
        }, mode="INFERRED", **_dates(reference))
    return [_serialiser(learning, evenement,
                        source_maj_le=(evenement or {}).get("source_maj_le"),
                        source_objet=(evenement or {}).get("source"))]


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
        # Le producteur ne fixe jamais l'ordre : la date de référence vient de l'événement.
        source_maj = (evenement or {}).get("source_maj_le")
        source_objet = (evenement or {}).get("source")
        resultat.append(_serialiser(candidat, evenement, source_maj_le=source_maj,
                                    source_objet=source_objet))
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


def _maj_doc(doc: Any, defaut: str) -> str:
    if not isinstance(doc, Mapping):
        return defaut
    return _date_depuis(
        doc, ("maj_le", "cree_le", "detectee", "observe_le", "quand", "decidee_le",
              "mesure_le"), defaut)


def _source_maj_le(operation: str, payload: Mapping[str, Any],
                   source_event_id: Any, defaut: str) -> str:
    if operation == OPERATION_SITUATION:
        doc = payload.get("situation")
    elif operation == OPERATION_CASE:
        doc = payload.get("case")
    elif operation == OPERATION_INITIATIVE:
        doc = payload.get("initiative")
    elif operation == OPERATION_OUTCOME:
        doc = payload
    else:
        doc = {}
    return _maj_doc(doc, _iso(source_event_id) or defaut)


def verifier_source_evenement(evenement: Mapping[str, Any]) -> None:
    """Vérifie identifiant, provenance, ordre source et restriction du producteur interne."""
    operation = _operation_normalisee(evenement.get("operation"))
    tenant = normaliser_tenant(evenement.get("tenant_id"))
    canonical_id = _texte(evenement.get("canonical_id"))
    identifiant = _texte(evenement.get("_id"))
    attendu = identifiant_evenement(
        tenant, operation, canonical_id, evenement.get("source_event_id"))
    if not identifiant or identifiant != attendu:
        raise PontInvalide(
            f"_id {identifiant!r} non conforme à la clé d'idempotence {attendu!r}")
    source_maj = _iso(evenement.get("source_maj_le"))
    if not source_maj:
        raise PontInvalide("source_maj_le obligatoire et ISO")
    if _est_futur(source_maj, datetime.now(timezone.utc).isoformat(timespec="seconds")):
        raise PontInvalide(f"source_maj_le {source_maj!r} dans le futur")
    payload = evenement.get("payload")
    if not isinstance(payload, Mapping):
        raise PontInvalide("payload : objet attendu")
    principal = _identifiant_principal(operation, payload)
    if principal is not None and principal != canonical_id:
        raise PontInvalide(
            f"canonical_id {canonical_id!r} incohérent avec l'id principal {principal!r}")
    if operation in {OPERATION_OBJETS, OPERATION_OUTCOME, OPERATION_LEARNING}:
        ids = {objet["id"] for objet in objets_depuis_evenement(
            evenement, tenant_id=tenant)}
        if canonical_id not in ids:
            raise PontInvalide(
                f"canonical_id {canonical_id!r} absent des objets construits "
                f"{sorted(ids)!r}")
    source = evenement.get("source")
    if not isinstance(source, Mapping):
        raise PontInvalide("source obligatoire")
    collection = _texte(source.get("collection"))
    attendue = _collection_attendue(operation)
    if collection != attendue:
        raise PontInvalide(
            f"source.collection {collection!r} inattendue pour {operation} "
            f"(attendu {attendue!r})")
    if _texte(source.get("id")) != canonical_id:
        raise PontInvalide(
            f"source.id {source.get('id')!r} incohérent avec canonical_id {canonical_id!r}")
    empreinte = hash_contenu(evenement.get("payload"))
    if _texte(source.get("hash")) != empreinte:
        raise PontInvalide("source.hash ne correspond pas au payload")
    if _texte(evenement.get("hash")) and _texte(evenement.get("hash")) != empreinte:
        raise PontInvalide("hash d'événement divergent du payload")
    if operation == OPERATION_OBJETS and not bool(source.get("interne")):
        raise PontInvalide("objets.upsert exige source.interne=true")


def _identifiant_principal(operation: str, payload: Mapping[str, Any]) -> str | None:
    cle = {
        OPERATION_SITUATION: "situation",
        OPERATION_CASE: "case",
        OPERATION_INITIATIVE: "initiative",
    }.get(operation)
    if not cle:
        return None
    document = payload.get(cle)
    return _texte(document.get("id")) if isinstance(document, Mapping) else ""


def _collection_attendue(operation: str) -> str:
    return {
        OPERATION_SITUATION: "situations",
        OPERATION_CASE: "cases",
        OPERATION_INITIATIVE: "initiatives",
        OPERATION_OUTCOME: "pont",
        OPERATION_LEARNING: "pont",
        OPERATION_OBJETS: "pont_interne",
    }[operation]


collection_attendue = _collection_attendue
source_maj_le = _source_maj_le


def construire_evenement(operation: Any, tenant_id: Any, canonical_id: Any, payload: Any, *,
                         source: Mapping[str, Any] | None = None,
                         source_event_id: Any = None,
                         canonical_ids: Iterable[str] | None = None,
                         maintenant: Any = None) -> dict[str, Any]:
    """Construit un document d'outbox signé, avec identifiant et canonical_ids déterministes."""
    tenant = normaliser_tenant(tenant_id)
    operation_texte = _operation_normalisee(operation)
    identifiant = identifiant_evenement(tenant, operation_texte, canonical_id, source_event_id)
    instant = _instant_reference(None, maintenant)
    payload_assaini = assainir(payload)
    if not isinstance(payload_assaini, Mapping):
        raise PontInvalide("payload : objet attendu")
    source_final = dict(assainir(source or {}))
    collection = _texte(source_final.get("collection")) or _collection_attendue(operation_texte)
    if operation_texte == OPERATION_OBJETS:
        if collection != "pont_interne" or not bool(source_final.get("interne")):
            raise PontInvalide(
                "objets.upsert est réservé au producteur interne "
                "(source.collection=pont_interne, source.interne=true)")
    principal = _identifiant_principal(operation_texte, payload_assaini)
    if principal is not None and principal != _texte(canonical_id):
        raise PontInvalide(
            f"canonical_id {canonical_id!r} incohérent avec l'id principal {principal!r}")
    source_final["collection"] = collection
    source_final["id"] = _texte(source_final.get("id")) or _texte(canonical_id)
    source_final["hash"] = hash_contenu(payload_assaini)
    source_maj_le = _source_maj_le(operation_texte, payload_assaini,
                                   source_event_id, instant)
    source_final["source_maj_le"] = source_maj_le
    evenement: dict[str, Any] = {
        "_id": identifiant,
        "tenant_id": tenant,
        "operation": operation_texte,
        "canonical_id": _texte(canonical_id),
        "canonical_ids": [],
        "source_event_id": _iso(source_event_id) or _texte(source_event_id),
        "source_maj_le": source_maj_le,
        "payload": payload_assaini,
        "source": source_final,
        "etat": "pending",
        "tentatives": 0,
        "disponible_le": instant,
        "prochaine_tentative": None,
        "derniere_erreur": None,
        "cree_le": instant,
        "maj_le": instant,
        "locked_until": None,
        "lock_token": None,
        "fencing_token": 0,
    }
    objets = objets_depuis_evenement(evenement, tenant_id=tenant, maintenant=instant)
    ids = [objet["id"] for objet in objets]
    if operation_texte in {OPERATION_OBJETS, OPERATION_SITUATION, OPERATION_OUTCOME,
                           OPERATION_LEARNING} and _texte(canonical_id) not in ids:
        raise PontInvalide(
            f"canonical_id {canonical_id!r} absent des objets construits {ids!r}")
    if canonical_ids is None:
        evenement["canonical_ids"] = ids
    else:
        evenement["canonical_ids"] = (
            [canonical_ids] if isinstance(canonical_ids, str) else list(canonical_ids))
    evenement["hash"] = hash_contenu(evenement["payload"])
    cle_signature = (cle_interne() if operation_texte == OPERATION_OBJETS else None)
    return signer_evenement(evenement, cle_signature)


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
    if isinstance(mesure, bool):
        raise PontInvalide("mesure booléenne refusée")
    metrique_finale = _texte(metrique) or _metrique_mesure(mesure)
    mesure_le_iso = _iso(mesure_le)
    identifiant = outcome_id(
        initiative_id, metrique_finale, periode,
        mesure_le=mesure_le_iso, empreinte=hash_contenu(mesure)[:8])
    payload = {
        "initiative_id": _texte(initiative_id),
        "mesure": mesure,
        "metrique": metrique_finale,
        "periode": _texte(periode),
        "valeur_attendue": valeur_attendue,
        "interpretation": interpretation,
        "mesure_le": mesure_le_iso,
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
