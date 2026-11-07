"""Boucle P1 canonique : Situation → Investigation → Decision → Initiative → Outcome → Learning.

Ce module ne fait ni réseau ni agent. Il construit des objets canoniques reliés, valide leurs transitions et les
persiste via :mod:`meridian.adapters.outbound.postgres.entreprise_depot`. Un Outcome exige une mesure et une
Initiative ; un Learning exige un Outcome mesuré ou une Investigation. Tous les objets d'une boucle appartiennent
au même tenant.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
import copy
import uuid
from typing import Any

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import objets_exploitation
from meridian.domain import modele_entreprise as modele
from meridian.domain.construction_objets_exploitation import nouveau_scenario as _nouveau_scenario
from meridian.domain.objets_exploitation import Scenario
from meridian.domain.mesure import mesure_renseignee as _mesure_renseignee

__all__ = [
    "BoucleInvalide", "TYPES_BOUCLE", "STATUT_DECISION_PROPOSEE", "STATUT_DECISION_TRANCHEE",
    "STATUT_INITIATIVE", "STATUT_OUTCOME", "STATUT_LEARNING",
    "Situation", "Investigation", "Decision", "Scenario", "Initiative", "Outcome", "Learning",
    "est_decision_tranchee",
    "ouvrir_investigation", "proposer_decision", "trancher_decision", "lancer_initiative",
    "mesurer_outcome", "capitaliser_learning",
    "enregistrer_boucle", "lire_boucle", "lire_par_id",
    "transaction", "nouvelle_situation", "donnees_de", "fusionner_donnees",
    "nouveau_scenario", "enregistrer_objets", "lister_objets_exploitation",
]

TYPES_BOUCLE = (
    "SITUATION", "INVESTIGATION", "DECISION", "SCENARIO",
    "INITIATIVE", "OUTCOME", "LEARNING",
)
STATUT_DECISION_PROPOSEE = "PROPOSED"
STATUT_DECISION_TRANCHEE = "DECIDED"
STATUT_INITIATIVE = "PLANNED"
STATUT_OUTCOME = "OBSERVED"
STATUT_LEARNING = "PROPOSED"

_ORDRE = {type_: rang for rang, type_ in enumerate(TYPES_BOUCLE)}
_MODE_DEFAUT = {
    "SITUATION": "OBSERVED",
    "INVESTIGATION": "DECLARED",
    "DECISION": "DECLARED",
    "SCENARIO": "PROPOSED",
    "INITIATIVE": "DECLARED",
    "OUTCOME": "OBSERVED",
    "LEARNING": "INFERRED",
}
_CHAMPS_TABLE = frozenset({
    "id", "tenant_id", "famille", "type", "mode", "titre", "donnees", "version",
    "observe_le", "valide_depuis", "valide_jusqua", "cree_le", "maj_le",
})
_CHAMPS_DATES = ("cree_le", "observe_le", "valide_depuis", "valide_jusqua")
_MAX_HISTORIQUE = 50

# Liens inverses maintenus par les autres producteurs (B) et par A : un parent
# fraîchement construit ne doit pas les effacer avec ses valeurs par défaut.
_CHAMPS_INVERSES_LIES = frozenset({
    "signal_ids", "expression_id", "opportunity_ids", "risk_ids",
    "hypothesis_ids", "expert_ids", "scenario_ids",
    "scenario_id", "initiative_id", "outcome_ids", "scenarios_rejetes",
})


class BoucleInvalide(modele.ModeleInvalide):
    """Une étape de la boucle ne respecte pas ses liens, son tenant ou son état."""


class _LiensBoucle:
    """Expose les liens et les dates portés par un objet, sans dupliquer les champs."""

    CHAMPS_LIENS: tuple[str, ...] = ()
    CHAMPS_LIENS_MULTIPLES: tuple[str, ...] = ()

    @property
    def tenant(self) -> str:
        return self.tenant_id

    @property
    def liens(self) -> dict[str, Any]:
        liens: dict[str, Any] = {}
        for nom in self.CHAMPS_LIENS:
            valeur = getattr(self, nom, None)
            if valeur:
                liens[nom] = valeur
        for nom in self.CHAMPS_LIENS_MULTIPLES:
            valeur = getattr(self, nom, None)
            if valeur:
                liens[nom] = list(valeur)
        return liens

    @property
    def dates(self) -> dict[str, Any]:
        return {nom: getattr(self, nom, None) for nom in _CHAMPS_DATES if getattr(self, nom, None)}


def _texte(valeur: Any, champ: str | None = None, *, obligatoire: bool = False) -> str:
    texte = "" if valeur is None else str(valeur).strip()
    if obligatoire and not texte:
        raise BoucleInvalide(f"{champ or 'valeur'} obligatoire")
    return texte


def _texte_ou_none(valeur: Any) -> str | None:
    texte = _texte(valeur)
    return texte or None


def _liste_textes(valeur: Any, champ: str) -> list[str]:
    if valeur is None:
        return []
    elements = [valeur] if isinstance(valeur, (str, Mapping)) or not isinstance(valeur, Iterable) else list(valeur)
    resultat: list[str] = []
    for element in elements:
        texte = _texte(element)
        if not texte:
            continue
        if texte not in resultat:
            resultat.append(texte)
    return resultat


def _liste_ids(valeur: Any, champ: str) -> list[str]:
    if valeur is None:
        return []
    elements = [valeur] if isinstance(valeur, (str, Mapping)) or not isinstance(valeur, Iterable) else list(valeur)
    resultat: list[str] = []
    for element in elements:
        if isinstance(element, Mapping):
            element = element.get("id")
        texte = _texte(element)
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def _instant(valeur: Any = None) -> str:
    if valeur is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    texte = _texte(valeur)
    if not texte:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return texte


def _dater(objet: Any) -> None:
    instant = _instant()
    for champ in ("cree_le", "observe_le", "valide_depuis"):
        if not getattr(objet, champ, None):
            setattr(objet, champ, instant)


def _normaliser_statut(valeur: Any) -> str:
    return _texte(valeur).upper()


def _est_tranchee_statut(valeur: Any) -> bool:
    return _normaliser_statut(valeur) in {"DECIDED", "TRANCHEE", "TRANCHÉE", "TRANCHE"}


def est_decision_tranchee(decision: Any) -> bool:
    """Vrai si la décision porte un statut de décision tranchée."""
    return _est_tranchee_statut(_valeur(decision, "statut"))


def _valeur_mesure(mesure: Any) -> Any:
    if isinstance(mesure, Mapping):
        for cle in ("valeur_observee", "valeur", "observed_value", "value", "resultat", "résultat"):
            if cle in mesure and mesure[cle] is not None:
                return mesure[cle]
        return None
    if isinstance(mesure, bool):
        return mesure
    if isinstance(mesure, (str, int, float)):
        return mesure
    return None


def _metrique_mesure(mesure: Any) -> str | None:
    if isinstance(mesure, Mapping):
        for cle in ("metrique", "metric", "indicateur", "mesure"):
            if valeur := _texte_ou_none(mesure.get(cle)):
                return valeur
    return None


def _jsonable(valeur: Any) -> Any:
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        return valeur
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Enum):
        return _jsonable(valeur.value)
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return _jsonable(asdict(valeur))
    if isinstance(valeur, Mapping):
        return {str(cle): _jsonable(element) for cle, element in valeur.items()}
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_jsonable(element) for element in valeur]
    return str(valeur)


def _valeur(objet: Any, nom: str, defaut: Any = None) -> Any:
    if objet is None:
        return defaut
    if isinstance(objet, Mapping):
        if nom in objet:
            return objet[nom]
        donnees = objet.get("donnees")
        if isinstance(donnees, Mapping) and nom in donnees:
            return donnees[nom]
        return defaut
    return getattr(objet, nom, defaut)


def _id_de(objet: Any) -> str:
    return _texte(_valeur(objet, "id"), "id", obligatoire=True)


def _tenant_de(objet: Any) -> str:
    return _texte(_valeur(objet, "tenant_id") or _valeur(objet, "tenant"), "tenant_id", obligatoire=True)


def _type_de(objet: Any) -> str:
    return _normaliser_statut(_valeur(objet, "type") or _valeur(objet, "type_") or _valeur(objet, "type_objet"))


def _exiger_type(objet: Any, attendu: str, role: str) -> None:
    if objet is None:
        raise BoucleInvalide(f"{role} obligatoire")
    trouve = _type_de(objet)
    if trouve != attendu:
        raise BoucleInvalide(f"{role} doit être de type {attendu} (reçu {trouve or 'inconnu'})")
    _id_de(objet)


def _verifier_tenant(source: Any, tenant_id: Any = None) -> str:
    tenant_source = _tenant_de(source)
    if tenant_id is None:
        return tenant_source
    tenant = _texte(tenant_id, "tenant_id", obligatoire=True)
    if tenant != tenant_source:
        raise BoucleInvalide(
            f"tenants incompatibles : {tenant!r} demandé, objet du tenant {tenant_source!r}"
        )
    return tenant


def _nouvel_id(prefixe: str) -> str:
    return f"{prefixe.lower()}-{uuid.uuid4().hex[:12]}"


def _valeur_source(objet: Any) -> dict[str, Any]:
    if isinstance(objet, Mapping):
        valeurs = dict(objet.get("donnees") or {}) if isinstance(objet.get("donnees"), Mapping) else {}
        valeurs.update({cle: valeur for cle, valeur in objet.items() if cle != "donnees"})
        return valeurs
    if is_dataclass(objet) and not isinstance(objet, type):
        return asdict(objet)
    return {}


def _construire(classe: type, source: Any, **remplacements: Any) -> Any:
    noms = {champ.name for champ in fields(classe)}
    valeurs = {cle: valeur for cle, valeur in _valeur_source(source).items() if cle in noms}
    for cle, valeur in remplacements.items():
        if valeur is not None and cle in noms:
            valeurs[cle] = valeur
    return classe(**valeurs)


@dataclass
class Situation(modele.Situation, _LiensBoucle):
    """Phénomène observé qui ouvre la boucle ; il peut relier plusieurs Twins, signaux et Claims."""

    mode: str = "OBSERVED"
    resume: str = ""

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume) or _texte(self.description)
        if not self.description:
            self.description = self.resume
        _dater(self)
        super().__post_init__()


@dataclass
class Investigation(modele.Investigation, _LiensBoucle):
    """Investigation reliée à une Situation et portant la question à instruire."""

    mode: str = "DECLARED"
    resume: str = ""
    situation_id: str | None = None
    incertitudes: list[str] = field(default_factory=list)
    CHAMPS_LIENS = ("situation_id",)

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume) or _texte(self.synthese) or _texte(self.question)
        _dater(self)
        super().__post_init__()
        self.situation_id = _texte_ou_none(self.situation_id)
        if not self.situation_id:
            raise BoucleInvalide("une Investigation exige situation_id")
        self.incertitudes = _liste_textes(self.incertitudes, "incertitudes")


@dataclass
class Decision(modele.Decision, _LiensBoucle):
    """Décision proposée puis tranchée par un acteur, reliée à une Investigation."""

    mode: str = "DECLARED"
    titre: str = ""
    resume: str = ""
    situation_id: str | None = None
    choix: str | None = None
    acteur: str | None = None
    incertitudes: list[str] = field(default_factory=list)
    CHAMPS_LIENS = ("situation_id", "investigation_id", "initiative_id")
    CHAMPS_LIENS_MULTIPLES = ("scenario_ids", "scenarios_rejetes")

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume) or _texte(self.rationale)
        if not self.titre:
            self.titre = _texte(self.resume) or _texte(self.rationale) or "Décision"
        _dater(self)
        super().__post_init__()
        self.situation_id = _texte_ou_none(self.situation_id)
        self.choix = _texte_ou_none(self.choix)
        self.acteur = _texte_ou_none(self.acteur)
        self.incertitudes = _liste_textes(self.incertitudes, "incertitudes")
        if _est_tranchee_statut(self.statut):
            if not self.acteur:
                raise BoucleInvalide("une décision tranchée exige un acteur")
            if not self.choix:
                raise BoucleInvalide("une décision tranchée exige un choix")
            if not self.decide_le:
                raise BoucleInvalide("une décision tranchée exige une date de décision")


@dataclass
class Initiative(modele.Initiative, _LiensBoucle):
    """Action lancée après une décision tranchée, destinée à produire un Outcome mesuré."""

    mode: str = "DECLARED"
    resume: str = ""
    situation_id: str | None = None
    CHAMPS_LIENS = ("situation_id", "decision_id")
    CHAMPS_LIENS_MULTIPLES = ("outcome_ids",)

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume)
        if not self.titre:
            self.titre = _texte(self.resume) or "Initiative"
        _dater(self)
        super().__post_init__()
        self.situation_id = _texte_ou_none(self.situation_id)
        if not _texte(self.decision_id):
            raise BoucleInvalide("une Initiative exige decision_id")


@dataclass
class Outcome(modele.Outcome, _LiensBoucle):
    """Résultat observé après une Initiative ; la mesure est obligatoire."""

    mode: str = "OBSERVED"
    titre: str = ""
    resume: str = ""
    mesure: Any = None
    mesure_le: str | None = None
    periode: str = ""
    CHAMPS_LIENS = ("initiative_id",)

    @property
    def measure(self) -> Any:
        return self.mesure

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume) or _texte(self.interpretation)
        _dater(self)
        if not _mesure_renseignee(self.mesure):
            if self.valeur_observee is not None:
                self.mesure = {"valeur_observee": self.valeur_observee}
            else:
                raise BoucleInvalide("un Outcome exige une mesure")
        self.mesure = _jsonable(self.mesure)
        if not _mesure_renseignee(self.mesure):
            raise BoucleInvalide("un Outcome exige une mesure non vide")
        if not self.metrique:
            self.metrique = _metrique_mesure(self.mesure) or ""
        if self.valeur_observee is None:
            self.valeur_observee = _valeur_mesure(self.mesure)
        super().__post_init__()
        if not self.titre:
            self.titre = _texte(self.metrique) or _texte(self.resume) or "Outcome"
        self.mesure_le = _instant(self.mesure_le) if self.mesure_le else self.observe_le
        self.periode = _texte(self.periode)


@dataclass
class Learning(modele.Learning, _LiensBoucle):
    """Leçon généralisable issue d'un Outcome mesuré ou d'une Investigation."""

    mode: str = "INFERRED"
    titre: str = ""
    resume: str = ""
    situation_id: str | None = None
    CHAMPS_LIENS = ("situation_id",)
    CHAMPS_LIENS_MULTIPLES = ("outcome_ids", "investigation_ids")

    def __post_init__(self) -> None:
        self.resume = _texte(self.resume) or _texte(self.enonce)
        if not self.enonce:
            self.enonce = self.resume
        if not self.titre:
            self.titre = _texte(self.enonce) or "Learning"
        _dater(self)
        super().__post_init__()
        self.situation_id = _texte_ou_none(self.situation_id)
        if not _texte(self.enonce):
            raise BoucleInvalide("un Learning exige un énoncé")


_CLASSES = {
    "SITUATION": Situation,
    "INVESTIGATION": Investigation,
    "DECISION": Decision,
    "SCENARIO": Scenario,
    "INITIATIVE": Initiative,
    "OUTCOME": Outcome,
    "LEARNING": Learning,
}


def ouvrir_investigation(
    situation: Any, *, id: str | None = None, tenant_id: str | None = None,
    titre: str | None = None, question: str | None = None, resume: str | None = None,
    statut: str = "OPEN", preuves: Any = None, mode: str = "DECLARED", **champs: Any,
) -> Investigation:
    """Ouvre une Investigation reliée à une Situation du même tenant."""
    _exiger_type(situation, "SITUATION", "situation")
    tenant = _verifier_tenant(situation, tenant_id)
    situation_id = _id_de(situation)
    question_finale = (
        _texte(question) or _texte(_valeur(situation, "description"))
        or _texte(_valeur(situation, "titre")) or "Comprendre la situation"
    )
    valeurs = {
        "id": _texte(id) or _nouvel_id("investigation"),
        "tenant_id": tenant,
        "titre": _texte(titre) or _texte(_valeur(situation, "titre")) or question_finale,
        "question": question_finale,
        "resume": _texte(resume),
        "situation_id": situation_id,
        "statut": _normaliser_statut(statut) or "OPEN",
        "mode": mode,
    }
    if preuves is not None:
        valeurs["preuves"] = preuves
    valeurs.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    return Investigation(**valeurs)


def proposer_decision(
    investigation: Any, options: Any, criteres: Any = None, incertitudes: Any = None,
    *, id: str | None = None, tenant_id: str | None = None, titre: str | None = None,
    resume: str | None = None, preuves: Any = None, mode: str = "DECLARED", **champs: Any,
) -> Decision:
    """Propose une Decision non tranchée, reliée à une Investigation du même tenant."""
    _exiger_type(investigation, "INVESTIGATION", "investigation")
    tenant = _verifier_tenant(investigation, tenant_id)
    options_normalisees = _liste_textes(options, "options")
    if not options_normalisees:
        raise BoucleInvalide("une décision exige au moins une option")
    investigation_id = _id_de(investigation)
    situation_id = _texte_ou_none(_valeur(investigation, "situation_id"))
    valeurs = {
        "id": _texte(id) or _nouvel_id("decision"),
        "tenant_id": tenant,
        "titre": _texte(titre) or f"Décider — {_texte(_valeur(investigation, 'titre')) or investigation_id}",
        "resume": _texte(resume),
        "investigation_id": investigation_id,
        "situation_id": situation_id,
        "options": options_normalisees,
        "criteres": _liste_textes(criteres, "criteres"),
        "incertitudes": _liste_textes(incertitudes, "incertitudes"),
        "statut": STATUT_DECISION_PROPOSEE,
        "mode": mode,
    }
    if preuves is not None:
        valeurs["preuves"] = preuves
    valeurs.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    return Decision(**valeurs)


def trancher_decision(
    decision: Any, acteur: str, choix: str, *, motif: str | None = None,
    rationale: str | None = None, preuves: Any = None, decide_le: Any = None,
    mode: str | None = None, tenant_id: str | None = None, **champs: Any,
) -> Decision:
    """Tranche une Decision proposée ; l'objet source n'est pas muté."""
    _exiger_type(decision, "DECISION", "décision")
    _verifier_tenant(decision, tenant_id)
    acteur_final = _texte(acteur, "acteur", obligatoire=True)
    choix_final = _texte(choix, "choix", obligatoire=True)
    if est_decision_tranchee(decision):
        raise BoucleInvalide("décision déjà tranchée : transition refusée")
    options = _liste_textes(_valeur(decision, "options"), "options")
    if options and not any(choix_final.casefold() == option.casefold() for option in options):
        raise BoucleInvalide(f"choix {choix_final!r} absent des options {options!r}")
    remplacements: dict[str, Any] = {
        "statut": STATUT_DECISION_TRANCHEE,
        "acteur": acteur_final,
        "choix": choix_final,
        "decide_le": _instant(decide_le),
    }
    if rationale is not None or motif is not None:
        valeur = _texte(rationale if rationale is not None else motif)
        if valeur:
            remplacements["rationale"] = valeur
    if preuves is not None:
        remplacements["preuves"] = preuves
    if mode is not None:
        remplacements["mode"] = mode
    remplacements.update(champs)
    return _construire(Decision, decision, **remplacements)


def lancer_initiative(
    decision: Any, *, id: str | None = None, tenant_id: str | None = None,
    titre: str | None = None, resume: str | None = None, statut: str = STATUT_INITIATIVE,
    outcome_attendu_ids: Any = None, preuves: Any = None, mode: str = "DECLARED",
    **champs: Any,
) -> Initiative:
    """Lance une Initiative reliée à une décision tranchée du même tenant."""
    _exiger_type(decision, "DECISION", "décision")
    tenant = _verifier_tenant(decision, tenant_id)
    if not est_decision_tranchee(decision):
        raise BoucleInvalide("décision non tranchée : initiative refusée")
    decision_id = _id_de(decision)
    situation_id = _texte_ou_none(_valeur(decision, "situation_id"))
    valeurs = {
        "id": _texte(id) or _nouvel_id("initiative"),
        "tenant_id": tenant,
        "titre": _texte(titre) or _texte(_valeur(decision, "titre")) or f"Initiative — {decision_id}",
        "resume": _texte(resume),
        "decision_id": decision_id,
        "situation_id": situation_id,
        "statut": _normaliser_statut(statut) or STATUT_INITIATIVE,
        "outcome_attendu_ids": _liste_ids(outcome_attendu_ids, "outcome_attendu_ids"),
        "mode": mode,
    }
    if preuves is not None:
        valeurs["preuves"] = preuves
    valeurs.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    return Initiative(**valeurs)


def mesurer_outcome(
    initiative: Any, mesure: Any, *, id: str | None = None, tenant_id: str | None = None,
    titre: str | None = None, resume: str | None = None, metrique: str | None = None,
    valeur_attendue: Any = None, interpretation: str | None = None,
    preuves: Any = None, mesure_le: Any = None, periode: str = "",
    statut: str = STATUT_OUTCOME, mode: str = "OBSERVED", **champs: Any,
) -> Outcome:
    """Mesure un Outcome rattaché à une Initiative du même tenant ; aucune mesure n'est inventée."""
    _exiger_type(initiative, "INITIATIVE", "initiative")
    tenant = _verifier_tenant(initiative, tenant_id)
    if not _mesure_renseignee(mesure):
        raise BoucleInvalide("un Outcome exige une mesure non vide")
    initiative_id = _id_de(initiative)
    metrique_finale = _texte(metrique) or _metrique_mesure(mesure) or ""
    valeurs = {
        "id": _texte(id) or _nouvel_id("outcome"),
        "tenant_id": tenant,
        "titre": _texte(titre) or metrique_finale or f"Outcome — {initiative_id}",
        "resume": _texte(resume),
        "initiative_id": initiative_id,
        "mesure": _jsonable(mesure),
        "metrique": metrique_finale,
        "valeur_attendue": valeur_attendue,
        "valeur_observee": _valeur_mesure(mesure),
        "interpretation": _texte(interpretation),
        "mesure_le": _instant(mesure_le) if mesure_le is not None else None,
        "periode": _texte(periode),
        "statut": _normaliser_statut(statut) or STATUT_OUTCOME,
        "mode": mode,
    }
    if preuves is not None:
        valeurs["preuves"] = preuves
    valeurs.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    return Outcome(**valeurs)


def _a_mesure(objet: Any) -> bool:
    if _mesure_renseignee(_valeur(objet, "mesure")):
        return True
    return _valeur(objet, "valeur_observee") is not None


def capitaliser_learning(
    source: Any, *, id: str | None = None, tenant_id: str | None = None,
    titre: str | None = None, enonce: str | None = None, resume: str | None = None,
    scope: str = "", conditions_applicabilite: Any = None, preuves: Any = None,
    statut: str = STATUT_LEARNING, mode: str = "INFERRED", **champs: Any,
) -> Learning:
    """Capitalise un Learning depuis un Outcome mesuré et/ou une Investigation du même tenant."""
    sources = list(source) if isinstance(source, (list, tuple, set, frozenset)) else [source]
    if not sources or any(element is None for element in sources):
        raise BoucleInvalide("un Learning exige un Outcome ou une Investigation source")
    tenant: str | None = None
    outcome_ids: list[str] = []
    investigation_ids: list[str] = []
    for element in sources:
        type_source = _type_de(element)
        if type_source not in {"OUTCOME", "INVESTIGATION"}:
            raise BoucleInvalide(
                f"un Learning ne peut venir que d'un Outcome ou d'une Investigation (reçu {type_source or 'inconnu'})"
            )
        tenant_source = _verifier_tenant(element, tenant_id if tenant is None else tenant)
        tenant = tenant_source
        if type_source == "OUTCOME":
            if not _a_mesure(element):
                raise BoucleInvalide("un Learning issu d'un Outcome exige un Outcome mesuré")
            identifiant = _id_de(element)
            if identifiant not in outcome_ids:
                outcome_ids.append(identifiant)
        else:
            identifiant = _id_de(element)
            if identifiant not in investigation_ids:
                investigation_ids.append(identifiant)
    if not outcome_ids and not investigation_ids:
        raise BoucleInvalide("un Learning exige un Outcome ou une Investigation source")
    enonce_final = _texte(enonce) or _texte(resume)
    if not enonce_final:
        raise BoucleInvalide("un Learning exige un énoncé")
    valeurs = {
        "id": _texte(id) or _nouvel_id("learning"),
        "tenant_id": tenant,
        "titre": _texte(titre) or enonce_final,
        "resume": _texte(resume) or enonce_final,
        "enonce": enonce_final,
        "scope": _texte(scope),
        "outcome_ids": outcome_ids,
        "investigation_ids": investigation_ids,
        "conditions_applicabilite": _liste_textes(conditions_applicabilite, "conditions_applicabilite"),
        "statut": _normaliser_statut(statut) or STATUT_LEARNING,
        "mode": mode,
    }
    if preuves is not None:
        valeurs["preuves"] = preuves
    valeurs.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    return Learning(**valeurs)


def _ressemble_objet(valeur: Mapping) -> bool:
    return "id" in valeur and ("type" in valeur or "famille" in valeur)


def _cle_tri(objet: Any) -> tuple[int, str]:
    return (_ORDRE.get(_type_de(objet), len(_ORDRE)), _id_de(objet))


def _payload_objet(objet: Any) -> dict[str, Any]:
    if isinstance(objet, Mapping):
        charge = copy.deepcopy(dict(objet))
    elif is_dataclass(objet) and not isinstance(objet, type):
        convertisseur = getattr(objet, "to_dict", None) or getattr(objet, "as_dict", None)
        charge = copy.deepcopy(convertisseur() if callable(convertisseur) else asdict(objet))
    else:
        raise BoucleInvalide("objet de boucle attendu")

    type_objet = _type_de(charge)
    if type_objet not in _ORDRE:
        raise BoucleInvalide(f"type hors boucle : {type_objet or 'inconnu'}")
    charge["type"] = type_objet
    if not charge.get("famille"):
        charge["famille"] = modele.famille_de(type_objet)
    if not charge.get("mode"):
        charge["mode"] = _MODE_DEFAUT[type_objet]
    if "titre" not in charge:
        charge["titre"] = ""
    if charge.get("version") == 1:
        charge.pop("version", None)
    donnees = charge.get("donnees")
    if not isinstance(donnees, Mapping):
        donnees = {
            cle: valeur for cle, valeur in charge.items()
            if cle not in _CHAMPS_TABLE and cle != "donnees"
        }
    charge["donnees"] = dict(donnees)
    return charge


def _source_attendue(type_objet: str) -> tuple[str, str] | None:
    return {
        "INVESTIGATION": ("situation_id", "SITUATION"),
        "DECISION": ("investigation_id", "INVESTIGATION"),
        "INITIATIVE": ("decision_id", "DECISION"),
        "OUTCOME": ("initiative_id", "INITIATIVE"),
    }.get(type_objet)


def _resoudre_source(
    conn: Any, tenant: str, par_id: Mapping[str, Any], source_id: Any,
    champ: str, type_attendu: str,
) -> Any:
    identifiant = _texte_ou_none(source_id)
    if not identifiant:
        raise BoucleInvalide(f"{champ} obligatoire")
    source = par_id.get(identifiant)
    if source is None:
        source = entreprise_depot.lire_objet(conn, tenant, identifiant)
    if source is None:
        raise BoucleInvalide(f"{champ} introuvable : {identifiant}")
    if _type_de(source) != type_attendu:
        raise BoucleInvalide(
            f"{champ} doit référencer un {type_attendu}, pas un {_type_de(source) or 'type inconnu'}"
        )
    if _tenant_de(source) != tenant:
        raise BoucleInvalide(f"{champ} appartient à un autre tenant")
    return source


def _valider_pour_persistance(conn: Any, tenant: str, objets: list[Any]) -> None:
    par_id = {_id_de(objet): objet for objet in objets}
    if len(par_id) != len(objets):
        raise BoucleInvalide("identifiants dupliqués dans la boucle")
    for objet in objets:
        type_objet = _type_de(objet)
        if type_objet not in _ORDRE:
            raise BoucleInvalide(f"type hors boucle : {type_objet or 'inconnu'}")
        if _tenant_de(objet) != tenant:
            raise BoucleInvalide(
                f"objet {_id_de(objet)} du tenant {_tenant_de(objet)!r}, attendu {tenant!r}"
            )
        attendu = _source_attendue(type_objet)
        if attendu is not None:
            champ, type_source = attendu
            _resoudre_source(conn, tenant, par_id, _valeur(objet, champ), champ, type_source)
        if type_objet == "SCENARIO":
            investigation_id = _texte_ou_none(_valeur(objet, "investigation_id"))
            decision_id = _texte_ou_none(_valeur(objet, "decision_id"))
            if not investigation_id and not decision_id:
                raise BoucleInvalide("un scénario exige investigation_id ou decision_id")
            if investigation_id:
                _resoudre_source(
                    conn, tenant, par_id, investigation_id,
                    "investigation_id", "INVESTIGATION")
            decision_investigation = None
            if decision_id:
                decision = _resoudre_source(
                    conn, tenant, par_id, decision_id, "decision_id", "DECISION")
                decision_investigation = _lien_ou_alias(
                    decision, "investigation_id", "investigation_ref")
                if (
                    investigation_id and decision_investigation
                    and decision_investigation != investigation_id
                ):
                    raise BoucleInvalide(
                        f"la décision {decision_id!r} appartient à l'investigation "
                        f"{decision_investigation!r}, pas à {investigation_id!r}"
                    )
            investigation_reference = investigation_id or decision_investigation
            for hypothesis_id in _liste_ids(
                _valeur(objet, "hypothesis_ids"), "hypothesis_ids"
            ):
                hypothesis = _resoudre_source(
                    conn, tenant, par_id, hypothesis_id,
                    "hypothesis_ids", "HYPOTHESIS")
                hypothesis_investigation = _texte_ou_none(
                    _valeur(hypothesis, "investigation_id"))
                if (
                    investigation_reference and hypothesis_investigation
                    and hypothesis_investigation != investigation_reference
                ):
                    raise BoucleInvalide(
                        f"l'hypothèse {hypothesis_id!r} appartient à l'investigation "
                        f"{hypothesis_investigation!r}, pas à {investigation_reference!r}"
                    )
        if type_objet == "DECISION" and est_decision_tranchee(objet):
            for champ in ("acteur", "choix", "decide_le"):
                if not _valeur(objet, champ):
                    raise BoucleInvalide(f"décision tranchée sans {champ}")
        if type_objet == "INITIATIVE":
            decision = _resoudre_source(
                conn, tenant, par_id, _valeur(objet, "decision_id"), "decision_id", "DECISION"
            )
            if not est_decision_tranchee(decision):
                raise BoucleInvalide("décision non tranchée : initiative refusée")
        if type_objet == "OUTCOME":
            _resoudre_source(
                conn, tenant, par_id, _valeur(objet, "initiative_id"), "initiative_id", "INITIATIVE"
            )
            if not _a_mesure(objet):
                raise BoucleInvalide("un Outcome exige une mesure")
        if type_objet == "LEARNING":
            outcome_ids = _liste_ids(_valeur(objet, "outcome_ids"), "outcome_ids")
            investigation_ids = _liste_ids(_valeur(objet, "investigation_ids"), "investigation_ids")
            if not outcome_ids and not investigation_ids:
                raise BoucleInvalide("un Learning exige un Outcome ou une Investigation source")
            for identifiant in outcome_ids:
                outcome = _resoudre_source(
                    conn, tenant, par_id, identifiant, "outcome_ids", "OUTCOME"
                )
                if not _a_mesure(outcome):
                    raise BoucleInvalide("un Learning issu d'un Outcome exige un Outcome mesuré")
            for identifiant in investigation_ids:
                _resoudre_source(
                    conn, tenant, par_id, identifiant, "investigation_ids", "INVESTIGATION"
                )


def _entree_historique(ligne: Mapping[str, Any]) -> dict[str, Any]:
    donnees = {
        cle: copy.deepcopy(valeur) for cle, valeur in (ligne.get("donnees") or {}).items()
        if cle != "_historique"
    }
    return {
        "version": ligne.get("version"),
        "titre": ligne.get("titre", ""),
        "donnees": donnees,
        "cree_le": ligne.get("cree_le"),
        "observe_le": ligne.get("observe_le"),
        "valide_depuis": ligne.get("valide_depuis"),
        "valide_jusqua": ligne.get("valide_jusqua"),
        "maj_le": ligne.get("maj_le"),
    }


def _liens_inverses(objets: list[Any]) -> dict[str, dict[str, Any]]:
    """Liens que le modèle porte du côté parent : décision → initiative, initiative → outcomes."""
    extras: dict[str, dict[str, Any]] = {}
    for objet in objets:
        type_objet = _type_de(objet)
        identifiant = _id_de(objet)
        if type_objet == "INITIATIVE":
            decision_id = _texte_ou_none(_valeur(objet, "decision_id"))
            if decision_id:
                extras.setdefault(decision_id, {})["initiative_id"] = identifiant
        elif type_objet == "OUTCOME":
            initiative_id = _texte_ou_none(_valeur(objet, "initiative_id"))
            if initiative_id:
                extras.setdefault(initiative_id, {}).setdefault("outcome_ids", []).append(identifiant)
        elif type_objet == "SCENARIO":
            investigation_id = _texte_ou_none(_valeur(objet, "investigation_id"))
            decision_id = _texte_ou_none(_valeur(objet, "decision_id"))
            if investigation_id:
                extras.setdefault(investigation_id, {}).setdefault(
                    "scenario_ids", []).append(identifiant)
            if decision_id:
                extra_decision = extras.setdefault(decision_id, {})
                extra_decision.setdefault("scenario_ids", []).append(identifiant)
                extra_decision.setdefault("scenario_id", identifiant)
    for objet in objets:
        identifiant = _id_de(objet)
        extra = extras.get(identifiant)
        if not extra:
            continue
        initiative_id = extra.get("initiative_id")
        existant = _texte_ou_none(_valeur(objet, "initiative_id"))
        if initiative_id and existant and existant != initiative_id:
            raise BoucleInvalide(
                f"la décision {identifiant} est déjà reliée à l'initiative {existant}"
            )
    return extras


def _est_vide(valeur: Any) -> bool:
    return valeur is None or valeur == "" or valeur == [] or valeur == () or valeur == {}


def _persister(
    conn: Any, tenant: str, objet: Any, *, historique: bool, as_dict: bool,
    extra_donnees: Mapping[str, Any] | None = None, creer: bool = False,
) -> Any:
    payload = _payload_objet(objet)
    identifiant = _texte(payload.get("id"), "id", obligatoire=True)
    if extra_donnees:
        donnees = dict(payload.get("donnees") or {})
        for cle, valeur in extra_donnees.items():
            if cle in {"outcome_ids", "scenario_ids"}:
                actuels = _liste_ids(donnees.get(cle), cle)
                donnees[cle] = actuels + [
                    element for element in valeur if element not in actuels
                ]
            elif cle == "scenario_id" and _texte_ou_none(donnees.get(cle)):
                continue
            else:
                donnees[cle] = valeur
        payload["donnees"] = donnees
    with conn.transaction():
        ancien = None
        if not creer:
            ancien = entreprise_depot.lire_objet(conn, tenant, identifiant, for_update=True)
        if ancien is not None:
            existantes = dict(ancien.get("donnees") or {})
            nouvelles = dict(payload.get("donnees") or {})
            nouvelles.pop("_historique", None)
            donnees = dict(existantes)
            for cle, valeur in nouvelles.items():
                if (cle in _CHAMPS_INVERSES_LIES and _est_vide(valeur)
                        and not _est_vide(existantes.get(cle))):
                    continue
                if cle in {"scenario_ids", "outcome_ids"} and isinstance(valeur, list):
                    actuels = _liste_ids(existantes.get(cle), cle)
                    donnees[cle] = actuels + [
                        element for element in valeur if element not in actuels
                    ]
                    continue
                if cle == "scenario_id" and _texte_ou_none(existantes.get(cle)):
                    continue
                donnees[cle] = valeur
            if historique:
                versions = list(existantes.get("_historique") or [])
                versions.append(_entree_historique(ancien))
                donnees["_historique"] = versions[-_MAX_HISTORIQUE:]
            payload["donnees"] = donnees
        ligne = dict(entreprise_depot.enregistrer_objet(conn, tenant, payload, creer=creer))
    if historique:
        ligne["historique"] = list((ligne.get("donnees") or {}).get("_historique") or [])
    if as_dict:
        return ligne
    retour = _objet_depuis_ligne(ligne)
    if historique:
        retour.historique = ligne["historique"]
    return retour


def enregistrer_boucle(
    conn: Any, tenant_id: Any = None, objets: Any = None, *,
    historique: bool = False, as_dict: bool = True, creer: bool = False,
) -> Any:
    """Persiste une boucle d'objets canoniques et rend le ou les objets stockés.

    `objets` peut être un objet unique, une liste, un ensemble ou un mapping rôle → objet. Les objets sont écrits
    dans l'ordre de la boucle (Situation d'abord, Learning en dernier) après validation des liens, des tenants,
    des mesures et de la décision tranchée. `historique=True` conserve les versions antérieures dans
    `donnees["_historique"]` et les expose dans la clé `historique` du retour. `as_dict=False` rend les objets
    canoniques (instances de ce module) plutôt que les lignes de `objet_entreprise`.

    ``creer=True`` impose une création exclusive : un identifiant déjà présent lève
    :class:`meridian.ports.boucle.ObjetExistant` et n'écrase rien.
    """
    if tenant_id is not None and not isinstance(tenant_id, str):
        if objets is not None:
            raise BoucleInvalide("objets fournis deux fois")
        objets, tenant_id = tenant_id, None
    if objets is None:
        raise BoucleInvalide("objets obligatoires")

    mapping_roles = isinstance(objets, Mapping) and not _ressemble_objet(objets)
    paires: list[tuple[Any, Any]] | None = None
    if mapping_roles:
        paires = sorted(objets.items(), key=lambda paire: _cle_tri(paire[1]))
        liste = [objet for _, objet in paires]
        simple = False
    elif isinstance(objets, (list, tuple, set, frozenset)):
        liste = sorted(list(objets), key=_cle_tri)
        simple = False
    else:
        liste = [objets]
        simple = True
    if not liste:
        raise BoucleInvalide("objets obligatoires")

    tenants = {_tenant_de(objet) for objet in liste}
    if tenant_id is None:
        if len(tenants) != 1:
            raise BoucleInvalide(f"une boucle doit avoir un seul tenant (reçu {sorted(tenants)!r})")
        tenant = tenants.pop()
    else:
        tenant = _texte(tenant_id, "tenant_id", obligatoire=True)
        if tenants - {tenant}:
            raise BoucleInvalide(f"tenants incompatibles avec {tenant!r} : {sorted(tenants)!r}")

    _valider_pour_persistance(conn, tenant, liste)
    extras = _liens_inverses(liste)
    resultats = [
        _persister(
            conn, tenant, objet, historique=historique, as_dict=as_dict,
            extra_donnees=extras.get(_id_de(objet)), creer=creer,
        )
        for objet in liste
    ]
    if simple:
        return resultats[0]
    if mapping_roles and paires is not None:
        return {cle: resultat for (cle, _), resultat in zip(paires, resultats)}
    return resultats


def _objet_depuis_ligne(ligne: Mapping[str, Any]) -> Any:
    type_objet = _type_de(ligne)
    classe = _CLASSES.get(type_objet)
    if classe is None:
        raise BoucleInvalide(f"type hors boucle : {type_objet or 'inconnu'}")
    noms = {champ.name for champ in fields(classe)}
    donnees = {
        cle: copy.deepcopy(valeur) for cle, valeur in (ligne.get("donnees") or {}).items()
        if not str(cle).startswith("_")
    }
    valeurs = {cle: valeur for cle, valeur in donnees.items() if cle in noms}
    valeurs.update({
        "id": ligne.get("id"),
        "tenant_id": ligne.get("tenant_id"),
        "famille": ligne.get("famille"),
        "type": type_objet,
        "mode": ligne.get("mode"),
        "titre": ligne.get("titre", ""),
    })
    for champ in _CHAMPS_DATES:
        if ligne.get(champ) is not None:
            valeurs[champ] = ligne[champ]
    if ligne.get("version") is not None:
        valeurs["version"] = ligne["version"]
    return classe(**valeurs)


def _lien_ou_alias(ligne: Mapping[str, Any], principal: str, alias: str) -> str | None:
    """Lit le lien canonique ou son alias legacy (``*_ref``)."""
    return _texte_ou_none(_valeur(ligne, principal)) or _texte_ou_none(_valeur(ligne, alias))


def _source_principale(ligne: Mapping[str, Any]) -> str | None:
    type_objet = _type_de(ligne)
    if type_objet == "INVESTIGATION":
        return _texte_ou_none(_valeur(ligne, "situation_id"))
    if type_objet == "DECISION":
        return _lien_ou_alias(ligne, "investigation_id", "investigation_ref")
    if type_objet == "SCENARIO":
        return _lien_ou_alias(ligne, "decision_id", "decision_ref") or _texte_ou_none(
            _valeur(ligne, "investigation_id"))
    if type_objet == "INITIATIVE":
        return _lien_ou_alias(ligne, "decision_id", "decision_ref")
    if type_objet == "OUTCOME":
        return _lien_ou_alias(ligne, "initiative_id", "initiative_ref")
    if type_objet == "LEARNING":
        outcomes = _liste_ids(_valeur(ligne, "outcome_ids"), "outcome_ids")
        if outcomes:
            return outcomes[0]
        investigations = _liste_ids(_valeur(ligne, "investigation_ids"), "investigation_ids")
        if investigations:
            return investigations[0]
    return None


def _chaine_lignes(conn: Any, tenant: str, ligne: Mapping[str, Any]) -> list[dict[str, Any]]:
    chaine: list[dict[str, Any]] = []
    vus: set[str] = set()
    courant: Mapping[str, Any] | None = ligne
    while courant is not None:
        identifiant = _id_de(courant)
        if identifiant in vus:
            break
        vus.add(identifiant)
        chaine.append(dict(courant))
        source_id = _source_principale(courant)
        if not source_id:
            break
        courant = entreprise_depot.lire_objet(conn, tenant, source_id)
    return list(reversed(chaine))


def lire_boucle(
    conn: Any, tenant_id: str, objet_id: str, *, historique: bool = False, as_dict: bool = True,
    for_update: bool = False,
) -> Any:
    """Lit un objet de la boucle par `(tenant, id)`.

    Sans `historique`, rend l'objet courant (ligne ou objet canonique). Avec `historique=True`, ajoute au retour
    `chaine` (Situation → … → objet) et `historique` (versions conservées par `enregistrer_boucle`).
    ``for_update=True`` verrouille la ligne principale jusqu'à la fin de la transaction courante ; la chaîne
    n'est pas verrouillée.
    """
    ligne = entreprise_depot.lire_objet(conn, tenant_id, objet_id, for_update=for_update)
    if ligne is None:
        return None
    if not historique:
        return ligne if as_dict else _objet_depuis_ligne(ligne)

    chaine = _chaine_lignes(conn, tenant_id, ligne)
    versions = list((ligne.get("donnees") or {}).get("_historique") or [])
    if as_dict:
        resultat = dict(ligne)
        resultat["chaine"] = chaine
        resultat["historique"] = versions
        return resultat
    objet = _objet_depuis_ligne(ligne)
    objet.chaine = [_objet_depuis_ligne(element) for element in chaine]
    objet.historique = versions
    return objet


lire_par_id = lire_boucle


def transaction(conn: Any) -> Any:
    """Ouvre une transaction sur la connexion ; les appels imbriqués deviennent des savepoints."""
    return conn.transaction()


def nouvelle_situation(**champs: Any) -> Situation:
    """Fabrique la Situation canonique utilisée par l'orchestration applicative."""
    return Situation(**champs)


def nouveau_scenario(**champs: Any) -> Any:
    """Fabrique un Scénario canonique sans faire dépendre l'application du domaine concret."""
    return _nouveau_scenario(**champs)


def enregistrer_objets(
    conn: Any, tenant_id: Any = None, objets: Any = None, *,
    historique: bool = False, as_dict: bool = True,
) -> Any:
    """Persiste des objets d'exploitation, dont les Scénarios, avec leurs liens inverses."""
    return objets_exploitation.enregistrer_objets_exploitation(
        conn, tenant_id, objets, historique=historique, as_dict=as_dict,
    )


def lister_objets_exploitation(
    conn: Any, tenant_id: str, *, type_: str | None = None,
    investigation_id: str | None = None, decision_id: str | None = None,
    limite: int = 100, as_dict: bool = True,
) -> list[Any]:
    """Liste les objets d'exploitation du tenant, filtrés par type et par parent."""
    return objets_exploitation.lister_objets_exploitation(
        conn, tenant_id, type_=type_, investigation_id=investigation_id,
        decision_id=decision_id, limite=limite, as_dict=as_dict,
    )


def donnees_de(objet: Any) -> dict[str, Any]:
    """Rend les champs canoniques d'un objet sous la forme attendue dans ``donnees``."""
    return _payload_objet(objet)["donnees"]


def fusionner_donnees(
    conn: Any, tenant_id: Any, objet_id: Any, patch: Mapping[str, Any], *,
    historique: bool = True, ajouter: Any = (), mode: str | None = None,
    version_attendue: Any = None,
) -> dict[str, Any]:
    """Fusionne un patch dans ``donnees`` sans effacer les clés legacy de l'objet.

    La ligne est verrouillée avant la fusion de l'historique. Les clés de ``ajouter`` sont
    concaténées aux listes existantes (sans doublon) au lieu d'être remplacées. La version de
    ``version_attendue`` rend l'écriture optimiste : une version périmée lève
    :class:`meridian.ports.boucle.VersionRefusee`.
    """
    tenant = _texte(tenant_id, "tenant_id", obligatoire=True)
    identifiant = _texte(objet_id, "id", obligatoire=True)
    entreprise_depot.verifier_donnees(patch)
    with conn.transaction():
        ligne = entreprise_depot.lire_objet(conn, tenant, identifiant, for_update=True)
        if ligne is None:
            raise BoucleInvalide(f"objet introuvable : {identifiant}")
        donnees = dict(ligne.get("donnees") or {})
        if historique:
            versions = list(donnees.get("_historique") or [])
            versions.append(_entree_historique(ligne))
            donnees["_historique"] = versions[-_MAX_HISTORIQUE:]
        listes = frozenset(str(cle) for cle in ajouter)
        for cle, valeur in patch.items():
            if str(cle) == "_historique":
                continue
            if str(cle) in listes:
                actuels = _liste_ids(donnees.get(cle), str(cle))
                nouveaux = _liste_ids(valeur, str(cle))
                donnees[cle] = actuels + [
                    element for element in nouveaux if element not in actuels]
            else:
                donnees[cle] = copy.deepcopy(valeur)
        attendue = version_attendue if version_attendue is not None else ligne.get("version")
        return entreprise_depot.enregistrer_donnees(
            conn, tenant, identifiant, donnees, mode=mode, version_attendue=attendue,
            verifier_secrets=False)
