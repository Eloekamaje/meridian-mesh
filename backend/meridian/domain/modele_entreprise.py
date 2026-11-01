"""Modèle d'entreprise de Méridian : huit familles, types de Twin et objets de la boucle de connaissance.

Ce module est volontairement autonome : ni base de données, ni réseau, ni agent. Il pose les types et les invariants
d'ADR-0005 et de PRD-001, sans réduire le Twin à une application. Les dataclasses sont sérialisables en JSON et
peuvent servir de contrat commun aux projections, APIs et tests d'architecture.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum
import json
from typing import Any
import unicodedata

__all__ = [
    "FAMILLES", "FAMILLES_ENTREPRISE", "TYPES_TWIN", "TYPES_DE_TWIN", "TYPES", "MODES",
    "MODES_CONNAISSANCE", "TYPES_OBJET", "TYPES_PAR_FAMILLE", "FAMILLE_PAR_TYPE",
    "FAMILLE_DE_TYPE", "STATUTS_CLAIM", "ETATS_CONNAISSANCE", "CYCLE_CONNAISSANCE", "CYCLE",
    "TRANSITIONS_CONNAISSANCE", "TRANSITIONS", "TRANSITIONS_AUTORISEES",
    "CHAMPS_TEMPORELS_OBLIGATOIRES", "ModeleInvalide",
    "famille_de", "est_twin_non_applicatif", "transitions_connaissance",
    "transition_autorisee", "verifier_transition",
    "ObjetEntreprise", "Twin", "Claim", "Relation", "Situation", "Opportunity", "Risk",
    "Investigation", "Decision", "Initiative", "Outcome", "Learning", "Source", "Domain",
]


class _Familles(tuple):
    def __contains__(self, valeur: Any) -> bool:
        try:
            return super().__contains__(_normaliser_famille(valeur))
        except Exception:
            return False


FAMILLES = _Familles((
    "identite_structure",
    "sources_preuves",
    "connaissance",
    "emergence",
    "investigation",
    "decision",
    "resultat_apprentissage",
    "interaction_gouvernance",
))
FAMILLES_ENTREPRISE = FAMILLES

TYPES_TWIN = (
    "APPLICATION",
    "PROCESS",
    "CAPABILITY",
    "JOURNEY",
    "ORGANIZATION",
    "PRODUCT",
    "DATA_DOMAIN",
)
TYPES = TYPES_TWIN
TYPES_DE_TWIN = TYPES_TWIN

MODES = (
    "DECLARED",
    "OBSERVED",
    "INFERRED",
    "PROPOSED",
    "CONFIRMED",
)
MODES_CONNAISSANCE = MODES

TYPES_PAR_FAMILLE = {
    "identite_structure": (
        "TWIN", "DOMAIN", "CAPABILITY", "APPLICATION", "PROCESS", "JOURNEY", "TEAM",
        "ORGANIZATION", "PRODUCT", "DATA_DOMAIN",
    ),
    "sources_preuves": ("SOURCE", "ARTIFACT", "OBSERVATION", "EVIDENCE"),
    "connaissance": ("CLAIM", "RELATION", "RELATIONSHIP", "UNKNOWN", "CONTRADICTION"),
    "emergence": ("SIGNAL", "SITUATION", "EXPRESSION", "OPPORTUNITY", "RISK"),
    "investigation": ("INVESTIGATION", "HYPOTHESIS", "EXPERT", "EXPERT_CONTRIBUTION"),
    "decision": ("SCENARIO", "DECISION", "INITIATIVE"),
    "resultat_apprentissage": ("OUTCOME", "LEARNING"),
    "interaction_gouvernance": (
        "USER_CONTEXT", "SCOPE", "PERMISSION", "ANNOTATION", "SUBSCRIPTION",
    ),
}

FAMILLE_PAR_TYPE = {
    type_objet: famille
    for famille, types in TYPES_PAR_FAMILLE.items()
    for type_objet in types
}
TYPES_OBJET = frozenset(FAMILLE_PAR_TYPE)
FAMILLE_DE_TYPE = FAMILLE_PAR_TYPE

STATUTS_CLAIM = frozenset({
    "DECLARED", "OBSERVED", "INFERRED", "PROPOSED", "CONFIRMED", "SUPPORTED",
    "STRENGTHENED", "MATURE", "CONTESTED", "INVALIDATED", "HISTORICAL",
})

ETATS_CONNAISSANCE = (
    "observation",
    "hypothese",
    "claim",
    "claim_renforce",
    "connaissance_mature",
    "decision",
    "apprentissage",
)
CYCLE_CONNAISSANCE = ETATS_CONNAISSANCE
CYCLE = CYCLE_CONNAISSANCE

TRANSITIONS_CONNAISSANCE = {
    "observation": ("hypothese",),
    "hypothese": ("claim",),
    "claim": ("claim_renforce",),
    "claim_renforce": ("connaissance_mature",),
    "connaissance_mature": ("decision",),
    "decision": ("apprentissage",),
    "apprentissage": (),
}
TRANSITIONS = TRANSITIONS_CONNAISSANCE
TRANSITIONS_AUTORISEES = TRANSITIONS_CONNAISSANCE

CHAMPS_TEMPORELS_OBLIGATOIRES = ("cree_le", "observe_le", "valide_depuis")


class ModeleInvalide(ValueError):
    """Un objet du modèle d'entreprise ne respecte pas un invariant."""


def _normaliser_cle(valeur: Any, *, minuscule: bool = False) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = "".join(c if c.isalnum() else "_" for c in texte).strip("_")
    while "__" in texte:
        texte = texte.replace("__", "_")
    return texte.lower() if minuscule else texte.upper()


def _normaliser_famille(valeur: Any) -> str:
    return _normaliser_cle(valeur, minuscule=True)


def _normaliser_type(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def _normaliser_mode(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def _normaliser_statut(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def _normaliser_etat(valeur: Any) -> str:
    return _normaliser_cle(valeur, minuscule=True)


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    if valeur is None:
        raise ModeleInvalide(f"{champ} obligatoire")
    texte = str(valeur).strip()
    if not texte:
        raise ModeleInvalide(f"{champ} obligatoire")
    return texte


def _texte_ou_none(valeur: Any) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


def _identifiant_lien(valeur: Any, champ: str, *, obligatoire: bool = True) -> str | None:
    if isinstance(valeur, ObjetEntreprise):
        valeur = valeur.id
    texte = _texte_ou_none(valeur)
    if obligatoire and not texte:
        raise ModeleInvalide(f"{champ} obligatoire")
    return texte


def _liste(valeur: Any) -> list[Any]:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return list(valeur)
    return [valeur]


def _liste_ids(valeur: Any, champ: str) -> list[str]:
    ids = []
    for element in _liste(valeur):
        if isinstance(element, ObjetEntreprise):
            element = element.id
        texte = _texte_ou_none(element)
        if texte:
            ids.append(texte)
        elif element is not None:
            raise ModeleInvalide(f"{champ} contient un identifiant vide")
    return ids


def _normaliser_instant(valeur: Any, champ: str) -> str | None:
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        return _texte_ou_none(valeur)
    raise ModeleInvalide(f"{champ} doit être une date ISO ou une chaîne")


def _instant_comparable(valeur: str | None) -> datetime | None:
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None


def _verifier_periode(debut: str | None, fin: str | None) -> None:
    d, f = _instant_comparable(debut), _instant_comparable(fin)
    if d is None or f is None:
        return
    try:
        invalide = f < d
    except TypeError:
        return
    if invalide:
        raise ModeleInvalide("valide_jusqua précède valide_depuis")


def _normaliser_modes(valeur: Any) -> list[str]:
    modes = []
    for mode in _liste(valeur):
        normalise = _normaliser_mode(mode)
        if normalise not in MODES:
            raise ModeleInvalide(f"mode inconnu : {mode!r} (attendus : {', '.join(MODES)})")
        if normalise not in modes:
            modes.append(normalise)
    return modes


def _normaliser_preuves(valeur: Any) -> list[Any]:
    preuves = _liste(valeur)
    for preuve in preuves:
        if preuve is None or (isinstance(preuve, str) and not preuve.strip()):
            raise ModeleInvalide("une preuve ne peut pas être vide")
        if isinstance(preuve, (dict, list, tuple, set, frozenset)) and not preuve:
            raise ModeleInvalide("une preuve ne peut pas être vide")
    return [_jsonable(preuve) for preuve in preuves]


def _jsonable(valeur: Any) -> Any:
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        return valeur
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Enum):
        return _jsonable(valeur.value)
    if is_dataclass(valeur) and not isinstance(valeur, type):
        return _jsonable(asdict(valeur))
    if isinstance(valeur, dict):
        return {str(cle): _jsonable(val) for cle, val in valeur.items()}
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_jsonable(element) for element in valeur]
    return str(valeur)


def famille_de(type_objet: Any) -> str:
    """Famille des huit familles à laquelle appartient un type d'objet, une classe ou une instance."""
    if isinstance(type_objet, ObjetEntreprise):
        type_objet = type_objet.type
    elif isinstance(type_objet, type) and issubclass(type_objet, ObjetEntreprise):
        type_objet = type_objet.__name__
    cle = _normaliser_type(type_objet)
    famille = FAMILLE_PAR_TYPE.get(cle)
    if famille is None:
        raise ModeleInvalide(f"type d'objet inconnu : {type_objet!r}")
    return famille


def est_twin_non_applicatif(type_objet: Any) -> bool:
    """Vrai pour un Twin PROCESS, CAPABILITY, JOURNEY, ORGANIZATION, PRODUCT ou DATA_DOMAIN."""
    if isinstance(type_objet, ObjetEntreprise):
        type_objet = type_objet.type
    elif isinstance(type_objet, type) and issubclass(type_objet, ObjetEntreprise):
        type_objet = type_objet.__name__
    cle = _normaliser_type(type_objet)
    return cle in TYPES_TWIN and cle != "APPLICATION"


def transitions_connaissance(
    etat: Any = None, vers: Any = None
) -> frozenset[str] | bool | dict[str, tuple[str, ...]]:
    """Transitions autorisées depuis un état ; avec `vers`, dit si la transition est autorisée."""
    if etat is None:
        return TRANSITIONS_CONNAISSANCE
    depuis = _normaliser_etat(etat)
    if depuis not in TRANSITIONS_CONNAISSANCE:
        raise ModeleInvalide(f"état de connaissance inconnu : {etat!r}")
    autorisees = frozenset(TRANSITIONS_CONNAISSANCE[depuis])
    if vers is None:
        return autorisees
    return _normaliser_etat(vers) in autorisees


def transition_autorisee(depuis: Any, vers: Any) -> bool:
    return bool(transitions_connaissance(depuis, vers))


def verifier_transition(depuis: Any, vers: Any) -> None:
    if not transition_autorisee(depuis, vers):
        raise ModeleInvalide(f"transition de connaissance refusée : {depuis!r} → {vers!r}")


def _appliquer_temporalite(objet: "ObjetEntreprise") -> None:
    temporalite = objet.temporalite
    if not isinstance(temporalite, dict):
        return
    alias = {
        "cree_le": ("cree_le", "created_at", "appris_le"),
        "observe_le": ("observe_le", "observed_at", "observe_at"),
        "valide_depuis": ("valide_depuis", "valid_from", "valide_de"),
        "valide_jusqua": ("valide_jusqua", "valid_to", "valide_a"),
    }
    for cible, noms in alias.items():
        if getattr(objet, cible):
            continue
        for nom in noms:
            if nom in temporalite:
                setattr(objet, cible, temporalite[nom])
                break


@dataclass
class ObjetEntreprise:
    """Base commune : identité stable, famille, mode(s), temporalité, confiance et preuves."""

    id: str
    tenant_id: str
    famille: str = ""
    type: str = ""
    type_: str = ""
    type_objet: str = ""
    mode: str = ""
    cree_le: str | None = None
    observe_le: str | None = None
    valide_depuis: str | None = None
    valide_jusqua: str | None = None
    modes: list[str] = field(default_factory=list)
    confiance: float = 0.5
    preuves: list[Any] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    version: int = 1
    temporalite: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _texte_obligatoire(self.id, "id")
        self.tenant_id = _texte_obligatoire(self.tenant_id, "tenant_id")

        _appliquer_temporalite(self)
        if isinstance(self.temporalite, dict):
            self.temporalite = _jsonable(self.temporalite)
        for champ in CHAMPS_TEMPORELS_OBLIGATOIRES:
            valeur = _normaliser_instant(getattr(self, champ), champ)
            if not valeur:
                raise ModeleInvalide(f"{champ} obligatoire")
            setattr(self, champ, valeur)
        self.valide_jusqua = _normaliser_instant(self.valide_jusqua, "valide_jusqua")
        _verifier_periode(self.valide_depuis, self.valide_jusqua)

        if not self.type:
            self.type = self.type_ or self.type_objet
        self.type = _normaliser_type(self.type)
        if not self.type:
            raise ModeleInvalide("type obligatoire")
        famille_deduite = famille_de(self.type)

        if self.famille:
            famille = _normaliser_famille(self.famille)
            if famille not in FAMILLES:
                raise ModeleInvalide(f"famille inconnue : {self.famille!r} (attendues : {', '.join(FAMILLES)})")
            if famille != famille_deduite:
                raise ModeleInvalide(
                    f"famille incohérente : {self.type} appartient à {famille_deduite}, pas à {famille}"
                )
            self.famille = famille
        else:
            self.famille = famille_deduite

        self.modes = _normaliser_modes(self.modes)
        if self.mode:
            self.mode = _normaliser_mode(self.mode)
            if self.mode not in MODES:
                raise ModeleInvalide(f"mode inconnu : {self.mode!r} (attendus : {', '.join(MODES)})")
            if self.mode not in self.modes:
                self.modes.append(self.mode)
        try:
            self.confiance = float(self.confiance)
        except (TypeError, ValueError) as exc:
            raise ModeleInvalide("confiance doit être un nombre entre 0 et 1") from exc
        if not 0.0 <= self.confiance <= 1.0:
            raise ModeleInvalide("confiance doit être comprise entre 0 et 1")
        self.preuves = _normaliser_preuves(self.preuves)
        self.source_ids = _liste_ids(self.source_ids, "source_ids")
        try:
            self.version = int(self.version)
        except (TypeError, ValueError) as exc:
            raise ModeleInvalide("version doit être un entier positif") from exc
        if self.version < 1:
            raise ModeleInvalide("version doit être un entier positif")

    def est_valide_a(self, date_: Any) -> bool:
        instant = _normaliser_instant(date_, "date")
        if not instant:
            return False
        if _instant_comparable(instant) is None:
            return False
        if self.valide_depuis and instant < self.valide_depuis:
            return False
        if self.valide_jusqua and instant > self.valide_jusqua:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)


@dataclass
class Twin(ObjetEntreprise):
    """Représentation vivante d'une entité de l'entreprise, pas seulement d'une application.

    Le type peut être APPLICATION, PROCESS, CAPABILITY, JOURNEY, ORGANIZATION, PRODUCT ou DATA_DOMAIN.
    """

    famille: str = "identite_structure"
    type: str = ""
    nom: str = ""
    mission: str = ""
    proprietaire: str | None = None
    domaine: str | None = None
    application_id: str | None = None
    alias: list[str] = field(default_factory=list)
    perimetre: str = ""
    statut: str = "PROVISOIRE"
    type_twin: str = ""

    def __post_init__(self) -> None:
        if not self.type:
            self.type = self.type_twin or self.type_ or self.type_objet
        if not self.type:
            raise ModeleInvalide("type de Twin obligatoire")
        super().__post_init__()
        if self.type not in TYPES_TWIN:
            raise ModeleInvalide(
                f"type de Twin inconnu : {self.type!r} (attendus : {', '.join(TYPES_TWIN)})"
            )
        self.nom = str(self.nom or "").strip()
        self.mission = str(self.mission or "").strip()
        self.proprietaire = _texte_ou_none(self.proprietaire)
        self.domaine = _texte_ou_none(self.domaine)
        self.application_id = _texte_ou_none(self.application_id)
        self.alias = _liste_ids(self.alias, "alias")
        self.perimetre = str(self.perimetre or "").strip()
        self.statut = _normaliser_statut(self.statut) or "PROVISOIRE"
        self.type_twin = self.type

    @property
    def est_application(self) -> bool:
        return self.type == "APPLICATION"


@dataclass
class Claim(ObjetEntreprise):
    """Affirmation explicite, vérifiable, temporelle et versionnée : sujet — prédicat — objet."""

    famille: str = "connaissance"
    type: str = "CLAIM"
    sujet: str = ""
    predicat: str = ""
    objet: str = ""
    mode: str = "OBSERVED"
    statut: str = "OBSERVED"
    maturite: str = "observation"
    contradiction_ids: list[str] = field(default_factory=list)
    remplace_id: str | None = None

    def __post_init__(self) -> None:
        self.sujet = _texte_obligatoire(self.sujet, "sujet")
        self.predicat = _texte_obligatoire(self.predicat, "predicat")
        self.objet = _texte_obligatoire(self.objet, "objet")
        self.mode = _normaliser_mode(self.mode)
        if self.mode not in MODES:
            raise ModeleInvalide(f"mode inconnu : {self.mode!r} (attendus : {', '.join(MODES)})")
        self.statut = _normaliser_statut(self.statut) or "OBSERVED"
        if self.maturite is not None and isinstance(self.maturite, str):
            self.maturite = _normaliser_etat(self.maturite) or "observation"
        super().__post_init__()
        if self.mode not in self.modes:
            self.modes.append(self.mode)
        if self.statut == "CONFIRMED" or self.mode == "CONFIRMED":
            if not self.preuves:
                raise ModeleInvalide("un Claim CONFIRMED exige au moins une preuve")
        self.contradiction_ids = _liste_ids(self.contradiction_ids, "contradiction_ids")
        self.remplace_id = _identifiant_lien(self.remplace_id, "remplace_id", obligatoire=False)

    def maturer(self, vers: str) -> "Claim":
        verifier_transition(self.maturite, vers)
        self.maturite = _normaliser_etat(vers)
        return self


@dataclass
class Relation(ObjetEntreprise):
    """Lien typé et prouvable entre deux objets du Mesh."""

    famille: str = "connaissance"
    type: str = "RELATION"
    source_id: str = ""
    cible_id: str = ""
    predicat: str = ""
    mode: str = "INFERRED"
    statut: str = "PROPOSED"
    sujet_id: str = ""
    objet_id: str = ""
    de_id: str = ""
    vers_id: str = ""
    justification: str = ""

    def __post_init__(self) -> None:
        self.source_id = _identifiant_lien(
            self.source_id or self.sujet_id or self.de_id, "source_id"
        ) or ""
        self.cible_id = _identifiant_lien(
            self.cible_id or self.objet_id or self.vers_id, "cible_id"
        ) or ""
        self.sujet_id = self.source_id
        self.objet_id = self.cible_id
        self.de_id = self.source_id
        self.vers_id = self.cible_id
        self.predicat = _texte_obligatoire(self.predicat, "predicat")
        self.mode = _normaliser_mode(self.mode)
        if self.mode not in MODES:
            raise ModeleInvalide(f"mode inconnu : {self.mode!r} (attendus : {', '.join(MODES)})")
        self.statut = _normaliser_statut(self.statut) or "PROPOSED"
        self.justification = str(self.justification or "").strip()
        super().__post_init__()
        if self.mode not in self.modes:
            self.modes.append(self.mode)


@dataclass
class Situation(ObjetEntreprise):
    """Phénomène émergent reliant plusieurs Twins, signaux, Claims ou impacts."""

    famille: str = "emergence"
    type: str = "SITUATION"
    titre: str = ""
    description: str = ""
    statut: str = "CANDIDATE"
    priorite: str = "MOYENNE"
    twin_ids: list[str] = field(default_factory=list)
    signal_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    opportunite_ids: list[str] = field(default_factory=list)
    risk_ids: list[str] = field(default_factory=list)
    expression_id: str | None = None
    inconnues: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.titre = str(self.titre or "").strip()
        self.description = str(self.description or "").strip()
        self.statut = _normaliser_statut(self.statut) or "CANDIDATE"
        self.priorite = _normaliser_statut(self.priorite) or "MOYENNE"
        for champ in ("twin_ids", "signal_ids", "claim_ids", "opportunite_ids", "risk_ids"):
            setattr(self, champ, _liste_ids(getattr(self, champ), champ))
        self.expression_id = _identifiant_lien(self.expression_id, "expression_id", obligatoire=False)
        self.inconnues = [str(i).strip() for i in _liste(self.inconnues) if str(i).strip()]


@dataclass
class Opportunity(ObjetEntreprise):
    """Possibilité d'amélioration, reliée à une situation et éventuellement à une investigation."""

    famille: str = "emergence"
    type: str = "OPPORTUNITY"
    titre: str = ""
    description: str = ""
    statut: str = "DETECTED"
    type_opportunite: str = ""
    valeur_potentielle: Any = None
    situation_id: str | None = None
    investigation_id: str | None = None
    proprietaire: str | None = None
    twin_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.titre = str(self.titre or "").strip()
        self.description = str(self.description or "").strip()
        self.statut = _normaliser_statut(self.statut) or "DETECTED"
        self.type_opportunite = _normaliser_statut(self.type_opportunite)
        self.situation_id = _identifiant_lien(self.situation_id, "situation_id", obligatoire=False)
        self.investigation_id = _identifiant_lien(
            self.investigation_id, "investigation_id", obligatoire=False
        )
        self.proprietaire = _texte_ou_none(self.proprietaire)
        self.twin_ids = _liste_ids(self.twin_ids, "twin_ids")


@dataclass
class Risk(ObjetEntreprise):
    """Risque : structure proche de l'opportunité, avec probabilité, sévérité et exposition."""

    famille: str = "emergence"
    type: str = "RISK"
    titre: str = ""
    description: str = ""
    statut: str = "DETECTED"
    type_risque: str = ""
    probabilite: float | None = None
    severite: str = ""
    exposition: float | None = None
    situation_id: str | None = None
    investigation_id: str | None = None
    proprietaire: str | None = None
    controles: list[str] = field(default_factory=list)
    twin_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.titre = str(self.titre or "").strip()
        self.description = str(self.description or "").strip()
        self.statut = _normaliser_statut(self.statut) or "DETECTED"
        self.type_risque = _normaliser_statut(self.type_risque)
        self.probabilite = _probabilite(self.probabilite, "probabilite")
        self.exposition = _probabilite(self.exposition, "exposition")
        self.severite = _normaliser_statut(self.severite)
        self.situation_id = _identifiant_lien(self.situation_id, "situation_id", obligatoire=False)
        self.investigation_id = _identifiant_lien(
            self.investigation_id, "investigation_id", obligatoire=False
        )
        self.proprietaire = _texte_ou_none(self.proprietaire)
        self.controles = _liste_ids(self.controles, "controles")
        self.twin_ids = _liste_ids(self.twin_ids, "twin_ids")


def _probabilite(valeur: Any, champ: str) -> float | None:
    if valeur is None or valeur == "":
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise ModeleInvalide(f"{champ} doit être un nombre entre 0 et 1") from exc
    if not 0.0 <= nombre <= 1.0:
        raise ModeleInvalide(f"{champ} doit être comprise entre 0 et 1")
    return nombre


@dataclass
class Investigation(ObjetEntreprise):
    """Espace structuré de compréhension : question, périmètre, hypothèses et preuves."""

    famille: str = "investigation"
    type: str = "INVESTIGATION"
    titre: str = ""
    question: str = ""
    statut: str = "OPEN"
    perimetre: str = ""
    proprietaire: str | None = None
    twin_ids: list[str] = field(default_factory=list)
    hypothesis_ids: list[str] = field(default_factory=list)
    expert_ids: list[str] = field(default_factory=list)
    scenario_ids: list[str] = field(default_factory=list)
    ouverte_le: str | None = None
    close_le: str | None = None
    synthese: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.titre = str(self.titre or "").strip()
        self.question = str(self.question or "").strip()
        self.statut = _normaliser_statut(self.statut) or "OPEN"
        self.perimetre = str(self.perimetre or "").strip()
        self.proprietaire = _texte_ou_none(self.proprietaire)
        for champ in ("twin_ids", "hypothesis_ids", "expert_ids", "scenario_ids"):
            setattr(self, champ, _liste_ids(getattr(self, champ), champ))
        self.ouverte_le = _normaliser_instant(self.ouverte_le, "ouverte_le") or self.observe_le
        self.close_le = _normaliser_instant(self.close_le, "close_le")
        self.synthese = str(self.synthese or "").strip()


@dataclass
class Decision(ObjetEntreprise):
    """Décision humaine enregistrée, toujours reliée à une investigation."""

    famille: str = "decision"
    type: str = "DECISION"
    investigation_id: str = ""
    investigation_ref: str = ""
    scenario_id: str | None = None
    scenarios_rejetes: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    criteres: list[str] = field(default_factory=list)
    rationale: str = ""
    approbateur_ids: list[str] = field(default_factory=list)
    decide_le: str | None = None
    statut: str = "PROPOSED"
    initiative_id: str | None = None

    def __post_init__(self) -> None:
        self.investigation_id = _identifiant_lien(
            self.investigation_id or self.investigation_ref, "investigation_id"
        ) or ""
        super().__post_init__()
        self.scenario_id = _identifiant_lien(self.scenario_id, "scenario_id", obligatoire=False)
        self.scenarios_rejetes = _liste_ids(self.scenarios_rejetes, "scenarios_rejetes")
        self.options = [str(o).strip() for o in _liste(self.options) if str(o).strip()]
        self.criteres = [str(c).strip() for c in _liste(self.criteres) if str(c).strip()]
        self.rationale = str(self.rationale or "").strip()
        self.approbateur_ids = _liste_ids(self.approbateur_ids, "approbateur_ids")
        self.decide_le = _normaliser_instant(self.decide_le, "decide_le") or self.observe_le
        self.statut = _normaliser_statut(self.statut) or "PROPOSED"
        self.initiative_id = _identifiant_lien(self.initiative_id, "initiative_id", obligatoire=False)


@dataclass
class Initiative(ObjetEntreprise):
    """Traduction d'une décision en action suivie, avec ses outcomes attendus."""

    famille: str = "decision"
    type: str = "INITIATIVE"
    decision_id: str = ""
    decision_ref: str = ""
    titre: str = ""
    statut: str = "PLANNED"
    proprietaire: str | None = None
    perimetre: str = ""
    outcome_attendu_ids: list[str] = field(default_factory=list)
    outcome_ids: list[str] = field(default_factory=list)
    debut_le: str | None = None
    fin_prevue_le: str | None = None

    def __post_init__(self) -> None:
        self.decision_id = _identifiant_lien(
            self.decision_id or self.decision_ref, "decision_id"
        ) or ""
        super().__post_init__()
        self.titre = str(self.titre or "").strip()
        self.statut = _normaliser_statut(self.statut) or "PLANNED"
        self.proprietaire = _texte_ou_none(self.proprietaire)
        self.perimetre = str(self.perimetre or "").strip()
        self.outcome_attendu_ids = _liste_ids(self.outcome_attendu_ids, "outcome_attendu_ids")
        self.outcome_ids = _liste_ids(self.outcome_ids, "outcome_ids")
        self.debut_le = _normaliser_instant(self.debut_le, "debut_le") or self.valide_depuis
        self.fin_prevue_le = _normaliser_instant(self.fin_prevue_le, "fin_prevue_le")


@dataclass
class Outcome(ObjetEntreprise):
    """Ce qui est observé après une action, toujours relié à une initiative."""

    famille: str = "resultat_apprentissage"
    type: str = "OUTCOME"
    initiative_id: str = ""
    initiative_ref: str = ""
    metrique: str = ""
    valeur_attendue: Any = None
    valeur_observee: Any = None
    delta: Any = None
    interpretation: str = ""
    statut: str = "OBSERVED"

    def __post_init__(self) -> None:
        self.initiative_id = _identifiant_lien(
            self.initiative_id or self.initiative_ref, "initiative_id"
        ) or ""
        super().__post_init__()
        self.metrique = str(self.metrique or "").strip()
        self.interpretation = str(self.interpretation or "").strip()
        self.statut = _normaliser_statut(self.statut) or "OBSERVED"


@dataclass
class Learning(ObjetEntreprise):
    """Connaissance généralisable issue d'un outcome ou d'une investigation historique."""

    famille: str = "resultat_apprentissage"
    type: str = "LEARNING"
    enonce: str = ""
    scope: str = ""
    outcome_ids: list[str] = field(default_factory=list)
    investigation_ids: list[str] = field(default_factory=list)
    source_outcome_refs: list[str] = field(default_factory=list)
    source_investigation_refs: list[str] = field(default_factory=list)
    conditions_applicabilite: list[str] = field(default_factory=list)
    related_claim_ids: list[str] = field(default_factory=list)
    statut: str = "PROPOSED"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.enonce = str(self.enonce or "").strip()
        self.scope = str(self.scope or "").strip()
        self.outcome_ids = _liste_ids(
            self.outcome_ids or self.source_outcome_refs, "outcome_ids"
        )
        self.investigation_ids = _liste_ids(
            self.investigation_ids or self.source_investigation_refs, "investigation_ids"
        )
        self.source_outcome_refs = list(self.outcome_ids)
        self.source_investigation_refs = list(self.investigation_ids)
        self.conditions_applicabilite = [
            str(c).strip() for c in _liste(self.conditions_applicabilite) if str(c).strip()
        ]
        self.related_claim_ids = _liste_ids(self.related_claim_ids, "related_claim_ids")
        self.statut = _normaliser_statut(self.statut) or "PROPOSED"
        if not self.outcome_ids and not self.investigation_ids:
            raise ModeleInvalide(
                "un Learning doit être relié à au moins un Outcome ou une Investigation"
            )


@dataclass
class Source(ObjetEntreprise):
    """Système externe fournissant observations et artefacts ; une Source n'est ni un Twin ni un Claim."""

    famille: str = "sources_preuves"
    type: str = "SOURCE"
    nom: str = ""
    type_source: str = "AUTRE"
    emplacement: str = ""
    proprietaire: str | None = None
    curseur: str = ""
    fraicheur_le: str | None = None

    def __post_init__(self) -> None:
        if self.type and _normaliser_type(self.type) != "SOURCE":
            if not self.type_source or _normaliser_type(self.type_source) == "AUTRE":
                self.type_source = self.type
            self.type = "SOURCE"
        super().__post_init__()
        self.nom = str(self.nom or "").strip()
        self.type_source = _normaliser_statut(self.type_source) or "AUTRE"
        self.emplacement = str(self.emplacement or "").strip()
        self.proprietaire = _texte_ou_none(self.proprietaire)
        self.curseur = str(self.curseur or "").strip()
        self.fraicheur_le = _normaliser_instant(self.fraicheur_le, "fraicheur_le")


@dataclass
class Domain(ObjetEntreprise):
    """Regroupement cohérent d'entités ; le domaine découvert ne remplace jamais le domaine officiel."""

    famille: str = "identite_structure"
    type: str = "DOMAIN"
    nom: str = ""
    description: str = ""
    origine: str = "DECLARED"
    type_domaine: str = ""
    parent_id: str | None = None
    membre_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.type and _normaliser_type(self.type) in {
            "DECLARED", "DISCOVERED", "PROPOSED", "HYBRID"
        }:
            if not self.origine or _normaliser_statut(self.origine) == "DECLARED":
                self.origine = self.type
            self.type = "DOMAIN"
        super().__post_init__()
        self.nom = str(self.nom or "").strip()
        self.description = str(self.description or "").strip()
        self.origine = _normaliser_statut(self.origine) or "DECLARED"
        self.type_domaine = _normaliser_statut(self.type_domaine)
        self.parent_id = _identifiant_lien(self.parent_id, "parent_id", obligatoire=False)
        self.membre_ids = _liste_ids(self.membre_ids, "membre_ids")
