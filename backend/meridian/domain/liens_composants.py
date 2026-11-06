"""Liens entre composants : producteurs, consommateurs, déploiements et soupçons.

Le modèle sépare quatre choses qu'un nom d'API confond souvent :

- un **composant** (frontend, backend, worker, batch, passerelle) ;
- une **interface** exposée par un composant (route HTTP, opération SOAP, file JMS) ;
- un **appel** émis par un composant (URL, propriété, nom de service, file) ;
- un **déploiement** qui relie un composant à un service, un hôte et une route de passerelle.

Un `LienPropose` n'est jamais une vérité : c'est un soupçon avec ses preuves, ses inconnues et
la prochaine vérification. La revue humaine le confirme, le rejette ou le conteste.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from meridian.domain.naissance_relationnelle import PORTEES_ELIGIBLES, PORTEES_EXPOSITION

__all__ = [
    "PROTOCOLES",
    "SOURCES_PREUVE",
    "ETATS_LIEN",
    "TYPES_COMPOSANT",
    "Appel",
    "Composant",
    "Configuration",
    "Deploiement",
    "ExtractionDepot",
    "IdentiteDeclaree",
    "Interface",
    "LienPropose",
    "Preuve",
    "QuestionLien",
    "RapportLiens",
    "RoutePasserelle",
    "SourceDepot",
]

PROTOCOLES = ("HTTP", "SOAP", "JMS", "KAFKA", "DB", "GRPC", "GRAPHQL", "ASYNCAPI",
              "BATCH", "FILE", "AUTRE")
SOURCES_PREUVE = ("CODE", "CONFIG", "CONTRAT", "HELM", "DEPLOIEMENT", "TRACE", "DECLARATION")
MODES_PREUVE = ("DECLARE", "OBSERVE", "DEDUIT")
ETATS_LIEN = ("suggere", "confirme", "conteste", "rejete")
TYPES_COMPOSANT = ("APPLICATION", "FRONTEND", "BACKEND", "SERVICE", "WORKER",
                   "BATCH", "GATEWAY", "ESB", "RESSOURCE")
VERIFICATIONS = ("implemente", "configure", "observe")
NATURES_LIEN = ("mesh", "interne", "externe")
TYPES_QUESTION = ("PROPRIETE_ABSENTE", "SERVICE_INCONNU", "PRODUCTEUR_INCONNU",
                  "AMBIGU", "CONTRADICTION")

_CLES_SECRETES = frozenset({
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "apikey", "access_key", "private_key", "client_secret",
})


def _texte(valeur, champ, maximum=500, obligatoire=True) -> str:
    texte = " ".join(str(valeur or "").split())
    if not texte:
        if obligatoire:
            raise ValueError(f"{champ} obligatoire")
        return ""
    if len(texte) > maximum:
        raise ValueError(f"{champ} trop long (maximum {maximum})")
    return texte


def _choix(valeur, permis, champ) -> str:
    texte = str(valeur or "").strip()
    for autorise in permis:
        if texte.casefold() == str(autorise).casefold():
            return autorise
    raise ValueError(f"{champ} inconnu : {valeur!r}")


def _environnement(valeur) -> str:
    texte = str(valeur or "inconnu").strip().lower()
    if texte not in ("prod", "preprod", "recette", "dev", "inconnu"):
        raise ValueError(f"environnement inconnu : {valeur!r}")
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


def _sans_secret(valeur: str, champ: str) -> str:
    texte = str(valeur or "").strip()
    if "@" in texte and "://" in texte:
        raise ValueError(f"{champ} : identifiants interdits dans une URL")
    return texte


def _identifiant(prefixe: str, *parties) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return f"{prefixe}-{hashlib.sha256(brut.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class Preuve:
    """Une origine datée et localisée, jamais une conclusion."""

    source: str
    locator: str
    detail: str = ""
    mode: str = "DECLARE"
    observed_at: str = ""
    confidence: float = 0.8
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "source", _choix(self.source, SOURCES_PREUVE, "source"))
        object.__setattr__(self, "locator", _texte(self.locator, "locator", 1000))
        object.__setattr__(self, "detail", _sans_secret(
            _texte(self.detail, "detail", 1000, obligatoire=False), "detail"))
        object.__setattr__(self, "mode", _choix(self.mode, MODES_PREUVE, "mode"))
        object.__setattr__(self, "observed_at",
                           _instant(self.observed_at) if self.observed_at else "")
        object.__setattr__(self, "confidence", _confiance(self.confidence))
        object.__setattr__(self, "id", self.id or _identifiant(
            "preuve", self.source, self.locator, self.detail, self.mode))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "source": self.source, "locator": self.locator,
            "detail": self.detail, "mode": self.mode,
            "observed_at": self.observed_at, "confidence": self.confidence,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "Preuve":
        if not isinstance(valeur, dict):
            raise ValueError("preuve : objet attendu")
        return cls(**{cle: valeur.get(cle) for cle in (
            "source", "locator", "detail", "mode", "observed_at", "confidence", "id")})


@dataclass(frozen=True)
class Composant:
    application_id: str
    nom: str
    type: str = "SERVICE"
    owner: str = ""
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "application_id", _texte(self.application_id, "application_id", 128))
        object.__setattr__(self, "nom", _texte(self.nom, "nom", 300))
        object.__setattr__(self, "type", _choix(self.type, TYPES_COMPOSANT, "type"))
        object.__setattr__(self, "owner", _texte(self.owner, "owner", 200, obligatoire=False))
        object.__setattr__(self, "id", self.id or _identifiant(
            "composant", self.application_id, self.nom))

    def as_dict(self) -> dict:
        return {"id": self.id, "application_id": self.application_id, "nom": self.nom,
                "type": self.type, "owner": self.owner}


@dataclass(frozen=True)
class Interface:
    """Ce qu'un composant expose : une route, une opération SOAP ou une file."""

    composant_id: str
    application_id: str
    protocole: str
    operation: str
    methode: str = ""
    chemin: str = ""
    nom: str = ""
    environment: str = "inconnu"
    portee: str = "UNKNOWN"
    source_kind: str = "CODE"
    role: str = "FOURNISSEUR"
    service_name: str = ""
    context_path: str = ""
    contrat_ref: str = ""
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "composant_id", _texte(self.composant_id, "composant_id", 300))
        object.__setattr__(self, "application_id", _texte(self.application_id, "application_id", 128))
        object.__setattr__(self, "protocole", _choix(self.protocole, PROTOCOLES, "protocole"))
        object.__setattr__(self, "operation", _sans_secret(
            _texte(self.operation, "operation", 800), "operation"))
        object.__setattr__(self, "methode", _texte(
            self.methode, "methode", 40, obligatoire=False).upper())
        object.__setattr__(self, "chemin", _sans_secret(
            _texte(self.chemin, "chemin", 800, obligatoire=False), "chemin"))
        object.__setattr__(self, "nom", _texte(self.nom, "nom", 500, obligatoire=False))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "portee", _choix(self.portee, PORTEES_EXPOSITION, "portee"))
        object.__setattr__(self, "source_kind", _choix(self.source_kind, SOURCES_PREUVE, "source_kind"))
        object.__setattr__(self, "role", _choix(self.role, ("FOURNISSEUR", "CONSOMMATEUR"), "role"))
        object.__setattr__(self, "service_name", _texte(
            self.service_name, "service_name", 300, obligatoire=False))
        object.__setattr__(self, "context_path", _texte(
            self.context_path, "context_path", 300, obligatoire=False))
        object.__setattr__(self, "contrat_ref", _texte(
            self.contrat_ref, "contrat_ref", 300, obligatoire=False))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "interface", self.application_id, self.composant_id, self.protocole,
            self.operation, self.environment))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "composant_id": self.composant_id,
            "application_id": self.application_id, "protocole": self.protocole,
            "operation": self.operation, "methode": self.methode, "chemin": self.chemin,
            "nom": self.nom, "environment": self.environment, "portee": self.portee,
            "source_kind": self.source_kind, "role": self.role,
            "service_name": self.service_name, "context_path": self.context_path,
            "contrat_ref": self.contrat_ref,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class Appel:
    """Ce qu'un composant appelle : une URL, une propriété, un service ou une file."""

    composant_id: str
    application_id: str
    protocole: str
    cible: str
    cible_type: str = "URL"
    methode: str = "ANY"
    chemin: str = ""
    operation: str = ""
    environment: str = "inconnu"
    source_kind: str = "CODE"
    role: str = "CONSOMMATEUR"
    origine: str = ""
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "composant_id", _texte(
            self.composant_id, "composant_id", 300, obligatoire=False))
        object.__setattr__(self, "application_id", _texte(
            self.application_id, "application_id", 128, obligatoire=False))
        object.__setattr__(self, "protocole", _choix(self.protocole, PROTOCOLES, "protocole"))
        object.__setattr__(self, "cible", _sans_secret(
            _texte(self.cible, "cible", 1000, obligatoire=False), "cible"))
        object.__setattr__(self, "cible_type", _choix(
            self.cible_type, ("URL", "SERVICE", "PROPRIETE", "CHEMIN", "JNDI", "QUEUE"), "cible_type"))
        object.__setattr__(self, "methode", _texte(
            self.methode, "methode", 40, obligatoire=False).upper())
        object.__setattr__(self, "chemin", _sans_secret(
            _texte(self.chemin, "chemin", 800, obligatoire=False), "chemin"))
        object.__setattr__(self, "operation", _texte(
            self.operation, "operation", 800, obligatoire=False))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "source_kind", _choix(self.source_kind, SOURCES_PREUVE, "source_kind"))
        object.__setattr__(self, "role", _choix(self.role, ("FOURNISSEUR", "CONSOMMATEUR"), "role"))
        object.__setattr__(self, "origine", _texte(
            self.origine, "origine", 500, obligatoire=False))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "appel", self.application_id, self.composant_id, self.protocole,
            self.methode, self.cible, self.environment, self.origine))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "composant_id": self.composant_id,
            "application_id": self.application_id, "protocole": self.protocole,
            "cible": self.cible, "cible_type": self.cible_type, "methode": self.methode,
            "chemin": self.chemin, "operation": self.operation,
            "environment": self.environment, "source_kind": self.source_kind,
            "role": self.role, "origine": self.origine,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class Configuration:
    cle: str
    valeur: str
    fichier: str
    environment: str = "inconnu"
    source_kind: str = "CONFIG"
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "cle", _texte(self.cle, "cle", 500))
        if any(marque in self.cle.casefold() for marque in _CLES_SECRETES):
            raise ValueError(f"clé secrète refusée : {self.cle}")
        object.__setattr__(self, "valeur", _sans_secret(
            _texte(self.valeur, "valeur", 2000, obligatoire=False), "valeur"))
        object.__setattr__(self, "fichier", _texte(self.fichier, "fichier", 1000))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "source_kind", _choix(self.source_kind, SOURCES_PREUVE, "source_kind"))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "config", self.fichier, self.cle, self.environment))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "cle": self.cle, "valeur": self.valeur,
            "fichier": self.fichier, "environment": self.environment,
            "source_kind": self.source_kind,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class RoutePasserelle:
    chemin: str
    service: str
    host: str = ""
    environment: str = "inconnu"
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "chemin", _sans_secret(
            _texte(self.chemin, "chemin", 500), "chemin"))
        object.__setattr__(self, "service", _texte(self.service, "service", 300))
        object.__setattr__(self, "host", _texte(self.host, "host", 300, obligatoire=False))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "route", self.host, self.chemin, self.service, self.environment))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "chemin": self.chemin, "service": self.service,
            "host": self.host, "environment": self.environment,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class Deploiement:
    composant_id: str
    application_id: str
    environment: str = "inconnu"
    service_name: str = ""
    hosts: tuple[str, ...] = ()
    images: tuple[str, ...] = ()
    routes: tuple[RoutePasserelle, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict)
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "composant_id", _texte(self.composant_id, "composant_id", 300))
        object.__setattr__(self, "application_id", _texte(self.application_id, "application_id", 128))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "service_name", _texte(
            self.service_name, "service_name", 300, obligatoire=False))
        object.__setattr__(self, "hosts", tuple(dict.fromkeys(
            str(host).strip().lower() for host in (self.hosts or ()) if str(host).strip())))
        object.__setattr__(self, "images", tuple(dict.fromkeys(
            str(image).strip() for image in (self.images or ()) if str(image).strip())))
        object.__setattr__(self, "routes", tuple(self.routes or ()))
        object.__setattr__(self, "labels", {str(cle): str(valeur)
                                            for cle, valeur in (self.labels or {}).items()})
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "deploiement", self.application_id, self.composant_id,
            self.environment, self.service_name))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "composant_id": self.composant_id,
            "application_id": self.application_id, "environment": self.environment,
            "service_name": self.service_name, "hosts": list(self.hosts),
            "images": list(self.images),
            "routes": [route.as_dict() for route in self.routes],
            "labels": dict(self.labels),
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class IdentiteDeclaree:
    """Une information manquante complétée par un humain, avec son auteur et sa preuve."""

    service_name: str
    composant_id: str
    application_id: str
    environment: str = "inconnu"
    acteur: str = ""
    preuve: Preuve | None = None
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "service_name", _texte(self.service_name, "service_name", 300))
        object.__setattr__(self, "composant_id", _texte(self.composant_id, "composant_id", 300))
        object.__setattr__(self, "application_id", _texte(self.application_id, "application_id", 128))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "acteur", _texte(self.acteur, "acteur", 200))
        if self.preuve is not None and not isinstance(self.preuve, Preuve):
            object.__setattr__(self, "preuve", Preuve.depuis_dict(self.preuve))
        object.__setattr__(self, "id", self.id or _identifiant(
            "identite", self.service_name, self.composant_id, self.environment))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "service_name": self.service_name,
            "composant_id": self.composant_id, "application_id": self.application_id,
            "environment": self.environment, "acteur": self.acteur,
            "preuve": self.preuve.as_dict() if self.preuve else None,
        }


@dataclass(frozen=True)
class LienPropose:
    """Un soupçon de lien, avec ce qui le prouve et ce qui manque encore."""

    consommateur_composant_id: str
    consommateur_application_id: str
    fournisseur_composant_id: str
    fournisseur_application_id: str
    operation: str
    protocole: str = "HTTP"
    environment: str = "inconnu"
    fournisseur_service: str = ""
    interface_id: str = ""
    portee: str = "UNKNOWN"
    nature: str = "mesh"
    state: str = "suggere"
    confiance: float = 0.5
    verifications: tuple[str, ...] = ()
    preuves: tuple[Preuve, ...] = ()
    unknowns: tuple[str, ...] = ()
    missing_evidence: str = ""
    next_check: str = ""
    id: str = ""

    def __post_init__(self):
        for nom in ("consommateur_composant_id", "consommateur_application_id"):
            object.__setattr__(self, nom, _texte(getattr(self, nom), nom, 300))
        fournisseur = _texte(self.fournisseur_composant_id, "fournisseur_composant_id",
                             300, obligatoire=False)
        object.__setattr__(self, "fournisseur_composant_id", fournisseur)
        object.__setattr__(self, "fournisseur_application_id", _texte(
            self.fournisseur_application_id, "fournisseur_application_id", 128, obligatoire=False))
        object.__setattr__(self, "operation", _sans_secret(
            _texte(self.operation, "operation", 800), "operation"))
        object.__setattr__(self, "protocole", _choix(self.protocole, PROTOCOLES, "protocole"))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "fournisseur_service", _texte(
            self.fournisseur_service, "fournisseur_service", 300, obligatoire=False))
        object.__setattr__(self, "interface_id", _texte(
            self.interface_id, "interface_id", 300, obligatoire=False))
        object.__setattr__(self, "portee", _choix(self.portee, PORTEES_EXPOSITION, "portee"))
        object.__setattr__(self, "nature", _choix(self.nature, NATURES_LIEN, "nature"))
        object.__setattr__(self, "state", _choix(self.state, ETATS_LIEN, "state"))
        object.__setattr__(self, "confiance", _confiance(self.confiance))
        object.__setattr__(self, "verifications", tuple(
            dict.fromkeys(str(x).lower() for x in (self.verifications or ())
                          if str(x).lower() in VERIFICATIONS)))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "unknowns", tuple(
            dict.fromkeys(str(x) for x in (self.unknowns or ()) if str(x).strip())))
        object.__setattr__(self, "missing_evidence", _texte(
            self.missing_evidence, "missing_evidence", 1000, obligatoire=False))
        object.__setattr__(self, "next_check", _texte(
            self.next_check, "next_check", 1000, obligatoire=False))
        object.__setattr__(self, "id", self.id or _identifiant(
            "lien", self.consommateur_composant_id, self.fournisseur_composant_id,
            self.operation, self.environment, self.interface_id))

    @property
    def eligible(self) -> bool:
        return (self.nature == "mesh" and self.state not in ("conteste", "rejete")
                and self.portee in PORTEES_ELIGIBLES
                and bool(self.fournisseur_application_id))

    @property
    def fort(self) -> bool:
        return {"implemente", "configure"} <= set(self.verifications)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "consommateur_composant_id": self.consommateur_composant_id,
            "consommateur_application_id": self.consommateur_application_id,
            "fournisseur_composant_id": self.fournisseur_composant_id,
            "fournisseur_application_id": self.fournisseur_application_id,
            "fournisseur_service": self.fournisseur_service,
            "interface_id": self.interface_id, "operation": self.operation,
            "protocole": self.protocole, "environment": self.environment,
            "portee": self.portee, "nature": self.nature, "state": self.state,
            "confiance": self.confiance, "verifications": list(self.verifications),
            "eligible": self.eligible,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
            "unknowns": list(self.unknowns),
            "missing_evidence": self.missing_evidence,
            "next_check": self.next_check,
        }


@dataclass(frozen=True)
class QuestionLien:
    """Ce que le moteur ne sait pas encore, avec la question exacte à poser."""

    type: str
    sujet: str
    question: str
    environment: str = "inconnu"
    composant_id: str = ""
    application_id: str = ""
    candidats: tuple[dict, ...] = ()
    missing_evidence: str = ""
    next_check: str = ""
    preuves: tuple[Preuve, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "type", _choix(self.type, TYPES_QUESTION, "type"))
        object.__setattr__(self, "sujet", _texte(self.sujet, "sujet", 800))
        object.__setattr__(self, "question", _texte(self.question, "question", 1500))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "composant_id", _texte(
            self.composant_id, "composant_id", 300, obligatoire=False))
        object.__setattr__(self, "application_id", _texte(
            self.application_id, "application_id", 128, obligatoire=False))
        object.__setattr__(self, "candidats", tuple(self.candidats or ()))
        object.__setattr__(self, "missing_evidence", _texte(
            self.missing_evidence, "missing_evidence", 1000, obligatoire=False))
        object.__setattr__(self, "next_check", _texte(
            self.next_check, "next_check", 1000, obligatoire=False))
        object.__setattr__(self, "preuves", tuple(self.preuves or ()))
        object.__setattr__(self, "id", self.id or _identifiant(
            "question", self.type, self.sujet, self.environment))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "sujet": self.sujet,
            "question": self.question, "environment": self.environment,
            "composant_id": self.composant_id,
            "application_id": self.application_id,
            "candidats": list(self.candidats),
            "missing_evidence": self.missing_evidence,
            "next_check": self.next_check,
            "preuves": [preuve.as_dict() for preuve in self.preuves],
        }


@dataclass(frozen=True)
class RapportLiens:
    liens: tuple[LienPropose, ...] = ()
    questions: tuple[QuestionLien, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def mesh(self) -> tuple[LienPropose, ...]:
        return tuple(lien for lien in self.liens if lien.nature == "mesh")

    @property
    def internes(self) -> tuple[LienPropose, ...]:
        return tuple(lien for lien in self.liens if lien.nature == "interne")

    @property
    def externes(self) -> tuple[LienPropose, ...]:
        return tuple(lien for lien in self.liens if lien.nature == "externe")

    @property
    def contradictions(self) -> tuple[LienPropose, ...]:
        return tuple(lien for lien in self.liens if lien.state == "conteste")

    def as_dict(self) -> dict:
        return {
            "liens": [lien.as_dict() for lien in self.liens],
            "mesh": [lien.as_dict() for lien in self.mesh],
            "internes": [lien.as_dict() for lien in self.internes],
            "externes": [lien.as_dict() for lien in self.externes],
            "contradictions": [lien.as_dict() for lien in self.contradictions],
            "questions": [question.as_dict() for question in self.questions],
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class SourceDepot:
    """Un dépôt ou un artefact, avec l'application et le composant qu'il décrit."""

    application_id: str
    composant_id: str
    fichiers: Mapping[str, str]
    environment: str = "prod"
    owner: str = ""
    type_composant: str = "SERVICE"

    def __post_init__(self):
        object.__setattr__(self, "application_id", _texte(self.application_id, "application_id", 128))
        object.__setattr__(self, "composant_id", _texte(self.composant_id, "composant_id", 300))
        object.__setattr__(self, "fichiers", dict(self.fichiers or {}))
        object.__setattr__(self, "environment", _environnement(self.environment))
        object.__setattr__(self, "owner", _texte(self.owner, "owner", 200, obligatoire=False))
        object.__setattr__(self, "type_composant", _choix(
            self.type_composant, TYPES_COMPOSANT, "type_composant"))


@dataclass(frozen=True)
class ExtractionDepot:
    composant: Composant
    interfaces: tuple[Interface, ...] = ()
    appels: tuple[Appel, ...] = ()
    deploiements: tuple[Deploiement, ...] = ()
    configurations: tuple[Configuration, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "composant": self.composant.as_dict(),
            "interfaces": [interface.as_dict() for interface in self.interfaces],
            "appels": [appel.as_dict() for appel in self.appels],
            "deploiements": [deploiement.as_dict() for deploiement in self.deploiements],
            "configurations": [configuration.as_dict() for configuration in self.configurations],
            "diagnostics": list(self.diagnostics),
        }
