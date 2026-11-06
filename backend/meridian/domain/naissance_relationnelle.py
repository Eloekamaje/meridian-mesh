"""Manifeste de naissance et propositions de relation.

Le manifeste est la déclaration structurée produite par la commande de naissance : ce que le
Twin expose, ce qu'il consomme, ce qu'il ignore. Une proposition de relation est un candidat
dérivé de ce manifeste et des autres Twins ; elle n'est jamais une confirmation.

Le Twin propose et atteste son côté. Le propriétaire confirme. L'observation renforce.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re

from meridian.domain.graphe import ETATS_RELATION
from meridian.domain.modele_entreprise import MODES
from meridian.domain.secrets import sans_secret as _sans_secret

__all__ = [
    "ENVIRONNEMENTS",
    "MODES_RELATION",
    "PORTEES_CONSOMMATION",
    "PORTEES_ELIGIBLES",
    "PORTEES_EXPOSITION",
    "VISIBILITES",
    "AutoriteInsuffisante",
    "Consommation",
    "Exposition",
    "ManifesteNaissance",
    "ManifesteInvalide",
    "PropositionRelation",
    "RelationInvalide",
    "Ressource",
    "decider",
    "marquer_observee",
    "marquer_obsolete",
]

VISIBILITES = ("TEAM", "TWIN", "PORTFOLIO", "TENANT")
ENVIRONNEMENTS = ("prod", "preprod", "recette", "dev", "inconnu")
MODES_RELATION = tuple(MODES)
PORTEES_EXPOSITION = ("INTERNAL", "ADMIN", "HEALTH", "DEMO", "DEBUG",
                      "SERVICE", "PARTNER", "PUBLIC", "UNKNOWN")
PORTEES_CONSOMMATION = ("INTERNAL", "EXTERNAL", "UNKNOWN")
PORTEES_ELIGIBLES = frozenset({"SERVICE", "PARTNER", "PUBLIC"})
KINDS = ("HTTP", "SOAP", "JMS", "KAFKA", "JNDI", "DB", "GRPC", "BATCH", "FILE", "AUTRE")
KINDS_RESSOURCE = ("QUEUE", "TOPIC", "TABLE", "FILE", "ENDPOINT", "AUTRE")

_RE_METHODE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", re.IGNORECASE)


class ManifesteInvalide(ValueError):
    """Le manifeste de naissance ne respecte pas son contrat."""


class RelationInvalide(ValueError):
    """La proposition de relation ne respecte pas son contrat."""


class AutoriteInsuffisante(PermissionError):
    """L'acteur ne peut pas trancher cette relation."""


def _texte(valeur, champ, maximum=500, obligatoire=True) -> str:
    texte = " ".join(str(valeur or "").split())
    if not texte:
        if obligatoire:
            raise ValueError(f"{champ} obligatoire")
        return ""
    if len(texte) > maximum:
        raise ValueError(f"{champ} trop long (maximum {maximum})")
    return texte


def _visible(valeur) -> str:
    texte = str(valeur or "TEAM").strip().upper()
    if texte not in VISIBILITES:
        raise ValueError(f"visibilité inconnue : {valeur!r}")
    return texte


def _environnement(valeur) -> str:
    texte = str(valeur or "inconnu").strip().lower()
    if texte not in ENVIRONNEMENTS:
        raise ValueError(f"environnement inconnu : {valeur!r}")
    return texte


def _kind(valeur) -> str:
    texte = str(valeur or "AUTRE").strip().upper()
    if texte == "REST":
        texte = "HTTP"
    if texte == "MQ":
        texte = "JMS"
    if texte not in KINDS:
        raise ValueError(f"type de lien inconnu : {valeur!r}")
    return texte


def _portee_exposition(valeur) -> str:
    texte = str(valeur or "UNKNOWN").strip().upper()
    if texte not in PORTEES_EXPOSITION:
        raise ValueError(f"portée d'exposition inconnue : {valeur!r}")
    return texte


def _portee_consommation(valeur) -> str:
    texte = str(valeur or "UNKNOWN").strip().upper()
    if texte not in PORTEES_CONSOMMATION:
        raise ValueError(f"portée de consommation inconnue : {valeur!r}")
    return texte


def _kind_ressource(valeur) -> str:
    texte = str(valeur or "AUTRE").strip().upper()
    if texte not in KINDS_RESSOURCE:
        raise ValueError(f"type de ressource inconnu : {valeur!r}")
    return texte


def _confiance(valeur) -> float:
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise ValueError("confiance attendue entre 0 et 1") from exc
    if not 0 <= nombre <= 1:
        raise ValueError("confiance attendue entre 0 et 1")
    return nombre


def _instant(valeur) -> str:
    if valeur is None or str(valeur).strip() == "":
        return datetime.now(timezone.utc).isoformat()
    if isinstance(valeur, datetime):
        return valeur.astimezone(timezone.utc).isoformat()
    texte = str(valeur).strip()
    try:
        datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("date ISO attendue") from exc
    return texte


def _cle_operation(valeur: str) -> str:
    texte = " ".join(str(valeur or "").split())
    return texte.casefold().rstrip("/")


@dataclass(frozen=True)
class Exposition:
    kind: str = "HTTP"
    operation: str = ""
    environment: str = "inconnu"
    contract_version: str = ""
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.5
    portee: str = "UNKNOWN"
    boundary_evidence: tuple[str, ...] = ()
    ressource_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "kind", _kind(self.kind))
        object.__setattr__(self, "operation", _sans_secret(
            _texte(self.operation, "operation", 500), "operation"))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "contract_version", _texte(
            self.contract_version, "contract_version", 80, obligatoire=False))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "confidence", _confiance(self.confidence))
        object.__setattr__(self, "portee", _portee_exposition(self.portee))
        object.__setattr__(self, "boundary_evidence", tuple(
            dict.fromkeys(str(x) for x in (self.boundary_evidence or ()) if str(x).strip())))
        object.__setattr__(self, "ressource_id", _texte(
            self.ressource_id, "ressource_id", 200, obligatoire=False))

    @property
    def cle(self) -> tuple[str, str, str]:
        return self.kind, _cle_operation(self.operation), self.environment

    @property
    def eligible(self) -> bool:
        return self.portee in PORTEES_ELIGIBLES

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "operation": self.operation, "environment": self.environment,
            "contract_version": self.contract_version, "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence, "portee": self.portee,
            "boundary_evidence": list(self.boundary_evidence), "ressource_id": self.ressource_id,
        }


@dataclass(frozen=True)
class Consommation:
    kind: str = "HTTP"
    logical_ref: str = ""
    target_hint: str = ""
    environment: str = "inconnu"
    evidence_ids: tuple[str, ...] = ()
    confidence: float = 0.5
    portee: str = "UNKNOWN"
    boundary_evidence: tuple[str, ...] = ()
    ressource_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "kind", _kind(self.kind))
        object.__setattr__(self, "logical_ref", _sans_secret(
            _texte(self.logical_ref, "logical_ref", 500), "logical_ref"))
        object.__setattr__(self, "target_hint", _texte(
            self.target_hint, "target_hint", 200, obligatoire=False))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "confidence", _confiance(self.confidence))
        object.__setattr__(self, "portee", _portee_consommation(self.portee))
        object.__setattr__(self, "boundary_evidence", tuple(
            dict.fromkeys(str(x) for x in (self.boundary_evidence or ()) if str(x).strip())))
        object.__setattr__(self, "ressource_id", _texte(
            self.ressource_id, "ressource_id", 200, obligatoire=False))

    @property
    def cle(self) -> tuple[str, str, str]:
        return self.kind, _cle_operation(self.logical_ref), self.environment

    @property
    def eligible(self) -> bool:
        return self.portee == "EXTERNAL"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "logical_ref": self.logical_ref, "target_hint": self.target_hint,
            "environment": self.environment, "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence, "portee": self.portee,
            "boundary_evidence": list(self.boundary_evidence), "ressource_id": self.ressource_id,
        }


@dataclass(frozen=True)
class Ressource:
    id: str
    kind: str = "AUTRE"
    nom: str = ""
    owner_twin_id: str = ""
    portee: str = "UNKNOWN"
    boundary_evidence: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    environment: str = "inconnu"

    def __post_init__(self):
        object.__setattr__(self, "id", _texte(self.id, "id", 200))
        object.__setattr__(self, "kind", _kind_ressource(self.kind))
        object.__setattr__(self, "nom", _texte(self.nom or self.id, "nom", 500))
        object.__setattr__(self, "owner_twin_id", _texte(
            self.owner_twin_id, "owner_twin_id", 128, obligatoire=False))
        object.__setattr__(self, "portee", _portee_exposition(self.portee))
        object.__setattr__(self, "boundary_evidence", tuple(
            dict.fromkeys(str(x) for x in (self.boundary_evidence or ()) if str(x).strip())))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "environment", _environnement(self.environment))

    @property
    def eligible(self) -> bool:
        return self.portee in PORTEES_ELIGIBLES

    def as_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "nom": self.nom,
            "owner_twin_id": self.owner_twin_id, "portee": self.portee,
            "boundary_evidence": list(self.boundary_evidence),
            "evidence_ids": list(self.evidence_ids), "environment": self.environment,
        }


@dataclass(frozen=True)
class ManifesteNaissance:
    tenant_id: str
    twin_id: str
    birth_run_id: str
    type: str = "APPLICATION"
    application_id: str = ""
    status: str = "PROVISIONAL"
    owner: str = ""
    perimetre_id: str = ""
    partial: bool = False
    declared_by: str = "naissance"
    declared_at: str = ""
    visibility: str = "TEAM"
    exposures: tuple[Exposition, ...] = ()
    consumptions: tuple[Consommation, ...] = ()
    unknowns: tuple[str, ...] = ()
    ressources: tuple[Ressource, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, "tenant_id", 128))
        object.__setattr__(self, "twin_id", _texte(self.twin_id, "twin_id", 128))
        object.__setattr__(self, "birth_run_id", _texte(self.birth_run_id, "birth_run_id", 128))
        object.__setattr__(self, "type", _texte(self.type, "type", 32).upper())
        object.__setattr__(self, "application_id", _texte(
            self.application_id, "application_id", 128, obligatoire=False))
        statut = str(self.status or "PROVISIONAL").strip().upper()
        if statut not in ("PROVISIONAL", "CONFIRMED"):
            raise ValueError(f"statut de Twin inconnu : {self.status!r}")
        object.__setattr__(self, "status", statut)
        object.__setattr__(self, "owner", _texte(self.owner, "owner", 200, obligatoire=False))
        object.__setattr__(self, "perimetre_id", _texte(
            self.perimetre_id, "perimetre_id", 128, obligatoire=False))
        object.__setattr__(self, "partial", bool(self.partial))
        object.__setattr__(self, "declared_by", _texte(
            self.declared_by, "declared_by", 200, obligatoire=False))
        object.__setattr__(self, "declared_at", _instant(self.declared_at))
        object.__setattr__(self, "visibility", _visible(self.visibility))
        expositions = {}
        for exposition in self.exposures or ():
            if not isinstance(exposition, Exposition):
                raise ValueError("expositions : Exposition attendue")
            expositions.setdefault(exposition.cle, exposition)
        consommations = {}
        for consommation in self.consumptions or ():
            if not isinstance(consommation, Consommation):
                raise ValueError("consommations : Consommation attendue")
            consommations.setdefault(consommation.cle, consommation)
        object.__setattr__(self, "exposures", tuple(expositions.values()))
        object.__setattr__(self, "consumptions", tuple(consommations.values()))
        object.__setattr__(self, "unknowns", tuple(
            dict.fromkeys(_texte(x, "unknown", 500, obligatoire=False)
                          for x in (self.unknowns or ()) if _texte(x, "unknown", 500, obligatoire=False))))
        ressources = {}
        for ressource in self.ressources or ():
            if not isinstance(ressource, Ressource):
                raise ValueError("ressources : Ressource attendue")
            ressources.setdefault(ressource.id, ressource)
        object.__setattr__(self, "ressources", tuple(ressources.values()))

    @property
    def id(self) -> str:
        return f"manifeste-{self.tenant_id}-{self.twin_id}-{self.birth_run_id}"

    def as_dict(self) -> dict:
        return {
            "kind": "manifeste_naissance",
            "tenant_id": self.tenant_id, "twin_id": self.twin_id,
            "birth_run_id": self.birth_run_id, "type": self.type,
            "application_id": self.application_id, "status": self.status,
            "owner": self.owner, "perimetre_id": self.perimetre_id,
            "partial": self.partial, "declared_by": self.declared_by,
            "declared_at": self.declared_at, "visibility": self.visibility,
            "exposures": [x.as_dict() for x in self.exposures],
            "consumptions": [x.as_dict() for x in self.consumptions],
            "unknowns": list(self.unknowns),
            "ressources": [x.as_dict() for x in self.ressources],
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "ManifesteNaissance":
        if not isinstance(valeur, dict):
            raise ManifesteInvalide("manifeste : objet attendu")
        try:
            return cls(
                tenant_id=valeur.get("tenant_id"), twin_id=valeur.get("twin_id"),
                birth_run_id=valeur.get("birth_run_id") or valeur.get("id"),
                type=valeur.get("type") or "APPLICATION",
                application_id=valeur.get("application_id") or "",
                status=valeur.get("status") or "PROVISIONAL",
                owner=valeur.get("owner") or "",
                perimetre_id=valeur.get("perimetre_id") or "",
                partial=bool(valeur.get("partial")),
                declared_by=valeur.get("declared_by") or "naissance",
                declared_at=valeur.get("declared_at") or "",
                visibility=valeur.get("visibility") or "TEAM",
                exposures=tuple(Exposition(
                    kind=x.get("kind"), operation=x.get("operation"),
                    environment=x.get("environment"), contract_version=x.get("contract_version") or "",
                    evidence_ids=tuple(x.get("evidence_ids") or ()),
                    confidence=x.get("confidence", 0.5), portee=x.get("portee") or "UNKNOWN",
                    boundary_evidence=tuple(x.get("boundary_evidence") or ()),
                    ressource_id=x.get("ressource_id") or "") for x in valeur.get("exposures") or ()),
                consumptions=tuple(Consommation(
                    kind=x.get("kind"), logical_ref=x.get("logical_ref"),
                    target_hint=x.get("target_hint") or "", environment=x.get("environment"),
                    evidence_ids=tuple(x.get("evidence_ids") or ()),
                    confidence=x.get("confidence", 0.5), portee=x.get("portee") or "UNKNOWN",
                    boundary_evidence=tuple(x.get("boundary_evidence") or ()),
                    ressource_id=x.get("ressource_id") or "") for x in valeur.get("consumptions") or ()),
                unknowns=tuple(valeur.get("unknowns") or ()),
                ressources=tuple(Ressource(
                    id=x.get("id"), kind=x.get("kind") or "AUTRE", nom=x.get("nom") or "",
                    owner_twin_id=x.get("owner_twin_id") or "",
                    portee=x.get("portee") or "UNKNOWN",
                    boundary_evidence=tuple(x.get("boundary_evidence") or ()),
                    evidence_ids=tuple(x.get("evidence_ids") or ()),
                    environment=x.get("environment") or "inconnu")
                    for x in valeur.get("ressources") or ()),
            )
        except (TypeError, ValueError) as exc:
            raise ManifesteInvalide(str(exc)) from exc


@dataclass(frozen=True)
class PropositionRelation:
    tenant_id: str
    consumer_id: str
    provider_id: str
    object: str
    environment: str = "inconnu"
    predicate: str = "CONSOMME"
    mode: str = "DECLARED"
    state: str = "supposee"
    confidence: float = 0.5
    evidence_ids: tuple[str, ...] = ()
    consumer_owner: str = ""
    provider_owner: str = ""
    justification: str = ""
    unknowns: tuple[str, ...] = ()
    created_at: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_note: str = ""
    confirmations: tuple[str, ...] = ()
    critique: bool = False
    last_observed_at: str = ""
    transport: str = "HTTP"
    portee: str = "UNKNOWN"
    boundary_evidence: tuple[str, ...] = ()
    via: str = ""
    consumer_application_id: str = ""
    provider_application_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, "tenant_id", 128))
        object.__setattr__(self, "consumer_id", _texte(self.consumer_id, "consumer_id", 128))
        object.__setattr__(self, "provider_id", _texte(self.provider_id, "provider_id", 128))
        if self.consumer_id == self.provider_id:
            raise RelationInvalide("une relation ne peut pas boucler sur elle-même")
        object.__setattr__(self, "object", _texte(self.object, "object", 500))
        object.__setattr__(self, "environment", _environnement(self.environment))
        predicate = str(self.predicate or "CONSOMME").strip().upper()
        if not re.fullmatch(r"[A-Z_]{1,40}", predicate):
            raise RelationInvalide(f"prédicat invalide : {self.predicate!r}")
        object.__setattr__(self, "predicate", predicate)
        mode = str(self.mode or "DECLARED").strip().upper()
        if mode not in MODES_RELATION:
            raise RelationInvalide(f"mode inconnu : {self.mode!r}")
        object.__setattr__(self, "mode", mode)
        state = str(self.state or "supposee").strip().lower()
        if state == "proposee":
            state = "supposee"
        if state not in ETATS_RELATION:
            raise RelationInvalide(f"état de relation inconnu : {self.state!r}")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "confidence", _confiance(self.confidence))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "consumer_owner", _texte(
            self.consumer_owner, "consumer_owner", 200, obligatoire=False))
        object.__setattr__(self, "provider_owner", _texte(
            self.provider_owner, "provider_owner", 200, obligatoire=False))
        object.__setattr__(self, "justification", _texte(
            self.justification, "justification", 1000, obligatoire=False))
        object.__setattr__(self, "unknowns", tuple(
            dict.fromkeys(str(x) for x in (self.unknowns or ()) if str(x).strip())))
        object.__setattr__(self, "created_at", _instant(self.created_at))
        object.__setattr__(self, "reviewed_by", _texte(
            self.reviewed_by, "reviewed_by", 200, obligatoire=False))
        object.__setattr__(self, "reviewed_at", _instant(self.reviewed_at) if self.reviewed_at else "")
        object.__setattr__(self, "review_note", _texte(
            self.review_note, "review_note", 2000, obligatoire=False))
        object.__setattr__(self, "confirmations", tuple(
            dict.fromkeys(str(x).strip() for x in (self.confirmations or ()) if str(x).strip())))
        object.__setattr__(self, "critique", bool(self.critique))
        object.__setattr__(self, "last_observed_at", _instant(self.last_observed_at)
                           if self.last_observed_at else "")
        object.__setattr__(self, "transport", _kind(self.transport))
        object.__setattr__(self, "portee", _portee_exposition(self.portee))
        object.__setattr__(self, "boundary_evidence", tuple(
            dict.fromkeys(str(x) for x in (self.boundary_evidence or ()) if str(x).strip())))
        object.__setattr__(self, "via", _texte(self.via, "via", 200, obligatoire=False))
        object.__setattr__(self, "consumer_application_id", _texte(
            self.consumer_application_id, "consumer_application_id", 128, obligatoire=False))
        object.__setattr__(self, "provider_application_id", _texte(
            self.provider_application_id, "provider_application_id", 128, obligatoire=False))

    @property
    def id(self) -> str:
        objet = re.sub(r"[^a-z0-9]+", "-", self.object.casefold()).strip("-")[:60] or "relation"
        return f"relation-{self.consumer_id}-{self.provider_id}-{objet}-{self.environment}"

    def as_dict(self) -> dict:
        return {
            "kind": "proposition_naissance",
            "tenant_id": self.tenant_id, "consumer_id": self.consumer_id,
            "provider_id": self.provider_id, "object": self.object,
            "environment": self.environment, "predicate": self.predicate,
            "mode": self.mode, "state": self.state, "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "consumer_owner": self.consumer_owner, "provider_owner": self.provider_owner,
            "justification": self.justification, "unknowns": list(self.unknowns),
            "created_at": self.created_at, "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at, "review_note": self.review_note,
            "confirmations": list(self.confirmations),
            "critique": self.critique,
            "last_observed_at": self.last_observed_at,
            "transport": self.transport, "portee": self.portee,
            "boundary_evidence": list(self.boundary_evidence), "via": self.via,
            "consumer_application_id": self.consumer_application_id,
            "provider_application_id": self.provider_application_id,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "PropositionRelation":
        if not isinstance(valeur, dict):
            raise RelationInvalide("proposition : objet attendu")
        try:
            return cls(
                tenant_id=valeur.get("tenant_id"), consumer_id=valeur.get("consumer_id"),
                provider_id=valeur.get("provider_id"), object=valeur.get("object"),
                environment=valeur.get("environment") or "inconnu",
                predicate=valeur.get("predicate") or "CONSOMME",
                mode=valeur.get("mode") or "DECLARED", state=valeur.get("state") or "supposee",
                confidence=valeur.get("confidence", 0.5),
                evidence_ids=tuple(valeur.get("evidence_ids") or ()),
                consumer_owner=valeur.get("consumer_owner") or "",
                provider_owner=valeur.get("provider_owner") or "",
                justification=valeur.get("justification") or "",
                unknowns=tuple(valeur.get("unknowns") or ()),
                created_at=valeur.get("created_at") or "",
                reviewed_by=valeur.get("reviewed_by") or "",
                reviewed_at=valeur.get("reviewed_at") or "",
                review_note=valeur.get("review_note") or "",
                confirmations=tuple(valeur.get("confirmations") or ()),
                critique=bool(valeur.get("critique")),
                last_observed_at=valeur.get("last_observed_at") or "",
                transport=valeur.get("transport") or "HTTP",
                portee=valeur.get("portee") or "UNKNOWN",
                boundary_evidence=tuple(valeur.get("boundary_evidence") or ()),
                via=valeur.get("via") or "",
                consumer_application_id=valeur.get("consumer_application_id") or "",
                provider_application_id=valeur.get("provider_application_id") or "",
            )
        except (TypeError, ValueError) as exc:
            raise RelationInvalide(str(exc)) from exc


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def decider(proposition: PropositionRelation, decision: str, acteur: str, *,
            motif: str = "", confirmations=(), critique: bool = False,
            gouvernance: bool = False) -> PropositionRelation:
    """Tranche une proposition sans jamais confondre attestation et confirmation.

    - `confirmer` exige un propriétaire (consommateur ou fournisseur) ou un rôle de gouvernance.
    - Une relation `critique` exige les deux propriétaires dans `confirmations`.
    - `contester` peut être fait par un propriétaire ou la gouvernance, avec un motif.
    """
    acteur = _texte(acteur, "acteur", 200)
    gestion = str(decision or "").strip().lower()
    if gestion not in ("confirmer", "contester"):
        raise RelationInvalide("décision attendue : confirmer ou contester")
    if not isinstance(proposition, PropositionRelation):
        raise RelationInvalide("PropositionRelation attendue")
    autorise = (gouvernance or acteur in {proposition.consumer_owner, proposition.provider_owner})
    if not autorise:
        raise AutoriteInsuffisante(
            "seul un propriétaire de la relation ou la gouvernance peut la trancher")
    if gestion == "contester":
        return replace(
            proposition, state="contestee", reviewed_by=acteur, reviewed_at=_maintenant(),
            review_note=_texte(motif, "motif", 2000, obligatoire=False))
    if proposition.mode == "PROPOSED":
        raise RelationInvalide(
            "Twin provisoire : la relation ne peut pas être confirmée avant sa promotion")
    confirmes = tuple(dict.fromkeys([
        *proposition.confirmations,
        *(str(x).strip() for x in (confirmations or ()) if str(x).strip()),
        acteur,
    ]))
    if critique:
        requis = {proposition.consumer_owner, proposition.provider_owner} - {""}
        if not requis.issubset(set(confirmes)):
            return replace(
                proposition, state="validation", confirmations=confirmes,
                reviewed_by=acteur, reviewed_at=_maintenant(),
                review_note=_texte(motif, "motif", 2000, obligatoire=False))
    return replace(
        proposition, state="confirmee", confirmations=confirmes,
        reviewed_by=acteur, reviewed_at=_maintenant(),
        review_note=_texte(motif, "motif", 2000, obligatoire=False))


def marquer_observee(proposition: PropositionRelation, *, observed_at: str = "",
                     evidence_ids=()) -> PropositionRelation:
    """L'observation runtime renforce la relation sans la confirmer à la place du propriétaire."""
    preuves = tuple(dict.fromkeys([*proposition.evidence_ids,
                                   *(str(x) for x in (evidence_ids or ()) if str(x).strip())]))
    return replace(proposition, state="observee", mode="OBSERVED", confidence=min(1.0, proposition.confidence + 0.1),
                   last_observed_at=_instant(observed_at), evidence_ids=preuves)


def marquer_obsolete(proposition: PropositionRelation, *, motif: str = "") -> PropositionRelation:
    return replace(proposition, state="obsolete", review_note=_texte(
        motif or proposition.review_note, "motif", 2000, obligatoire=False))
