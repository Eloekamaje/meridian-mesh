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

from collections.abc import Mapping
from typing import Any

from meridian.application import pont_canonique as pont

__all__ = [
    "candidat_boucle",
    "evenement_action_situation",
    "evenement_case_lie",
    "evenement_decision_situation",
    "extraire_boucle",
    "filtre_tenant",
    "normaliser_tenant",
    "situation_liee",
]


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def normaliser_tenant(tenant_id: Any) -> str:
    """Valide et canonise un tenant ; ne fabrique jamais de tenant par défaut."""
    return pont.normaliser_tenant(tenant_id)


def filtre_tenant(tenant_id: Any) -> dict[str, Any]:
    """Filtre Mongo d'isolation tenant.

    Les documents legacy antérieurs au P0 n'ont pas de ``tenant_id``. Les accepter comme
    relevant du tenant courant est le compromis de reprise retenu : une migration
    rétroactive massive est plus risquée qu'une normalisation applicative. Tout document
    qui déclare un autre tenant est en revanche exclu.
    """
    tenant = normaliser_tenant(tenant_id)
    # `local` et `demo` désignent le même tenant de démonstration dans le legacy.
    tenants = [tenant]
    if tenant in {"local", "demo"}:
        tenants = ["local", "demo"]
    return {"$or": [
        {"tenant_id": {"$in": tenants}},
        {"tenant_id": {"$exists": False}},
        {"tenant_id": None},
    ]}


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
    return pont.evenement_depuis_situation(
        situation,
        tenant_id=tenant_id,
        source_event_id=_source_action(action, statut, situation.get("maj_le")),
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
    return pont.evenement_depuis_situation(
        situation,
        tenant_id=tenant_id,
        source_event_id=_source_decision(
            decision, situation.get("decidee_par"), situation.get("decidee_le")),
        maintenant=maintenant,
    )


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
    contexte = (situation_contexte if isinstance(situation_contexte, Mapping)
                else situation)
    # Le builder lève si le case ou le snapshot est incohérent : la route legacy reste
    # best-effort et journalise l'échec sans annuler l'écriture Mongo.
    objets = pont.objets_depuis_case(
        case, tenant_id=tenant, situation=contexte, maintenant=maintenant)
    if not any(objet.get("type") == "DECISION" for objet in objets):
        return None
    return pont.evenement_depuis_case(
        case, tenant_id=tenant, situation=contexte, maintenant=maintenant)


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


def candidat_boucle(case: Any, situation: Any = None) -> str | None:
    """Objet canonique courant dérivable sans ambiguïté pour ce Travail.

    Priorité : dernière décision du Travail, décision de la Situation, puis Investigation.
    Aucune requête n'est faite ici : l'appelant lit une seule fois l'objet choisi.
    """
    situation_id = situation_liee(case)
    if not situation_id:
        return None
    case_id = _texte(case.get("id"))
    dernier = _dernier_rang_decision_case(case)
    if case_id and dernier:
        return pont.decision_case_id(case_id, dernier)
    nombre = _nombre_decisions_situation(situation)
    if nombre:
        return pont.decision_situation_id(situation_id, nombre)
    return pont.investigation_id(situation_id)


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
