"""Pont Travail → canonique C2 : décisions pures et lecture de la trace.

Ce module ne lit ni Mongo ni Postgres. Il construit les événements d'outbox à partir des
documents legacy déjà écrits, choisit l'objet canonique courant d'un Travail et met la
chaîne canonique au format du contrat UI.

Règles structurantes :

- ADR-0008 : un `case` n'est pas un objet canonique. Seul le case dont `situations[0]`
  référence la Situation traitée peut produire des objets ; un case sans Situation liée
  ne produit rien.
- l'identifiant canonique d'une Situation est son identifiant Mongo (`sid`). C1 utilise
  déjà cette correspondance déterministe (`objets_depuis_situation`, `investigation_id`) :
  aucune table de correspondance n'est nécessaire.
- les clés d'idempotence des événements de Situation reposent sur la version écrite
  (`maj_le` / `decidee_le`) : un rejeu ne change pas cette version et réutilise le même
  `_id` d'outbox ; une nouvelle transition produit une nouvelle version et un nouvel `_id`.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import os
from typing import Any

from meridian.application import pont_canonique as pont

__all__ = [
    "ADOPTION_ENV",
    "LEGACY_TENANT_ENV",
    "candidat_boucle",
    "candidats_boucle",
    "evenement_action_situation",
    "evenement_case_lie",
    "evenement_decision_situation",
    "extraire_boucle",
    "filtre_tenant",
    "normaliser_tenant",
    "situation_liee",
]

ADOPTION_ENV = "JUMEAU_LEGACY_TENANT_ADOPTION"
LEGACY_TENANT_ENV = "JUMEAU_LEGACY_TENANT"
_VALEURS_ACTIVES = frozenset({"1", "true", "vrai", "oui", "yes", "on"})
_CHAMPS_DATE = ("maj_le", "cree_le", "detectee", "observe_le", "quand",
                "decidee_le", "mesure_le")


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def normaliser_tenant(tenant_id: Any) -> str:
    """Valide et canonise un tenant via l'autorité unique du domaine."""
    return pont.normaliser_tenant(tenant_id)


def _tenant_aliases(tenant: str) -> list[str]:
    return ["local", "demo"] if tenant == "local" else [tenant]


def _adoption_active(tenant: str) -> bool:
    flag = str(os.environ.get(ADOPTION_ENV) or "").strip().lower()
    legacy = str(os.environ.get(LEGACY_TENANT_ENV) or "").strip()
    if flag not in _VALEURS_ACTIVES or not legacy:
        return False
    try:
        return normaliser_tenant(legacy) == tenant
    except pont.PontInvalide:
        return False


def filtre_tenant(tenant_id: Any, *, adoption: bool | None = None) -> dict[str, Any]:
    """Filtre Mongo strict par tenant.

    Par défaut un document sans ``tenant_id`` n'est visible par personne. L'adoption des
    documents legacy non estampillés est opt-in et réservée au tenant de reprise configuré
    par ``JUMEAU_LEGACY_TENANT`` ; un second tenant ne les voit jamais.
    """
    tenant = normaliser_tenant(tenant_id)
    strict = {"tenant_id": {"$in": _tenant_aliases(tenant)}}
    actif = _adoption_active(tenant) if adoption is None else bool(adoption)
    if not actif:
        return strict
    return {"$or": [
        strict,
        {"tenant_id": {"$exists": False}},
        {"tenant_id": None},
    ]}


def _document_canonique(document: Any, tenant: str) -> dict[str, Any]:
    """Copie un document legacy en ramenant un alias demo vers le tenant canonique."""
    doc = copy.deepcopy(dict(document))
    declare = _texte(doc.get("tenant_id"))
    if declare and normaliser_tenant(declare) == tenant:
        doc["tenant_id"] = tenant
    return doc


def _iso(valeur: Any) -> str | None:
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    texte = _texte(valeur)
    if not texte:
        return None
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _version_ancre(contexte: Mapping[str, Any], situation: Mapping[str, Any],
                   maintenant: Any = None) -> dict[str, Any]:
    """Snapshot d'ancre avec une version strictement antérieure à la Situation écrite."""
    doc = copy.deepcopy(dict(contexte))
    reference = (_iso(situation.get("maj_le")) or _iso(situation.get("cree_le"))
                 or _iso(maintenant))
    actuelle = next((_iso(doc.get(champ)) for champ in _CHAMPS_DATE if _iso(doc.get(champ))),
                    None)
    if reference and actuelle:
        try:
            if (datetime.fromisoformat(actuelle).timestamp()
                    < datetime.fromisoformat(reference).timestamp()):
                return doc
        except ValueError:
            pass
    try:
        base = (datetime.fromisoformat(reference) if reference
                else datetime.now(timezone.utc))
    except ValueError:
        base = datetime.now(timezone.utc)
    doc["maj_le"] = (base - timedelta(microseconds=1)).isoformat(timespec="microseconds")
    return doc


def situation_liee(case: Any) -> str | None:
    """Identifiant de la Situation liée : uniquement ``situations[0]`` (ADR-0008)."""
    if not isinstance(case, Mapping):
        return None
    situations = case.get("situations") or []
    if isinstance(situations, (str, bytes)) or not isinstance(situations, (list, tuple)):
        return None
    if not situations:
        return None
    identifiant = situations[0]
    if isinstance(identifiant, Mapping):
        identifiant = identifiant.get("id") or identifiant.get("situation_id")
    return _texte(identifiant) or None


def _source_action(action: Any, statut: Any, maj_le: Any = None) -> str:
    return f"action:{_texte(action)}:{_texte(statut)}:{_texte(maj_le)}"


def _source_decision(decision: Any, acteur: Any, decidee_le: Any = None) -> str:
    empreinte = pont.hash_contenu({
        "decision": _texte(decision), "par": _texte(acteur),
        "decidee_le": _texte(decidee_le)})[:16]
    return f"decision:{empreinte}"


def evenement_action_situation(situation: Any, action: Any, *, tenant_id: Any,
                               maintenant: Any = None) -> dict[str, Any] | None:
    """Événement `situation.maj` après une action Radar (statut déjà écrit dans Mongo)."""
    if not isinstance(situation, Mapping):
        raise pont.PontInvalide("situation : document attendu")
    statut = _texte(situation.get("statut"))
    if not statut:
        return None
    tenant = normaliser_tenant(tenant_id or situation.get("tenant_id"))
    doc = _document_canonique(situation, tenant)
    return pont.evenement_depuis_situation(
        doc,
        tenant_id=tenant,
        source_event_id=_source_action(action, statut, doc.get("maj_le")),
        maintenant=maintenant,
    )


def evenement_decision_situation(situation: Any, *, tenant_id: Any,
                                 maintenant: Any = None) -> dict[str, Any] | None:
    """Événement `situation.maj` après une décision legacy (statut/decision déjà écrits)."""
    if not isinstance(situation, Mapping):
        raise pont.PontInvalide("situation : document attendu")
    decision = _texte(situation.get("decision"))
    if not decision:
        return None
    tenant = normaliser_tenant(tenant_id or situation.get("tenant_id"))
    doc = _document_canonique(situation, tenant)
    return pont.evenement_depuis_situation(
        doc,
        tenant_id=tenant,
        source_event_id=_source_decision(
            decision, doc.get("decidee_par"), doc.get("decidee_le")),
        maintenant=maintenant,
    )


def _completer_snapshot(situation_id: str, contexte: Mapping[str, Any]) -> dict[str, Any]:
    """Complète les champs optionnels exigés par l'ancre C1 sans inventer de fait métier.

    Le builder Situation utilise déjà l'identifiant comme titre et CANDIDATE/MOYENNE par
    défaut. Le snapshot d'ancre doit produire exactement la même forme pour ne pas être
    silencieusement écarté quand un document legacy n'a ni titre ni priorité.
    """
    doc = copy.deepcopy(dict(contexte))
    for champ, defaut in (("titre", situation_id), ("statut", "candidate"),
                          ("priorite", "normale")):
        valeur = doc.get(champ)
        if not isinstance(valeur, str) or not valeur.strip():
            doc[champ] = defaut
    return doc


def evenement_case_lie(case: Any, situation: Any, *, tenant_id: Any,
                       situation_contexte: Any = None,
                       maintenant: Any = None) -> dict[str, Any] | None:
    """Événement `case.maj` du Travail lié à la Situation traitée, s'il produit des objets.

    L'événement embarque le snapshot de Situation (éventuellement celui d'avant l'écriture)
    pour être autosuffisant : le worker peut traiter le case avant l'événement de Situation.
    Le snapshot antérieur porte un ``source_maj_le`` plus ancien, donc il ne réécrit jamais
    la Situation à jour. Un case sans décision exploitable n'émet rien.
    """
    if not isinstance(case, Mapping):
        raise pont.PontInvalide("case : document attendu")
    if not isinstance(situation, Mapping):
        raise pont.PontInvalide("situation : document attendu")
    situation_id = situation_liee(case)
    if not situation_id or _texte(situation.get("id")) != situation_id:
        return None
    tenant = normaliser_tenant(tenant_id or case.get("tenant_id"))
    case_doc = _document_canonique(case, tenant)
    situation_doc = _document_canonique(situation, tenant)
    contexte_source = (_document_canonique(situation_contexte, tenant)
                       if isinstance(situation_contexte, Mapping) else situation_doc)
    contexte = _version_ancre(contexte_source, situation_doc, maintenant)
    contexte = _completer_snapshot(situation_id, contexte)
    # Le builder lève si le case ou le snapshot est incohérent : la route legacy reste
    # best-effort et journalise l'échec sans annuler l'écriture Mongo.
    objets = pont.objets_depuis_case(
        case_doc, tenant_id=tenant, situation=contexte, maintenant=maintenant)
    if not any(objet.get("type") == "DECISION" for objet in objets):
        return None
    utile = {cle: case_doc.get(cle) for cle in (
        "id", "tenant_id", "titre", "situations", "decisions", "options",
        "responsable", "objectif", "maj_le", "cree_le")}
    source_event_id = "case:" + pont.hash_contenu(
        {"case": utile, "situation": contexte})[:16]
    return pont.evenement_depuis_case(
        case_doc, tenant_id=tenant, situation=contexte,
        source_event_id=source_event_id, maintenant=maintenant)


def _texte_legacy(valeur: Any) -> str:
    if valeur is None or isinstance(
            valeur, (bool, bytes, bytearray, Mapping, list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _options_exploitables(valeur: Any) -> bool:
    if valeur is None:
        return False
    elements = ([valeur] if isinstance(valeur, Mapping)
                or not isinstance(valeur, (list, tuple, set, frozenset)) else list(valeur))
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("texte") or element.get("titre") or element.get("option")
        if _texte_legacy(element):
            return True
    return False


def _nombre_decisions_situation(situation: Any) -> int:
    """Compte exactement les Decisions que le builder C1 produirait pour cette Situation.

    Miroir de ``_decisions_situation`` : une liste `decisions` exploitable prime, sinon le
    champ `decision` isolé ne compte que si la Situation est réellement décidée.
    """
    if not isinstance(situation, Mapping):
        return 0
    decisions = 0
    brut = situation.get("decisions")
    if isinstance(brut, (list, tuple)):
        for element in brut:
            if isinstance(element, Mapping):
                texte = element.get("texte") or element.get("decision")
                if _texte_legacy(texte) or _options_exploitables(element.get("options")):
                    decisions += 1
            elif _texte_legacy(element):
                decisions += 1
    if decisions:
        return decisions
    if (pont.statut_canonique(situation.get("statut")) in {"DECIDED", "DISMISSED"}
            and _texte_legacy(situation.get("decision"))):
        return 1
    return 0


def _dernier_rang_decision_case(case: Mapping[str, Any]) -> int:
    """Dernier rang effectivement produit par `objets_depuis_case` (les blancs sont sautés)."""
    brut = case.get("decisions")
    if brut is None:
        return 0
    if isinstance(brut, Mapping) or isinstance(brut, str) or not isinstance(brut, (list, tuple)):
        decisions = [brut]
    else:
        decisions = list(brut)
    options_case = case.get("options")
    dernier = 0
    for rang, decision in enumerate(decisions, 1):
        if isinstance(decision, Mapping):
            texte = decision.get("texte") or decision.get("decision")
            options = (decision.get("options") if decision.get("options") is not None
                       else options_case)
        else:
            texte, options = decision, options_case
        if _texte_legacy(texte) or _options_exploitables(options):
            dernier = rang
    return dernier


def candidats_boucle(case: Any, situation: Any = None) -> list[str]:
    """Candidats d'objet courant, du plus précis au plus général.

    L'appelant les lit dans l'ordre et s'arrête au premier objet canonique lisible.
    """
    situation_id = situation_liee(case)
    if not situation_id:
        return []
    candidats: list[str] = []
    case_id = _texte(case.get("id"))
    dernier = _dernier_rang_decision_case(case)
    if case_id and dernier:
        candidats.append(pont.decision_case_id(case_id, dernier))
    nombre = _nombre_decisions_situation(situation)
    if nombre:
        candidats.append(pont.decision_situation_id(situation_id, nombre))
    candidats.append(pont.investigation_id(situation_id))
    return list(dict.fromkeys(candidats))


def candidat_boucle(case: Any, situation: Any = None) -> str | None:
    """Premier candidat canonique, ou ``None`` sans Situation liée."""
    candidats = candidats_boucle(case, situation)
    return candidats[0] if candidats else None


def _statut(ligne: Mapping[str, Any]) -> str:
    donnees = ligne.get("donnees")
    if isinstance(donnees, Mapping):
        statut = _texte(donnees.get("statut"))
        if statut:
            return statut
    return _texte(ligne.get("statut"))


def _etape(ligne: Any) -> dict[str, Any] | None:
    if not isinstance(ligne, Mapping):
        return None
    identifiant = _texte(ligne.get("id"))
    type_objet = _texte(ligne.get("type")).upper()
    if not identifiant or not type_objet:
        return None
    etape: dict[str, Any] = {"id": identifiant, "type": type_objet}
    titre = _texte(ligne.get("titre"))
    if titre:
        etape["titre"] = titre
    statut = _statut(ligne)
    if statut:
        etape["statut"] = statut
    return etape


def extraire_boucle(ligne: Any, *, boucle_id: Any = None) -> dict[str, Any] | None:
    """Réduit une ligne `lire_boucle(historique=True)` au contrat `cas.boucle`."""
    if not isinstance(ligne, Mapping):
        return None
    source = ligne.get("chaine")
    if not isinstance(source, (list, tuple)) or not source:
        source = [ligne]
    chaine = [etape for etape in (_etape(element) for element in source) if etape]
    if not chaine:
        return None
    courant = chaine[-1]
    resultat: dict[str, Any] = {
        "id": _texte(boucle_id) or courant["id"],
        "chaine": chaine,
    }
    if courant.get("statut"):
        resultat["statut"] = courant["statut"]
    return resultat
