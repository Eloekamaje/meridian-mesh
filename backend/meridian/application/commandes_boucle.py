"""Orchestration des transitions canoniques de la boucle d'entreprise.

Chaque commande charge sa source via le port :class:`~meridian.ports.boucle.BoucleStore`,
applique la transition pure exposée par ce port, persiste le résultat avec historique, puis
relit la chaîne canonique. Ce module ne connaît ni HTTP, ni FastAPI, ni Postgres : l'adaptateur
concret est injecté par la couche d'entrée.

Les erreurs sont explicites :

- :class:`SourceIntrouvable` : la source n'existe pas dans le tenant (l'API répond 404) ;
- :class:`TransitionRefusee` : l'orchestration refuse la transition (l'API répond 409) ;
- les erreurs du port (``BoucleInvalide``, ``ModeleInvalide``) remontent telles quelles et
  sont traduites par la couche HTTP.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, is_dataclass, replace
from typing import Any

from meridian.ports.boucle import BoucleStore

__all__ = [
    "SourceIntrouvable",
    "TransitionRefusee",
    "ResultatTransition",
    "creer_situation",
    "ouvrir_investigation",
    "proposer_decision",
    "trancher_decision",
    "lancer_initiative",
    "mesurer_outcome",
    "capitaliser_learning_depuis_outcome",
    "capitaliser_learning_depuis_investigation",
]

_LIBELLES = {
    "situation": "Situation",
    "investigation": "Investigation",
    "decision": "Décision",
    "initiative": "Initiative",
    "outcome": "Outcome",
}


class SourceIntrouvable(LookupError):
    """La source d'une transition n'existe pas dans le tenant courant."""

    def __init__(self, role: str, identifiant: str):
        self.role = role
        self.identifiant = identifiant
        libelle = _LIBELLES.get(role, role.capitalize())
        super().__init__(f"{libelle} introuvable : {identifiant or '?'}")


class TransitionRefusee(ValueError):
    """L'orchestration refuse la transition avant ou après l'appel du port."""


@dataclass(frozen=True)
class ResultatTransition:
    """Objet persisté, chaîne canonique jusqu'à lui et versions antérieures."""

    objet: dict[str, Any]
    chaine: list[dict[str, Any]]
    historique: list[dict[str, Any]]


def _texte(valeur: Any) -> str:
    return "" if valeur is None else str(valeur).strip()


def _source(
    depot: BoucleStore, conn: Any, tenant: str, identifiant: Any,
    type_attendu: str, role: str,
) -> Any:
    """Charge la source canonique et vérifie son type avant la transition pure."""
    identifiant = _texte(identifiant)
    if not identifiant:
        raise SourceIntrouvable(role, identifiant)
    source = depot.lire_boucle(conn, tenant, identifiant, as_dict=False)
    if source is None:
        raise SourceIntrouvable(role, identifiant)
    trouve = _texte(getattr(source, "type", "")).upper()
    if trouve != type_attendu:
        raise TransitionRefusee(
            f"{role} {identifiant!r} doit être de type {type_attendu} (reçu {trouve or 'inconnu'})"
        )
    tenant_source = _texte(getattr(source, "tenant_id", ""))
    if tenant_source != tenant:
        raise TransitionRefusee(
            f"{role} {identifiant!r} appartient au tenant {tenant_source or 'inconnu'!r}, "
            f"attendu {tenant!r}"
        )
    return source


def _sans_version(objet: Any) -> Any:
    """Laisse Postgres incrémenter la version : un objet relu ne réécrit pas sa version courante."""
    if is_dataclass(objet) and not isinstance(objet, type):
        return replace(objet, version=1)
    if isinstance(objet, Mapping):
        copie = dict(objet)
        copie.pop("version", None)
        return copie
    return objet


def _persister_et_relire(
    depot: BoucleStore, conn: Any, tenant: str, objets: list[Any], identifiant: str,
) -> ResultatTransition:
    """Persiste toute la chaîne dans une transaction, puis relit l'objet et sa chaîne.

    ``enregistrer_boucle`` ouvre une transaction par objet ; l'enveloppe externe garantit
    qu'une chaîne de plusieurs objets (décision + initiative, initiative + outcome) n'est
    jamais partiellement écrite. Sous psycopg 3, les transactions internes deviennent des
    savepoints et l'ensemble est validé ou annulé d'un bloc.
    """
    with conn.transaction():
        depot.enregistrer_boucle(
            conn, tenant, objets=[_sans_version(objet) for objet in objets], historique=True)
    lu = depot.lire_boucle(conn, tenant, identifiant, historique=True, as_dict=True)
    if lu is None:
        raise TransitionRefusee(f"objet persisté introuvable : {identifiant}")
    return ResultatTransition(
        objet={cle: valeur for cle, valeur in lu.items() if cle not in ("chaine", "historique")},
        chaine=list(lu.get("chaine") or []),
        historique=list(lu.get("historique") or []),
    )


def creer_situation(
    depot: BoucleStore, conn: Any, tenant_id: str, **champs: Any,
) -> ResultatTransition:
    """Crée une Situation racine ; un identifiant déjà présent est refusé (409)."""
    identifiant = _texte(champs.pop("id", None)) or f"situation-{uuid.uuid4().hex[:12]}"
    if depot.lire_boucle(conn, tenant_id, identifiant, as_dict=False) is not None:
        raise TransitionRefusee(f"situation déjà existante : {identifiant}")
    titre = _texte(champs.get("titre"))
    if not titre:
        champs["titre"] = _texte(champs.get("description")) or _texte(champs.get("resume"))
    objet = depot.Situation(id=identifiant, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], identifiant)


def ouvrir_investigation(
    depot: BoucleStore, conn: Any, tenant_id: str, situation_id: str, **champs: Any,
) -> ResultatTransition:
    """Ouvre une Investigation reliée à une Situation du même tenant."""
    situation = _source(depot, conn, tenant_id, situation_id, "SITUATION", "situation")
    objet = depot.ouvrir_investigation(situation, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], objet.id)


def proposer_decision(
    depot: BoucleStore, conn: Any, tenant_id: str, investigation_id: str, options: Any,
    **champs: Any,
) -> ResultatTransition:
    """Propose une Decision non tranchée reliée à une Investigation."""
    investigation = _source(
        depot, conn, tenant_id, investigation_id, "INVESTIGATION", "investigation")
    objet = depot.proposer_decision(
        investigation, options, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], objet.id)


def trancher_decision(
    depot: BoucleStore, conn: Any, tenant_id: str, decision_id: str, *,
    acteur: str, choix: str, **champs: Any,
) -> ResultatTransition:
    """Tranche une Decision proposée ; l'ancienne version est conservée dans l'historique."""
    decision = _source(depot, conn, tenant_id, decision_id, "DECISION", "decision")
    objet = depot.trancher_decision(
        decision, acteur, choix, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], objet.id)


def lancer_initiative(
    depot: BoucleStore, conn: Any, tenant_id: str, decision_id: str, **champs: Any,
) -> ResultatTransition:
    """Lance une Initiative depuis une Decision tranchée et maintient le lien inverse."""
    decision = _source(depot, conn, tenant_id, decision_id, "DECISION", "decision")
    objet = depot.lancer_initiative(decision, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [decision, objet], objet.id)


def mesurer_outcome(
    depot: BoucleStore, conn: Any, tenant_id: str, initiative_id: str, mesure: Any,
    **champs: Any,
) -> ResultatTransition:
    """Mesure un Outcome depuis une Initiative et maintient ``outcome_ids`` sur l'Initiative."""
    initiative = _source(
        depot, conn, tenant_id, initiative_id, "INITIATIVE", "initiative")
    objet = depot.mesurer_outcome(initiative, mesure, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [initiative, objet], objet.id)


def capitaliser_learning_depuis_outcome(
    depot: BoucleStore, conn: Any, tenant_id: str, outcome_id: str, **champs: Any,
) -> ResultatTransition:
    """Capitalise un Learning depuis un Outcome mesuré du même tenant."""
    outcome = _source(depot, conn, tenant_id, outcome_id, "OUTCOME", "outcome")
    objet = depot.capitaliser_learning(outcome, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], objet.id)


def capitaliser_learning_depuis_investigation(
    depot: BoucleStore, conn: Any, tenant_id: str, investigation_id: str, **champs: Any,
) -> ResultatTransition:
    """Capitalise un Learning directement depuis une Investigation du même tenant."""
    investigation = _source(
        depot, conn, tenant_id, investigation_id, "INVESTIGATION", "investigation")
    objet = depot.capitaliser_learning(investigation, tenant_id=tenant_id, **champs)
    return _persister_et_relire(depot, conn, tenant_id, [objet], objet.id)
