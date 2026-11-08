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
from meridian.domain.objets_exploitation import (
    STATUTS_HYPOTHESIS,
    STATUTS_OPPORTUNITE,
    STATUTS_RISQUE,
    TRANSITIONS_HYPOTHESIS,
    ObjetsExploitationInvalide,
    TransitionObjetRefusee,
    _PREFIXES,
)

__all__ = [
    "SourceIntrouvable",
    "TransitionRefusee",
    "DoublonExploitation",
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
    "creer_expression",
    "creer_opportunite",
    "creer_risque",
    "lister_opportunites",
    "lister_risques",
    "changer_statut_opportunite",
    "changer_statut_risque",
    "creer_hypothese",
    "lister_hypotheses",
    "changer_statut_hypothese",
    "creer_scenario",
    "lister_scenarios",
    "comparer_scenarios",
]

_LIBELLES = {
    "situation": "Situation",
    "investigation": "Investigation",
    "decision": "Décision",
    "scenario": "Scénario",
    "hypothesis": "Hypothèse",
    "initiative": "Initiative",
    "outcome": "Outcome",
    "learning": "Learning",
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


class DoublonExploitation(TransitionRefusee):
    """La source porte déjà l'objet d'exploitation exclusif demandé (409, jamais 422)."""


STATUT_EXPRESSION = "PROPOSED"
STATUTS_EXPRESSION_QUALIFIABLES = ("PROPOSED", "CONFIRMED")


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
        trouvees = [
            (alias, _texte(_valeur_source(source, alias)))
            for alias in aliases
            if _texte(_valeur_source(source, alias))
        ]
        if not trouvees:
            raise TransitionRefusee(
                f"{role} incomplète : {' ou '.join(aliases)} manquant")
        if len({valeur for _, valeur in trouvees}) > 1:
            details = ", ".join(f"{alias}={valeur!r}" for alias, valeur in trouvees)
            raise TransitionRefusee(f"{role} : liens contradictoires ({details})")
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
    # Le lien inverse est serveur : seule ``creer_expression`` pose ``expression_id``.
    champs.pop("expression_id", None)
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


def creer_expression(
    depot: BoucleStore, conn: Any, tenant_id: str, situation_id: str, **champs: Any,
) -> ResultatTransition:
    """Formule une Expression unique sur une Situation du même tenant.

    La Situation est verrouillée : deux créations concurrentes observent le même
    ``expression_id``, la seconde est refusée en :class:`DoublonExploitation`. Le statut
    est toujours ``PROPOSED``, jamais celui du client. La persistance passe par le port
    d'exploitation (type B) qui écrit l'Expression et le lien inverse dans une seule
    transaction ; ``enregistrer_boucle`` reste réservé aux types canoniques.
    """
    champs.pop("statut", None)
    with depot.transaction(conn):
        situation = _source(
            depot, conn, tenant_id, situation_id, "SITUATION", "situation")
        existante = _texte(_valeur_source(situation, "expression_id"))
        if existante:
            raise DoublonExploitation(
                f"Situation déjà exprimée : la situation {situation_id!r} "
                f"possède déjà l'Expression {existante!r}")
        objet = depot.nouvelle_expression(
            situation=situation, tenant_id=tenant_id,
            statut=STATUT_EXPRESSION, **champs)
        try:
            depot.enregistrer_objets(conn, tenant_id, objets=[objet], as_dict=False)
        except ObjetExistant as exc:
            # L'index unique (tenant_id, situation_id) reste la seconde barrière
            # derrière le verrou et le pré-check : le port convertit la
            # UniqueViolation en ObjetExistant, que le contrat public expose en 409.
            raise DoublonExploitation(
                "Situation déjà exprimée : une Expression existe déjà pour cette Situation"
            ) from exc
        return _relire(depot, conn, tenant_id, objet.id)


STATUT_OPPORTUNITE_INITIAL = "DETECTED"
STATUT_RISQUE_INITIAL = "DETECTED"
STATUT_HYPOTHESE_INITIAL = "OPEN"
MODE_HYPOTHESE_INITIAL = "PROPOSED"
STATUTS_INVESTIGATION_FERMES = frozenset({
    "CLOSED", "CLOSE", "CLOTUREE", "FERMEE", "ARCHIVED", "ARCHIVEE",
})
_CHAMPS_SERVEUR_HYPOTHESE = ("statut", "id")


def _refuser_statut_client(champs: dict[str, Any], libelle: str) -> None:
    """Le statut initial est serveur ; un statut client est un refus de contrat (422)."""
    if "statut" in champs:
        raise ObjetsExploitationInvalide(
            f"statut interdit à la création d'un {libelle} : le serveur force "
            f"{STATUT_OPPORTUNITE_INITIAL}")


def _exiger_titre(champs: dict[str, Any], libelle: str) -> None:
    if not _texte(champs.get("titre")):
        raise ObjetsExploitationInvalide(f"titre obligatoire pour un {libelle}")


def _source_expression(
    depot: BoucleStore, conn: Any, tenant: str, expression_id: Any, *,
    for_update: bool = True,
) -> Any:
    """Charge une Expression du tenant ; une autre source est un refus de contrat (422)."""
    identifiant = _texte(expression_id)
    if not identifiant:
        raise SourceIntrouvable("expression", identifiant)
    source = depot.lire_boucle(
        conn, tenant, identifiant, as_dict=True, for_update=for_update)
    if source is None:
        raise SourceIntrouvable("expression", identifiant)
    type_trouve = _texte(_valeur_source(source, "type")).upper()
    if type_trouve != "EXPRESSION":
        raise ObjetsExploitationInvalide(
            f"expression {identifiant!r} doit être de type EXPRESSION "
            f"(reçu {type_trouve or 'inconnu'})")
    tenant_source = _texte(_valeur_source(source, "tenant_id"))
    if tenant_source != tenant:
        raise SourceIntrouvable("expression", identifiant)
    return source


def _creation_depuis_expression(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: Any,
    *,
    fabrique: Any,
    type_objet: str,
    libelle: str,
    statut_initial: str,
    champs: dict[str, Any],
) -> ResultatTransition:
    _refuser_statut_client(champs, libelle)
    _exiger_titre(champs, libelle)
    with depot.transaction(conn):
        expression = _source_expression(depot, conn, tenant_id, expression_id)
        statut_expression = _texte(_valeur_source(expression, "statut")).upper()
        if statut_expression not in STATUTS_EXPRESSION_QUALIFIABLES:
            raise TransitionRefusee(
                f"expression {_texte(expression_id)!r} non qualifiable : statut "
                f"{statut_expression or 'inconnu'} (attendus : "
                f"{', '.join(STATUTS_EXPRESSION_QUALIFIABLES)})")
        identifiant = f"{_PREFIXES[type_objet]}-{uuid.uuid4().hex[:12]}"
        if depot.lire_boucle(conn, tenant_id, identifiant, as_dict=True) is not None:
            raise DoublonExploitation(
                f"{libelle} déjà existant : l'identifiant {identifiant!r} est déjà utilisé")
        objet = fabrique(
            expression=expression, tenant_id=tenant_id, id=identifiant,
            statut=statut_initial, **champs)
        depot.enregistrer_objets(conn, tenant_id, objets=[objet], as_dict=False)
        return _relire(depot, conn, tenant_id, identifiant)


def creer_opportunite(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: str, **champs: Any,
) -> ResultatTransition:
    """Crée une Opportunity depuis une Expression verrouillée, statut initial ``DETECTED``.

    L'Expression est la seule source acceptée et doit être ``PROPOSED`` ou ``CONFIRMED``
    (sinon 409) ; elle est verrouillée pour sérialiser les créations concurrentes. Le statut
    client est refusé, et la persistance d'exploitation écrit l'objet et
    ``Expression.opportunity_ids`` dans la même transaction.
    """
    return _creation_depuis_expression(
        depot, conn, tenant_id, expression_id,
        fabrique=depot.nouvelle_opportunite,
        type_objet="OPPORTUNITY",
        libelle="opportunité",
        statut_initial=STATUT_OPPORTUNITE_INITIAL,
        champs=dict(champs),
    )


def creer_risque(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: str, **champs: Any,
) -> ResultatTransition:
    """Crée un Risk depuis une Expression verrouillée, statut initial ``DETECTED``.

    Même règle : l'Expression doit être ``PROPOSED`` ou ``CONFIRMED`` (sinon 409).
    """
    return _creation_depuis_expression(
        depot, conn, tenant_id, expression_id,
        fabrique=depot.nouveau_risque,
        type_objet="RISK",
        libelle="risque",
        statut_initial=STATUT_RISQUE_INITIAL,
        champs=dict(champs),
    )


def _lister_enfants_expression(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: Any,
    *, type_objet: str, limite: int,
) -> list[dict[str, Any]]:
    expression = _source_expression(
        depot, conn, tenant_id, expression_id, for_update=False)
    identifiant = _texte(_valeur_source(expression, "id"))
    return depot.lister_objets_exploitation(
        conn, tenant_id, type_=type_objet, expression_id=identifiant,
        limite=limite, as_dict=True,
    )


def lister_opportunites(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: str,
    *, limite: int = 100,
) -> list[dict[str, Any]]:
    """Liste les Opportunities d'une Expression du tenant, bornées par ``limite``."""
    return _lister_enfants_expression(
        depot, conn, tenant_id, expression_id,
        type_objet="OPPORTUNITY", limite=limite)


def lister_risques(
    depot: BoucleStore, conn: Any, tenant_id: str, expression_id: str,
    *, limite: int = 100,
) -> list[dict[str, Any]]:
    """Liste les Risks d'une Expression du tenant, bornés par ``limite``."""
    return _lister_enfants_expression(
        depot, conn, tenant_id, expression_id, type_objet="RISK", limite=limite)


def _source_statut(
    depot: BoucleStore, conn: Any, tenant: str, identifiant: Any,
    type_attendu: str, role: str,
) -> Any:
    """Charge l'objet verrouillé d'une route de statut ; un autre type est un 422.

    Un identifiant inconnu ou hors tenant reste un 404. Le type incorrect n'est pas une
    transition refusée : c'est une erreur de contrat sur la ressource demandée.
    """
    identifiant = _texte(identifiant)
    if not identifiant:
        raise SourceIntrouvable(role, identifiant)
    source = depot.lire_boucle(
        conn, tenant, identifiant, as_dict=True, for_update=True)
    if source is None:
        raise SourceIntrouvable(role, identifiant)
    type_trouve = _texte(_valeur_source(source, "type")).upper()
    if type_trouve != type_attendu:
        raise ObjetsExploitationInvalide(
            f"{role} {identifiant!r} doit être de type {type_attendu} "
            f"(reçu {type_trouve or 'inconnu'})")
    tenant_source = _texte(_valeur_source(source, "tenant_id"))
    if tenant_source != tenant:
        raise SourceIntrouvable(role, identifiant)
    return source


def _changer_statut_objet(
    depot: BoucleStore, conn: Any, tenant_id: str, identifiant: Any,
    statut: Any, *,
    type_attendu: str,
    role: str,
    statuts: tuple[str, ...],
    muter: Any,
    motif: Any = None,
    preuves: Any = None,
) -> ResultatTransition:
    cible = _texte(statut).upper()
    if cible not in statuts:
        raise ObjetsExploitationInvalide(
            f"statut inconnu : {statut!r} (attendus : {', '.join(statuts)})")
    with depot.transaction(conn):
        source = _source_statut(
            depot, conn, tenant_id, identifiant, type_attendu, role)
        try:
            objet = muter(source, cible, motif=motif, preuves=preuves)
        except TransitionObjetRefusee as exc:
            raise TransitionRefusee(str(exc)) from exc
        depot.enregistrer_objets(
            conn, tenant_id, objets=[objet], as_dict=False, historique=True)
        return _relire(depot, conn, tenant_id, _texte(identifiant))


def changer_statut_opportunite(
    depot: BoucleStore, conn: Any, tenant_id: str, opportunite_id: str,
    statut: str, *, motif: Any = None, preuves: Any = None,
) -> ResultatTransition:
    """Fait évoluer une Opportunity selon ``TRANSITIONS_OPPORTUNITE``.

    Une transition refusée est un 409 ; un statut inconnu reste une erreur de contrat
    (422) avant toute écriture. Le motif courant est conservé dans ``motif`` et la version
    précédente dans ``historique``.
    """
    return _changer_statut_objet(
        depot, conn, tenant_id, opportunite_id, statut,
        type_attendu="OPPORTUNITY", role="opportunité",
        statuts=STATUTS_OPPORTUNITE, muter=depot.muer_opportunite,
        motif=motif, preuves=preuves,
    )


def changer_statut_risque(
    depot: BoucleStore, conn: Any, tenant_id: str, risque_id: str,
    statut: str, *, motif: Any = None, preuves: Any = None,
) -> ResultatTransition:
    """Fait évoluer un Risk selon ``TRANSITIONS_RISQUE`` (même contrat que l'opportunité)."""
    return _changer_statut_objet(
        depot, conn, tenant_id, risque_id, statut,
        type_attendu="RISK", role="risque",
        statuts=STATUTS_RISQUE, muter=depot.muer_risque,
        motif=motif, preuves=preuves,
    )


def _source_investigation(
    depot: BoucleStore, conn: Any, tenant: str, investigation_id: Any, *,
    for_update: bool = True,
) -> Any:
    """Charge une Investigation du tenant ; une autre source est un refus de contrat (422)."""
    identifiant = _texte(investigation_id)
    if not identifiant:
        raise SourceIntrouvable("investigation", identifiant)
    source = depot.lire_boucle(
        conn, tenant, identifiant, as_dict=True, for_update=for_update)
    if source is None:
        raise SourceIntrouvable("investigation", identifiant)
    type_trouve = _texte(_valeur_source(source, "type")).upper()
    if type_trouve != "INVESTIGATION":
        raise ObjetsExploitationInvalide(
            f"investigation {identifiant!r} doit être de type INVESTIGATION "
            f"(reçu {type_trouve or 'inconnu'})"
        )
    tenant_source = _texte(_valeur_source(source, "tenant_id"))
    if tenant_source != tenant:
        raise SourceIntrouvable("investigation", identifiant)
    return source


def creer_hypothese(
    depot: BoucleStore, conn: Any, tenant_id: str, investigation_id: str,
    **champs: Any,
) -> ResultatTransition:
    """Formule une Hypothesis initiale (``OPEN``/``PROPOSED``) sur une Investigation.

    L'Investigation est verrouillée : la création et le lien inverse
    ``Investigation.hypothesis_ids`` sont écrits dans la même transaction. Le statut et
    le mode initiaux sont serveur : un ``statut`` ou un ``id`` client est refusé (422),
    et un ``mode`` de commande est ignoré au profit de ``PROPOSED``.
    """
    for champ in _CHAMPS_SERVEUR_HYPOTHESE:
        if champ in champs:
            raise ObjetsExploitationInvalide(
                f"{champ} interdit à la création d'une hypothèse : le serveur force "
                f"statut={STATUT_HYPOTHESE_INITIAL}, mode={MODE_HYPOTHESE_INITIAL}")
    # Le mode initial est serveur : une valeur de commande (chemin interne) est ignorée,
    # le contrat HTTP la refuse avant d'arriver ici (extra="forbid").
    champs.pop("mode", None)
    with depot.transaction(conn):
        investigation = _source_investigation(
            depot, conn, tenant_id, investigation_id, for_update=True)
        statut_investigation = _texte(
            _valeur_source(investigation, "statut")).upper()
        if statut_investigation in STATUTS_INVESTIGATION_FERMES:
            raise TransitionRefusee(
                f"investigation {_texte(investigation_id)!r} fermée : statut "
                f"{statut_investigation or 'inconnu'} ; une hypothèse ne peut être "
                "formulée que sur une investigation ouverte")
        identifiant = f"{_PREFIXES['HYPOTHESIS']}-{uuid.uuid4().hex[:12]}"
        if depot.lire_boucle(conn, tenant_id, identifiant, as_dict=True) is not None:
            raise DoublonExploitation(
                "hypothèse déjà existante : l'identifiant "
                f"{identifiant!r} est déjà utilisé")
        objet = depot.nouvelle_hypothese(
            investigation=investigation, tenant_id=tenant_id, id=identifiant,
            statut=STATUT_HYPOTHESE_INITIAL, mode=MODE_HYPOTHESE_INITIAL, **champs)
        depot.enregistrer_objets(conn, tenant_id, objets=[objet], as_dict=False)
        return _relire(depot, conn, tenant_id, identifiant)


def lister_hypotheses(
    depot: BoucleStore, conn: Any, tenant_id: str, *,
    investigation_id: Any = None, statut: Any = None, limite: int = 100,
) -> list[dict[str, Any]]:
    """Liste les Hypothèses du tenant, filtrées par Investigation et statut."""
    statut_normalise = None
    if _texte(statut):
        statut_normalise = _texte(statut).upper()
        if statut_normalise not in STATUTS_HYPOTHESIS:
            raise ObjetsExploitationInvalide(
                f"statut inconnu : {statut!r} "
                f"(attendus : {', '.join(STATUTS_HYPOTHESIS)})")
    investigation = None
    if _texte(investigation_id):
        investigation = _source_investigation(
            depot, conn, tenant_id, investigation_id, for_update=False)
    return depot.lister_objets_exploitation(
        conn, tenant_id, type_="HYPOTHESIS",
        investigation_id=(
            _texte(_valeur_source(investigation, "id")) if investigation else None),
        statut=statut_normalise, limite=limite, as_dict=True,
    )


def changer_statut_hypothese(
    depot: BoucleStore, conn: Any, tenant_id: str, hypothese_id: str,
    statut: str, *, motif: Any = None, preuves: Any = None,
) -> ResultatTransition:
    """Fait évoluer une Hypothesis selon ``TRANSITIONS_HYPOTHESIS``.

    Une transition non autorisée est un 409 ; un statut inconnu et un ``CONFIRMED``
    sans preuve restent des refus de domaine (422). Le motif courant est conservé dans
    ``motif`` et la version précédente dans l'historique.
    """
    cible = _texte(statut).upper()
    if cible not in STATUTS_HYPOTHESIS:
        raise ObjetsExploitationInvalide(
            f"statut inconnu : {statut!r} "
            f"(attendus : {', '.join(STATUTS_HYPOTHESIS)})")
    with depot.transaction(conn):
        source = _source_statut(
            depot, conn, tenant_id, hypothese_id, "HYPOTHESIS", "hypothèse")
        actuel = _texte(_valeur_source(source, "statut")).upper() or "OPEN"
        if cible not in TRANSITIONS_HYPOTHESIS.get(actuel, ()):
            raise TransitionRefusee(
                f"transition d'hypothèse refusée : {actuel} → {cible}")
        objet = depot.muer_hypothese(
            source, cible, motif=motif, preuves=preuves)
        depot.enregistrer_objets(
            conn, tenant_id, objets=[objet], as_dict=False, historique=True)
        return _relire(depot, conn, tenant_id, _texte(hypothese_id))


_METRIQUES_SCENARIO = (
    "valeur_estimee", "cout_estime", "delai_jours", "complexite", "risque",
)


def _nombre_scenario(valeur: Any) -> float | None:
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _resume_scenario(ligne: Any) -> dict[str, Any]:
    """Rend les attributs comparables d'un scénario, sans exposer ses données internes."""
    return {
        "id": _texte(_valeur_source(ligne, "id")),
        "titre": _texte(_valeur_source(ligne, "titre")),
        "statut": _texte(_valeur_source(ligne, "statut")) or None,
        "investigation_id": _texte(_valeur_source(ligne, "investigation_id")) or None,
        "decision_id": _texte(_valeur_source(ligne, "decision_id")) or None,
        "valeur_estimee": _nombre_scenario(_valeur_source(ligne, "valeur_estimee")),
        "cout_estime": _nombre_scenario(_valeur_source(ligne, "cout_estime")),
        "delai_jours": _nombre_scenario(_valeur_source(ligne, "delai_jours")),
        "risque": _nombre_scenario(_valeur_source(ligne, "risque")),
        "reversibilite": _texte(_valeur_source(ligne, "reversibilite")) or None,
        "complexite": _nombre_scenario(_valeur_source(ligne, "complexite")),
    }


def _ecarts_scenario(reference: Mapping[str, Any], scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Calcule des écarts déterministes ; ``None`` reste ``None``, sans faux zéro."""
    ecarts: dict[str, Any] = {}
    for nom in _METRIQUES_SCENARIO:
        valeur_reference = reference.get(nom)
        valeur = scenario.get(nom)
        delta = delta_pct = sens = None
        if valeur_reference is not None and valeur is not None:
            delta = round(float(valeur) - float(valeur_reference), 6)
            if float(valeur_reference) != 0.0:
                delta_pct = round(delta / float(valeur_reference) * 100.0, 2)
            sens = "identique" if delta == 0 else ("hausse" if delta > 0 else "baisse")
        ecarts[nom] = {"delta": delta, "delta_pct": delta_pct, "sens": sens}
    for nom in ("reversibilite", "statut"):
        reference_valeur = reference.get(nom)
        scenario_valeur = scenario.get(nom)
        ecarts[nom] = {
            "reference": reference_valeur,
            "scenario": scenario_valeur,
            "identique": (
                reference_valeur == scenario_valeur
                if reference_valeur is not None and scenario_valeur is not None
                else None
            ),
        }
    return ecarts


def _avec_ecarts(
    reference: Mapping[str, Any], scenario: Mapping[str, Any],
) -> dict[str, Any]:
    return {**scenario, "ecarts": _ecarts_scenario(reference, scenario)}


def _chaine_scenario(
    parents: list[Any], resultat: ResultatTransition,
) -> ResultatTransition:
    """Conserve la chaîne complète relue, avec repli parents immédiats et dédoublonnage."""
    sources = list(resultat.chaine or [])
    if not sources or (len(sources) == 1 and parents):
        sources = [*parents, *sources]
    if not sources:
        sources = [resultat.objet]
    chaine: list[dict[str, Any]] = []
    vus: set[str] = set()
    for objet in sources:
        identifiant = _texte(_valeur_source(objet, "id"))
        if not identifiant or identifiant in vus:
            continue
        vus.add(identifiant)
        chaine.append(_nettoyer(objet) if isinstance(objet, Mapping) else objet)
    identifiant_scenario = _texte(_valeur_source(resultat.objet, "id"))
    if identifiant_scenario and identifiant_scenario not in vus:
        chaine.append(resultat.objet)
    return ResultatTransition(
        objet=resultat.objet, chaine=chaine, historique=resultat.historique)


def creer_scenario(
    depot: BoucleStore, conn: Any, tenant_id: str, **champs: Any,
) -> ResultatTransition:
    """Crée un Scénario rattaché à une Investigation et/ou une Decision du tenant."""
    investigation_id = _texte(champs.pop("investigation_id", None))
    decision_id = _texte(champs.pop("decision_id", None))
    if not investigation_id and not decision_id:
        raise TransitionRefusee("un scénario exige investigation_id ou decision_id")

    parents: list[Any] = []
    with depot.transaction(conn):
        investigation = None
        decision = None
        if investigation_id:
            investigation = _source(
                depot, conn, tenant_id, investigation_id,
                "INVESTIGATION", "investigation")
            parents.append(investigation)
        if decision_id:
            decision = _source(
                depot, conn, tenant_id, decision_id, "DECISION", "decision")
            parents.append(decision)
        decision_investigation = (
            _texte(_valeur_source(decision, "investigation_id"))
            or _texte(_valeur_source(decision, "investigation_ref"))
        ) if decision is not None else ""
        if investigation_id and decision_investigation and decision_investigation != investigation_id:
            raise TransitionRefusee(
                f"la décision {decision_id!r} appartient à l'investigation "
                f"{decision_investigation!r}, pas à {investigation_id!r}"
            )
        investigation_reference = investigation_id or decision_investigation
        hypotheses = champs.get("hypothesis_ids") or []
        if isinstance(hypotheses, str):
            hypotheses = [hypotheses]
        for hypothesis_id in hypotheses:
            identifiant_hypothese = _texte(hypothesis_id)
            if not identifiant_hypothese:
                continue
            hypothesis = depot.lire_boucle(
                conn, tenant_id, identifiant_hypothese, as_dict=True)
            if hypothesis is None:
                raise SourceIntrouvable("hypothesis", identifiant_hypothese)
            if _texte(_valeur_source(hypothesis, "type")).upper() != "HYPOTHESIS":
                raise TransitionRefusee(
                    f"hypothesis {identifiant_hypothese!r} n'est pas une hypothèse")
            hypothesis_investigation = _texte(
                _valeur_source(hypothesis, "investigation_id"))
            if not investigation_reference or (
                hypothesis_investigation
                and hypothesis_investigation != investigation_reference
            ):
                raise TransitionRefusee(
                    f"l'hypothèse {identifiant_hypothese!r} n'appartient pas "
                    f"à l'investigation {investigation_reference or 'du scénario'!r}"
                )
        identifiant = _texte(champs.pop("id", None)) or f"scenario-{uuid.uuid4().hex[:12]}"
        objet = depot.nouveau_scenario(
            investigation=investigation, decision=decision,
            tenant_id=tenant_id, id=identifiant, **champs)
        depot.enregistrer_objets(conn, tenant_id, objets=[objet], as_dict=False)
        resultat = _relire(depot, conn, tenant_id, identifiant)
        parents_relus = []
        for parent in parents:
            parent_id = _texte(_valeur_source(parent, "id"))
            frais = depot.lire_boucle(conn, tenant_id, parent_id, as_dict=True)
            parents_relus.append(frais or parent)
    return _chaine_scenario(parents_relus, resultat)


def lister_scenarios(
    depot: BoucleStore, conn: Any, tenant_id: str, *,
    investigation_id: Any = None, decision_id: Any = None, limite: int = 100,
) -> list[dict[str, Any]]:
    """Liste les Scénarios du tenant, filtrés par Investigation et/ou Decision."""
    lignes = depot.lister_objets_exploitation(
        conn, tenant_id, type_="SCENARIO",
        investigation_id=_texte(investigation_id) or None,
        decision_id=_texte(decision_id) or None,
        limite=limite, as_dict=True,
    )
    return [_resume_scenario(ligne) for ligne in lignes]


def comparer_scenarios(
    depot: BoucleStore, conn: Any, tenant_id: str, scenario_ids: Any,
    reference_id: Any = None,
) -> dict[str, Any]:
    """Compare des Scénarios du tenant à une référence, sans simulation inventée.

    ``application.planification.scenario.comparer`` simule des deltas de capacité et de
    prévision : son mapping vers les attributs canoniques n'est pas fidèle. La comparaison
    reste donc déterministe sur valeur, coût, délai, complexité, risque, réversibilité et
    statut, avec des écarts ``None`` dès qu'une donnée manque.
    """
    ids = [_texte(element) for element in (scenario_ids or [])]
    ids = [element for element in ids if element]
    if len(ids) < 2:
        raise TransitionRefusee("au moins deux scénarios sont nécessaires pour comparer")
    if len(set(ids)) != len(ids):
        raise TransitionRefusee("identifiants de scénarios dupliqués")
    reference = _texte(reference_id) or ids[0]
    if reference not in ids:
        raise TransitionRefusee("la référence doit appartenir aux scénarios comparés")

    resumes: list[dict[str, Any]] = []
    for identifiant in ids:
        ligne = depot.lire_boucle(conn, tenant_id, identifiant, as_dict=True)
        if ligne is None or _texte(_valeur_source(ligne, "type")).upper() != "SCENARIO":
            raise SourceIntrouvable("scénario", identifiant)
        resumes.append(_resume_scenario(ligne))

    reference_resume = next(
        scenario for scenario in resumes if scenario["id"] == reference)
    return {
        "reference": reference_resume,
        "scenarios": [
            _avec_ecarts(reference_resume, scenario) for scenario in resumes
        ],
    }
