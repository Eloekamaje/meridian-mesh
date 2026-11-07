"""Orchestration des transitions canoniques de la boucle d'entreprise.

Chaque commande ouvre une transaction, charge sa source verrouillée via le port
:class:`~meridian.ports.boucle.BoucleStore`, applique la transition pure, crée l'objet en
mode strictement create-only, met à jour uniquement les liens inverses nécessaires, puis
relit la chaîne canonique. Ce module ne connaît ni HTTP, ni FastAPI, ni Postgres :
l'adaptateur concret est injecté par la couche d'entrée.

Les sources sont lues en mapping (``as_dict=True``) pour conserver les clés ``donnees``
migrées du legacy. Les transitions pures du port utilisent déjà ``_valeur`` et acceptent
donc ces mappings.

Les erreurs sont explicites :

- :class:`SourceIntrouvable` : la source n'existe pas dans le tenant (l'API répond 404) ;
- :class:`TransitionRefusee` : source incomplète, type incohérent ou version périmée (409) ;
- :class:`meridian.ports.boucle.ObjetExistant` et
  :class:`meridian.ports.boucle.VersionRefusee` remontent du port et sont traduits en 409
  par la couche HTTP.
"""
from __future__ import annotations

import copy
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from meridian.ports.boucle import BoucleStore, ObjetExistant, VersionRefusee

__all__ = [
    "SourceIntrouvable",
    "TransitionRefusee",
    "ResultatTransition",
    "ObjetExistant",
    "VersionRefusee",
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

_LIENS_SOURCE = {
    "INVESTIGATION": (("situation_id",),),
    "DECISION": (("investigation_id", "investigation_ref"),),
    "INITIATIVE": (("decision_id", "decision_ref"),),
    "OUTCOME": (("initiative_id", "initiative_ref"),),
}

_VIGNETTES = ("chaine", "historique")


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


def _valeur_source(source: Any, nom: str, defaut: Any = None) -> Any:
    if isinstance(source, Mapping):
        if nom in source:
            return source[nom]
        donnees = source.get("donnees")
        if isinstance(donnees, Mapping) and nom in donnees:
            return donnees[nom]
        return defaut
    return getattr(source, nom, defaut)


def _source(
    depot: BoucleStore, conn: Any, tenant: str, identifiant: Any,
    type_attendu: str, role: str, *, for_update: bool = True,
    exiger_options: bool = False,
) -> Any:
    """Charge la source en mapping, verrouillée, et vérifie type, tenant et liens requis."""
    identifiant = _texte(identifiant)
    if not identifiant:
        raise SourceIntrouvable(role, identifiant)
    source = depot.lire_boucle(
        conn, tenant, identifiant, as_dict=True, for_update=for_update)
    if source is None:
        raise SourceIntrouvable(role, identifiant)
    trouve = _texte(_valeur_source(source, "type")).upper()
    if trouve != type_attendu:
        raise TransitionRefusee(
            f"{role} {identifiant!r} doit être de type {type_attendu} (reçu {trouve or 'inconnu'})"
        )
    tenant_source = _texte(_valeur_source(source, "tenant_id"))
    if tenant_source != tenant:
        raise TransitionRefusee(
            f"{role} {identifiant!r} appartient au tenant {tenant_source or 'inconnu'!r}, "
            f"attendu {tenant!r}"
        )
    for aliases in _LIENS_SOURCE.get(type_attendu, ()):
        if not any(_texte(_valeur_source(source, alias)) for alias in aliases):
            raise TransitionRefusee(
                f"{role} incomplète : {' ou '.join(aliases)} manquant")
    if exiger_options and type_attendu == "DECISION":
        options = _valeur_source(source, "options")
        if isinstance(options, str):
            options = [options]
        if not isinstance(options, (list, tuple)) or not any(_texte(o) for o in options):
            raise TransitionRefusee(f"{role} incomplète : options manquantes")
    return source


def _sans_version(objet: Any) -> Any:
    """Retire explicitement ``version`` pour laisser Postgres incrémenter la version stockée."""
    if isinstance(objet, Mapping):
        charge = copy.deepcopy(dict(objet))
    elif is_dataclass(objet) and not isinstance(objet, type):
        convertisseur = getattr(objet, "to_dict", None) or getattr(objet, "as_dict", None)
        charge = copy.deepcopy(convertisseur() if callable(convertisseur) else asdict(objet))
    else:
        return objet
    charge.pop("version", None)
    return charge


def _persister(
    depot: BoucleStore, conn: Any, tenant: str, objets: list[Any], *, creer: bool = True,
) -> None:
    """Persiste dans une transaction ; ``creer=True`` refuse tout identifiant déjà présent."""
    with depot.transaction(conn):
        depot.enregistrer_boucle(
            conn, tenant, objets=[_sans_version(objet) for objet in objets],
            historique=True, creer=creer)


def _nettoyer(objet: Mapping[str, Any]) -> dict[str, Any]:
    """Retire les vignettes de transport et ``_historique`` des données publiques."""
    nettoye = {cle: valeur for cle, valeur in objet.items() if cle not in _VIGNETTES}
    donnees = nettoye.get("donnees")
    if isinstance(donnees, Mapping):
        nettoye["donnees"] = {
            cle: valeur for cle, valeur in donnees.items() if str(cle) != "_historique"
        }
    return nettoye


def _relire(depot: BoucleStore, conn: Any, tenant: str, identifiant: str) -> ResultatTransition:
    """Relit l'objet et sa chaîne ; ``_historique`` reste dans ``historique``, pas dans ``objet``."""
    lu = depot.lire_boucle(conn, tenant, identifiant, historique=True, as_dict=True)
    if lu is None:
        raise TransitionRefusee(f"objet persisté introuvable : {identifiant}")
    return ResultatTransition(
        objet=_nettoyer(lu),
        chaine=[_nettoyer(element) for element in (lu.get("chaine") or [])],
        historique=list(lu.get("historique") or []),
    )


def creer_situation(
    depot: BoucleStore, conn: Any, tenant_id: str, **champs: Any,
) -> ResultatTransition:
    """Crée une Situation racine ; un identifiant existant est refusé par le port (409)."""
    identifiant = _texte(champs.pop("id", None)) or f"situation-{uuid.uuid4().hex[:12]}"
    if not _texte(champs.get("titre")):
        champs["titre"] = _texte(champs.get("description")) or _texte(champs.get("resume"))
    with depot.transaction(conn):
        objet = depot.nouvelle_situation(id=identifiant, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        return _relire(depot, conn, tenant_id, identifiant)


def ouvrir_investigation(
    depot: BoucleStore, conn: Any, tenant_id: str, situation_id: str, **champs: Any,
) -> ResultatTransition:
    """Ouvre une Investigation reliée à une Situation du même tenant."""
    with depot.transaction(conn):
        situation = _source(depot, conn, tenant_id, situation_id, "SITUATION", "situation")
        objet = depot.ouvrir_investigation(situation, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        return _relire(depot, conn, tenant_id, objet.id)


def proposer_decision(
    depot: BoucleStore, conn: Any, tenant_id: str, investigation_id: str, options: Any,
    **champs: Any,
) -> ResultatTransition:
    """Propose une Decision non tranchée reliée à une Investigation."""
    with depot.transaction(conn):
        investigation = _source(
            depot, conn, tenant_id, investigation_id, "INVESTIGATION", "investigation")
        objet = depot.proposer_decision(
            investigation, options, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        return _relire(depot, conn, tenant_id, objet.id)


def trancher_decision(
    depot: BoucleStore, conn: Any, tenant_id: str, decision_id: str, *,
    acteur: str, choix: str, **champs: Any,
) -> ResultatTransition:
    """Tranche une Decision ; seuls les champs canoniques changent, le legacy est préservé."""
    with depot.transaction(conn):
        decision = _source(
            depot, conn, tenant_id, decision_id, "DECISION", "decision",
            exiger_options=True)
        objet = depot.trancher_decision(
            decision, acteur, choix, tenant_id=tenant_id, **champs)
        depot.fusionner_donnees(
            conn, tenant_id, decision_id, depot.donnees_de(objet),
            historique=True, mode=getattr(objet, "mode", None),
            version_attendue=_valeur_source(decision, "version"),
        )
        return _relire(depot, conn, tenant_id, decision_id)


def lancer_initiative(
    depot: BoucleStore, conn: Any, tenant_id: str, decision_id: str, **champs: Any,
) -> ResultatTransition:
    """Lance une Initiative puis fusionne uniquement ``decision.initiative_id``."""
    with depot.transaction(conn):
        decision = _source(depot, conn, tenant_id, decision_id, "DECISION", "decision")
        existante = _texte(_valeur_source(decision, "initiative_id"))
        if existante:
            raise TransitionRefusee(
                f"décision déjà reliée à l'initiative {existante!r}")
        objet = depot.lancer_initiative(decision, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        depot.fusionner_donnees(
            conn, tenant_id, decision_id, {"initiative_id": objet.id},
            historique=True, version_attendue=_valeur_source(decision, "version"),
        )
        return _relire(depot, conn, tenant_id, objet.id)


def mesurer_outcome(
    depot: BoucleStore, conn: Any, tenant_id: str, initiative_id: str, mesure: Any,
    **champs: Any,
) -> ResultatTransition:
    """Mesure un Outcome puis concatène seulement ``outcome_ids`` sur l'Initiative."""
    with depot.transaction(conn):
        initiative = _source(
            depot, conn, tenant_id, initiative_id, "INITIATIVE", "initiative")
        objet = depot.mesurer_outcome(initiative, mesure, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        depot.fusionner_donnees(
            conn, tenant_id, initiative_id, {"outcome_ids": [objet.id]},
            historique=True, ajouter=("outcome_ids",),
            version_attendue=_valeur_source(initiative, "version"),
        )
        return _relire(depot, conn, tenant_id, objet.id)


def _forcer_learning(champs: dict[str, Any]) -> dict[str, Any]:
    """Le flux de promotion exige un humain : statut/mode du Learning ne viennent jamais du client."""
    champs.pop("statut", None)
    champs.pop("mode", None)
    return champs


def capitaliser_learning_depuis_outcome(
    depot: BoucleStore, conn: Any, tenant_id: str, outcome_id: str, **champs: Any,
) -> ResultatTransition:
    """Capitalise un Learning depuis un Outcome mesuré du même tenant."""
    champs = _forcer_learning(champs)
    with depot.transaction(conn):
        outcome = _source(depot, conn, tenant_id, outcome_id, "OUTCOME", "outcome")
        objet = depot.capitaliser_learning(outcome, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        return _relire(depot, conn, tenant_id, objet.id)


def capitaliser_learning_depuis_investigation(
    depot: BoucleStore, conn: Any, tenant_id: str, investigation_id: str, **champs: Any,
) -> ResultatTransition:
    """Capitalise un Learning directement depuis une Investigation du même tenant."""
    champs = _forcer_learning(champs)
    with depot.transaction(conn):
        investigation = _source(
            depot, conn, tenant_id, investigation_id, "INVESTIGATION", "investigation")
        objet = depot.capitaliser_learning(investigation, tenant_id=tenant_id, **champs)
        _persister(depot, conn, tenant_id, [objet], creer=True)
        return _relire(depot, conn, tenant_id, objet.id)
