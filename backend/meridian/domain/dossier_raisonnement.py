"""Dossier de raisonnement : le contrat commun à tout traitement cognitif.

Le dossier n'est ni une chaîne de pensée privée, ni un journal de tokens. Il porte les artefacts
vérifiables d'un tour : demande, cadre, plan, constats, options, critique, décision, validation,
gates et réponse. Il est indépendant du modèle et du transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from typing import Iterable, Mapping

from meridian.domain.epistemie import Belief, BeliefRevision, QuestionFrame, SourcePlan

__all__ = [
    "AUTORITES",
    "CRITIQUE_NIVEAUX",
    "ENJEUX",
    "NIVEAUX",
    "REVERSIBILITES",
    "SEVERITES",
    "STATUTS_TOUR",
    "VERDICTS",
    "Cadre",
    "Belief",
    "BeliefRevision",
    "Constat",
    "ContexteRaisonnement",
    "Critique",
    "Demande",
    "Decision",
    "DossierRaisonnement",
    "Finding",
    "Gate",
    "Hypothese",
    "Option",
    "PlanRaisonnement",
    "QuestionFrame",
    "SourcePlan",
    "Validation",
    "maintenant",
]

NIVEAUX = ("N0", "N1", "N2", "N3", "N4")
STATUTS_TOUR = (
    "reponse", "clarification_requise", "proposition", "decision",
    "action_requise", "partiel", "refus", "echec",
)
AUTORITES = ("lecture", "proposition", "approbation", "decision", "action")
ENJEUX = ("faible", "modere", "eleve", "critique")
REVERSIBILITES = ("reversible", "couteuse", "irreversible")
SEVERITES = ("info", "avertissement", "majeure", "critique")
VERDICTS = ("pass", "conditional", "fail")
CRITIQUE_NIVEAUX = ("N3", "N4")

_ORDRES = {
    "N0": 0, "N1": 1, "N2": 2, "N3": 3, "N4": 4,
    "faible": 0, "modere": 1, "eleve": 2, "critique": 3,
    "avertissement": 0, "majeure": 1, "critique": 2,
}


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texte(valeur, maximum=4000) -> str:
    return " ".join(str(valeur or "").split())[:maximum]


def _textes(valeurs, maximum=1000) -> tuple[str, ...]:
    if valeurs is None:
        return ()
    if isinstance(valeurs, str):
        valeurs = [valeurs]
    resultat: list[str] = []
    for valeur in valeurs:
        texte = _texte(valeur, maximum)
        if texte and texte not in resultat:
            resultat.append(texte)
    return tuple(resultat)


def _mapping(valeur) -> dict:
    return dict(valeur) if isinstance(valeur, Mapping) else {}


def _borne(valeur, minimum=0.0, maximum=1.0) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        nombre = minimum
    return max(minimum, min(maximum, nombre))


def _identifiant(valeur, prefixe="") -> str:
    texte = _texte(valeur, 1000)
    if not texte:
        texte = f"{prefixe}:{maintenant()}"
    normalise = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", normalise.lower()).strip("-")[:28]
    digest = hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]
    return f"{prefixe}-{base}-{digest}" if base else f"{prefixe}-{digest}"


@dataclass(frozen=True)
class ContexteRaisonnement:
    """Le contexte borné qui a servi au dossier.

    Il ne recopie pas le prompt : il garde l'empreinte, le périmètre et les identifiants qui rendent
    la réponse rejouable. Les constats, eux, portent le contenu.
    """

    fingerprint: str = ""
    acteur: str = ""
    poste: str = ""
    profil: str = ""
    autorite: str = ""
    espace: str = ""
    entites: tuple[str, ...] = ()
    twin_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    preuve_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    completude: str = "complet"
    fraicheur: str = ""
    limites: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "fingerprint", _texte(self.fingerprint, 128))
        object.__setattr__(self, "acteur", _texte(self.acteur, 128))
        object.__setattr__(self, "poste", _texte(self.poste, 160))
        object.__setattr__(self, "profil", _texte(self.profil, 80))
        object.__setattr__(self, "autorite", _texte(self.autorite, 20))
        object.__setattr__(self, "espace", _texte(self.espace, 160))
        object.__setattr__(self, "entites", _textes(self.entites, 160))
        object.__setattr__(self, "twin_ids", _textes(self.twin_ids, 160))
        object.__setattr__(self, "claim_ids", _textes(self.claim_ids, 160))
        object.__setattr__(self, "preuve_ids", _textes(self.preuve_ids, 200))
        object.__setattr__(self, "source_ids", _textes(self.source_ids, 200))
        object.__setattr__(self, "completude", _texte(self.completude, 40) or "complet")
        object.__setattr__(self, "fraicheur", _texte(self.fraicheur, 80))
        object.__setattr__(self, "limites", _textes(self.limites, 500))

    def as_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "acteur": self.acteur,
            "poste": self.poste,
            "profil": self.profil,
            "autorite": self.autorite,
            "espace": self.espace,
            "entites": list(self.entites),
            "twin_ids": list(self.twin_ids),
            "claim_ids": list(self.claim_ids),
            "preuve_ids": list(self.preuve_ids),
            "source_ids": list(self.source_ids),
            "completude": self.completude,
            "fraicheur": self.fraicheur,
            "limites": list(self.limites),
        }


@dataclass(frozen=True)
class Constat:
    """Un fait ou une proposition contextualisée, relié à sa provenance."""

    texte: str
    type: str = "CONSTAT"
    provenance: str = ""
    twin_id: str = ""
    claim_id: str = ""
    preuve_id: str = ""
    source_id: str = ""
    confiance: float = 0.5
    fraicheur: str = ""
    contradictions: tuple[str, ...] = ()
    limites: tuple[str, ...] = ()
    donnees: dict = field(default_factory=dict)
    id: str = ""

    def __post_init__(self):
        if not _texte(self.texte):
            raise ValueError("constat : texte obligatoire")
        object.__setattr__(self, "texte", _texte(self.texte))
        object.__setattr__(self, "type", _texte(self.type, 40).upper() or "CONSTAT")
        object.__setattr__(self, "provenance", _texte(self.provenance, 240))
        object.__setattr__(self, "twin_id", _texte(self.twin_id, 160))
        object.__setattr__(self, "claim_id", _texte(self.claim_id, 160))
        object.__setattr__(self, "preuve_id", _texte(self.preuve_id, 200))
        object.__setattr__(self, "source_id", _texte(self.source_id, 200))
        object.__setattr__(self, "confiance", _borne(self.confiance))
        object.__setattr__(self, "fraicheur", _texte(self.fraicheur, 80))
        object.__setattr__(self, "contradictions", _textes(self.contradictions, 500))
        object.__setattr__(self, "limites", _textes(self.limites, 500))
        object.__setattr__(self, "donnees", _mapping(self.donnees))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(self.texte, "constat"))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "texte": self.texte,
            "type": self.type,
            "provenance": self.provenance,
            "twin_id": self.twin_id,
            "claim_id": self.claim_id,
            "preuve_id": self.preuve_id,
            "source_id": self.source_id,
            "confiance": round(self.confiance, 3),
            "fraicheur": self.fraicheur,
            "contradictions": list(self.contradictions),
            "limites": list(self.limites),
            "donnees": self.donnees,
        }


@dataclass(frozen=True)
class Hypothese:
    texte: str
    impact: str = ""
    test: str = ""

    def __post_init__(self):
        if not _texte(self.texte):
            raise ValueError("hypothèse : texte obligatoire")
        object.__setattr__(self, "texte", _texte(self.texte))
        object.__setattr__(self, "impact", _texte(self.impact, 500))
        object.__setattr__(self, "test", _texte(self.test, 500))

    def as_dict(self) -> dict:
        return {"texte": self.texte, "impact": self.impact, "test": self.test}


@dataclass(frozen=True)
class Demande:
    question: str
    objet: str = ""
    but: str = "repondre"
    niveau: str = "N0"
    enjeu: str = "faible"
    ambiguite: float = 0.0
    reversibilite: str = "reversible"
    sensibilite: tuple[str, ...] = ()
    autorite: str = "lecture"
    raisons: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()

    def __post_init__(self):
        question = _texte(self.question)
        if not question:
            raise ValueError("demande : question obligatoire")
        niveau = _texte(self.niveau, 4).upper()
        if niveau not in NIVEAUX:
            raise ValueError(f"niveau inconnu : {niveau!r}")
        enjeu = _texte(self.enjeu, 20).lower()
        if enjeu not in ENJEUX:
            raise ValueError(f"enjeu inconnu : {enjeu!r}")
        reversibilite = _texte(self.reversibilite, 20).lower()
        if reversibilite not in REVERSIBILITES:
            raise ValueError(f"réversibilité inconnue : {reversibilite!r}")
        autorite = _texte(self.autorite, 20).lower()
        if autorite not in AUTORITES:
            raise ValueError(f"autorité inconnue : {autorite!r}")
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "objet", _texte(self.objet, 240))
        object.__setattr__(self, "but", _texte(self.but, 40).lower() or "repondre")
        object.__setattr__(self, "niveau", niveau)
        object.__setattr__(self, "enjeu", enjeu)
        object.__setattr__(self, "ambiguite", _borne(self.ambiguite))
        object.__setattr__(self, "reversibilite", reversibilite)
        object.__setattr__(self, "sensibilite", _textes(self.sensibilite, 120))
        object.__setattr__(self, "autorite", autorite)
        object.__setattr__(self, "raisons", _textes(self.raisons, 500))
        object.__setattr__(self, "questions", _textes(self.questions, 500))

    @property
    def critique_requise(self) -> bool:
        return self.niveau in CRITIQUE_NIVEAUX

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "objet": self.objet,
            "but": self.but,
            "niveau": self.niveau,
            "enjeu": self.enjeu,
            "ambiguite": round(self.ambiguite, 3),
            "reversibilite": self.reversibilite,
            "sensibilite": list(self.sensibilite),
            "autorite": self.autorite,
            "raisons": list(self.raisons),
            "questions": list(self.questions),
        }


@dataclass(frozen=True)
class Cadre:
    objectif: str
    perimetre: str = ""
    contraintes: tuple[str, ...] = ()
    criteres_succes: tuple[str, ...] = ()
    parties_prenantes: tuple[str, ...] = ()
    hypotheses: tuple[Hypothese, ...] = ()
    inconnues: tuple[str, ...] = ()
    risques: tuple[str, ...] = ()
    questions_bloquantes: tuple[str, ...] = ()
    questions_non_bloquantes: tuple[str, ...] = ()

    def __post_init__(self):
        if not _texte(self.objectif):
            raise ValueError("cadre : objectif obligatoire")
        object.__setattr__(self, "objectif", _texte(self.objectif))
        object.__setattr__(self, "perimetre", _texte(self.perimetre, 1000))
        object.__setattr__(self, "contraintes", _textes(self.contraintes))
        object.__setattr__(self, "criteres_succes", _textes(self.criteres_succes))
        object.__setattr__(self, "parties_prenantes", _textes(self.parties_prenantes))
        object.__setattr__(self, "inconnues", _textes(self.inconnues))
        object.__setattr__(self, "risques", _textes(self.risques))
        object.__setattr__(self, "questions_bloquantes", _textes(self.questions_bloquantes))
        object.__setattr__(
            self, "questions_non_bloquantes",
            _textes(self.questions_non_bloquantes))
        hypotheses = tuple(
            h if isinstance(h, Hypothese) else Hypothese(**_mapping(h))
            for h in self.hypotheses or ()
        )
        object.__setattr__(self, "hypotheses", hypotheses)

    @property
    def complet(self) -> bool:
        return not self.questions_bloquantes

    def as_dict(self) -> dict:
        return {
            "objectif": self.objectif,
            "perimetre": self.perimetre,
            "contraintes": list(self.contraintes),
            "criteres_succes": list(self.criteres_succes),
            "parties_prenantes": list(self.parties_prenantes),
            "hypotheses": [h.as_dict() for h in self.hypotheses],
            "inconnues": list(self.inconnues),
            "risques": list(self.risques),
            "questions_bloquantes": list(self.questions_bloquantes),
            "questions_non_bloquantes": list(self.questions_non_bloquantes),
        }


@dataclass(frozen=True)
class PlanRaisonnement:
    niveau: str
    operations: tuple[str, ...]
    methodes: tuple[str, ...] = ()
    competences: tuple[str, ...] = ()
    specialistes: tuple[str, ...] = ()
    outils_prevus: tuple[str, ...] = ()
    seuil_preuve: str = "declared"
    niveau_critique: str = "aucune"
    budget: dict = field(default_factory=dict)
    conditions_arret: tuple[str, ...] = ()
    justification: tuple[str, ...] = ()

    def __post_init__(self):
        niveau = _texte(self.niveau, 4).upper()
        if niveau not in NIVEAUX:
            raise ValueError(f"niveau inconnu : {niveau!r}")
        object.__setattr__(self, "niveau", niveau)
        object.__setattr__(self, "operations", _textes(self.operations, 80))
        object.__setattr__(self, "methodes", _textes(self.methodes, 80))
        object.__setattr__(self, "competences", _textes(self.competences, 80))
        object.__setattr__(self, "specialistes", _textes(self.specialistes, 80))
        object.__setattr__(self, "outils_prevus", _textes(self.outils_prevus, 80))
        object.__setattr__(self, "seuil_preuve", _texte(self.seuil_preuve, 20).lower())
        object.__setattr__(self, "niveau_critique", _texte(self.niveau_critique, 20).lower())
        object.__setattr__(self, "budget", _mapping(self.budget))
        object.__setattr__(self, "conditions_arret", _textes(self.conditions_arret))
        object.__setattr__(self, "justification", _textes(self.justification))

    def as_dict(self) -> dict:
        return {
            "niveau": self.niveau,
            "operations": list(self.operations),
            "methodes": list(self.methodes),
            "competences": list(self.competences),
            "specialistes": list(self.specialistes),
            "outils_prevus": list(self.outils_prevus),
            "seuil_preuve": self.seuil_preuve,
            "niveau_critique": self.niveau_critique,
            "budget": dict(self.budget),
            "conditions_arret": list(self.conditions_arret),
            "justification": list(self.justification),
        }


@dataclass(frozen=True)
class Option:
    titre: str
    description: str = ""
    avantages: tuple[str, ...] = ()
    inconvenients: tuple[str, ...] = ()
    risques: tuple[str, ...] = ()
    cout: str = ""
    reversible: bool | None = None
    conditions_validite: tuple[str, ...] = ()
    source: str = "proposee"
    id: str = ""

    def __post_init__(self):
        if not _texte(self.titre):
            raise ValueError("option : titre obligatoire")
        object.__setattr__(self, "titre", _texte(self.titre, 240))
        object.__setattr__(self, "description", _texte(self.description))
        object.__setattr__(self, "avantages", _textes(self.avantages))
        object.__setattr__(self, "inconvenients", _textes(self.inconvenients))
        object.__setattr__(self, "risques", _textes(self.risques))
        object.__setattr__(self, "cout", _texte(self.cout, 240))
        object.__setattr__(self, "reversible", self.reversible)
        object.__setattr__(
            self, "conditions_validite", _textes(self.conditions_validite))
        object.__setattr__(self, "source", _texte(self.source, 40) or "proposee")
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(self.titre, "opt"))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "titre": self.titre,
            "description": self.description,
            "avantages": list(self.avantages),
            "inconvenients": list(self.inconvenients),
            "risques": list(self.risques),
            "cout": self.cout,
            "reversible": self.reversible,
            "conditions_validite": list(self.conditions_validite),
            "source": self.source,
        }


@dataclass(frozen=True)
class Finding:
    constat: str
    severite: str = "avertissement"
    rubrique: str = "general"
    preuve: str = ""
    remediation: str = ""
    id: str = ""

    def __post_init__(self):
        if not _texte(self.constat):
            raise ValueError("finding : constat obligatoire")
        severite = _texte(self.severite, 20).lower()
        if severite not in SEVERITES:
            raise ValueError(f"sévérité inconnue : {severite!r}")
        object.__setattr__(self, "constat", _texte(self.constat))
        object.__setattr__(self, "severite", severite)
        object.__setattr__(self, "rubrique", _texte(self.rubrique, 80) or "general")
        object.__setattr__(self, "preuve", _texte(self.preuve, 1000))
        object.__setattr__(self, "remediation", _texte(self.remediation, 1000))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(self.constat, "find"))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "constat": self.constat,
            "severite": self.severite,
            "rubrique": self.rubrique,
            "preuve": self.preuve,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class Critique:
    cible: str = "livrable"
    findings: tuple[Finding, ...] = ()
    dissensus: tuple[str, ...] = ()
    verdict: str = "pass"
    reviewer: str = "noyau"
    independance: str = "separee"

    def __post_init__(self):
        verdict = _texte(self.verdict, 20).lower()
        if verdict not in VERDICTS:
            raise ValueError(f"verdict inconnu : {verdict!r}")
        findings = tuple(
            f if isinstance(f, Finding) else Finding(**_mapping(f))
            for f in self.findings or ()
        )
        object.__setattr__(self, "cible", _texte(self.cible, 80) or "livrable")
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "dissensus", _textes(self.dissensus))
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "reviewer", _texte(self.reviewer, 80) or "noyau")
        object.__setattr__(self, "independance", _texte(self.independance, 40) or "separee")

    @property
    def bloquante(self) -> bool:
        return any(f.severite in ("majeure", "critique") for f in self.findings)

    def as_dict(self) -> dict:
        return {
            "cible": self.cible,
            "findings": [f.as_dict() for f in self.findings],
            "dissensus": list(self.dissensus),
            "verdict": self.verdict,
            "reviewer": self.reviewer,
            "independance": self.independance,
        }


@dataclass(frozen=True)
class Decision:
    choix: str = ""
    justification: str = ""
    options_ecartees: tuple[str, ...] = ()
    consequences: tuple[str, ...] = ()
    proprietaire: str = ""
    autorite: str = "proposition"
    conditions_retournement: tuple[str, ...] = ()
    plan_validation: tuple[str, ...] = ()

    def __post_init__(self):
        autorite = _texte(self.autorite, 20).lower()
        if autorite not in AUTORITES:
            raise ValueError(f"autorité inconnue : {autorite!r}")
        object.__setattr__(self, "choix", _texte(self.choix))
        object.__setattr__(self, "justification", _texte(self.justification))
        object.__setattr__(self, "options_ecartees", _textes(self.options_ecartees))
        object.__setattr__(self, "consequences", _textes(self.consequences))
        object.__setattr__(self, "proprietaire", _texte(self.proprietaire, 120))
        object.__setattr__(self, "autorite", autorite)
        object.__setattr__(
            self, "conditions_retournement", _textes(self.conditions_retournement))
        object.__setattr__(self, "plan_validation", _textes(self.plan_validation))

    def as_dict(self) -> dict:
        return {
            "choix": self.choix,
            "justification": self.justification,
            "options_ecartees": list(self.options_ecartees),
            "consequences": list(self.consequences),
            "proprietaire": self.proprietaire,
            "autorite": self.autorite,
            "conditions_retournement": list(self.conditions_retournement),
            "plan_validation": list(self.plan_validation),
        }


@dataclass(frozen=True)
class Validation:
    hypothese: str
    methode: str = "test"
    critere: str = ""
    echeance: str = ""
    proprietaire: str = ""
    resultat: str = ""

    def __post_init__(self):
        if not _texte(self.hypothese):
            raise ValueError("validation : hypothèse obligatoire")
        object.__setattr__(self, "hypothese", _texte(self.hypothese))
        object.__setattr__(self, "methode", _texte(self.methode, 80) or "test")
        object.__setattr__(self, "critere", _texte(self.critere, 500))
        object.__setattr__(self, "echeance", _texte(self.echeance, 80))
        object.__setattr__(self, "proprietaire", _texte(self.proprietaire, 120))
        object.__setattr__(self, "resultat", _texte(self.resultat, 500))

    def as_dict(self) -> dict:
        return {
            "hypothese": self.hypothese,
            "methode": self.methode,
            "critere": self.critere,
            "echeance": self.echeance,
            "proprietaire": self.proprietaire,
            "resultat": self.resultat,
        }


@dataclass(frozen=True)
class Gate:
    id: str
    condition: str
    statut: str = "ok"
    message: str = ""

    def __post_init__(self):
        statut = _texte(self.statut, 20).lower()
        if statut not in ("ok", "avertissement", "echec"):
            raise ValueError(f"statut de gate inconnu : {statut!r}")
        object.__setattr__(self, "id", _texte(self.id, 40))
        object.__setattr__(self, "condition", _texte(self.condition, 500))
        object.__setattr__(self, "statut", statut)
        object.__setattr__(self, "message", _texte(self.message, 1000))

    @property
    def bloquante(self) -> bool:
        return self.statut == "echec"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "condition": self.condition,
            "statut": self.statut,
            "message": self.message,
        }


@dataclass
class DossierRaisonnement:
    question: str
    tenant: str = ""
    travail_id: str = ""
    demande: Demande | None = None
    cadre: Cadre | None = None
    plan: PlanRaisonnement | None = None
    question_frame: QuestionFrame | None = None
    beliefs: tuple[Belief, ...] = ()
    source_plan: SourcePlan | None = None
    revisions: tuple[BeliefRevision, ...] = ()
    contexte: ContexteRaisonnement | None = None
    constats: tuple[Constat, ...] = ()
    options: tuple[Option, ...] = ()
    critiques: tuple[Critique, ...] = ()
    decision: Decision | None = None
    validation: tuple[Validation, ...] = ()
    reponse: dict = field(default_factory=dict)
    statut: str = "reponse"
    trace_id: str = ""
    gates: tuple[Gate, ...] = ()
    id: str = ""
    cree_le: str = field(default_factory=maintenant)
    maj_le: str = field(default_factory=maintenant)

    def __post_init__(self):
        question = _texte(self.question)
        if not question:
            raise ValueError("dossier : question obligatoire")
        statut = _texte(self.statut, 30).lower()
        if statut not in STATUTS_TOUR:
            raise ValueError(f"statut de tour inconnu : {statut!r}")
        options = tuple(
            o if isinstance(o, Option) else Option(**_mapping(o))
            for o in self.options or ()
        )
        critiques = tuple(
            c if isinstance(c, Critique) else Critique(**_mapping(c))
            for c in self.critiques or ()
        )
        validation = tuple(
            v if isinstance(v, Validation) else Validation(**_mapping(v))
            for v in self.validation or ()
        )
        beliefs = tuple(
            b if isinstance(b, Belief) else Belief(**_mapping(b))
            for b in self.beliefs or ()
        )
        revisions = tuple(
            r if isinstance(r, BeliefRevision) else BeliefRevision(**_mapping(r))
            for r in self.revisions or ()
        )
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "tenant", _texte(self.tenant, 128))
        object.__setattr__(self, "travail_id", _texte(self.travail_id, 128))
        constats = tuple(
            c if isinstance(c, Constat) else Constat(**_mapping(c))
            for c in self.constats or ()
        )
        object.__setattr__(self, "constats", constats)
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "critiques", critiques)
        object.__setattr__(self, "validation", validation)
        object.__setattr__(self, "beliefs", beliefs)
        object.__setattr__(self, "revisions", revisions)
        object.__setattr__(self, "reponse", _mapping(self.reponse))
        object.__setattr__(self, "statut", statut)
        object.__setattr__(self, "gates", tuple(
            g if isinstance(g, Gate) else Gate(**_mapping(g)) for g in self.gates or ()))
        object.__setattr__(self, "id", _texte(self.id, 80) or _identifiant(
            f"{self.tenant}:{self.question}:{self.cree_le}", "dossier"))
        object.__setattr__(self, "maj_le", self.maj_le or maintenant())

    @property
    def bloquee(self) -> bool:
        return any(g.bloquante for g in self.gates) or any(c.bloquante for c in self.critiques)

    @property
    def niveau(self) -> str:
        return self.demande.niveau if self.demande else "N0"

    def question_libre(self) -> bool:
        return not (self.cadre and self.cadre.questions_bloquantes)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant": self.tenant,
            "travail_id": self.travail_id,
            "question": self.question,
            "demande": self.demande.as_dict() if self.demande else None,
            "cadre": self.cadre.as_dict() if self.cadre else None,
            "plan": self.plan.as_dict() if self.plan else None,
            "question_frame": self.question_frame.as_dict() if self.question_frame else None,
            "beliefs": [b.as_dict() for b in self.beliefs],
            "source_plan": self.source_plan.as_dict() if self.source_plan else None,
            "revisions": [r.as_dict() for r in self.revisions],
            "contexte": self.contexte.as_dict() if self.contexte else None,
            "constats": [c.as_dict() for c in self.constats],
            "options": [o.as_dict() for o in self.options],
            "critiques": [c.as_dict() for c in self.critiques],
            "decision": self.decision.as_dict() if self.decision else None,
            "validation": [v.as_dict() for v in self.validation],
            "reponse": dict(self.reponse),
            "statut": self.statut,
            "trace_id": self.trace_id,
            "gates": [g.as_dict() for g in self.gates],
            "niveau": self.niveau,
            "bloquee": self.bloquee,
            "cree_le": self.cree_le,
            "maj_le": self.maj_le,
        }
