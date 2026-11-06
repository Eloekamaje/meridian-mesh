"""Découverte des liens : bindings de destination, résolution et cas non résolus.

Le modèle ne confond jamais :

- un échange extrait (une référence logique) ;
- un binding de déploiement (une propriété, une route de passerelle, un service) ;
- une destination résolue vers un Twin ;
- une observation runtime.

Une résolution peut être `resolved`, `ambiguous` ou `missing_evidence`. Un cas non résolu
est un objet durable, avec la question exacte et la prochaine vérification.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

__all__ = [
    "KINDS_BINDING",
    "STATUTS_CASE",
    "STATUTS_RESOLUTION",
    "Binding",
    "CandidatResolution",
    "DestinationResolution",
    "ResolutionCase",
    "ResolutionInvalide",
]

KINDS_BINDING = ("PROPERTY", "GATEWAY_ROUTE", "SERVICE", "ALIAS", "JNDI",
                 "QUEUE", "TOPIC", "DATABASE", "FILE")
STATUTS_RESOLUTION = ("resolved", "ambiguous", "missing_evidence")
STATUTS_CASE = ("open", "resolved", "abandoned")


def _texte(valeur, champ, maximum=500, obligatoire=True) -> str:
    texte = " ".join(str(valeur or "").split())
    if not texte:
        if obligatoire:
            raise ValueError(f"{champ} obligatoire")
        return ""
    if len(texte) > maximum:
        raise ValueError(f"{champ} trop long (maximum {maximum})")
    return texte


def _kind(valeur) -> str:
    texte = str(valeur or "").strip().upper()
    if texte not in KINDS_BINDING:
        raise ValueError(f"type de binding inconnu : {valeur!r}")
    return texte


def _statut(valeur, permis) -> str:
    texte = str(valeur or "").strip().lower()
    if texte not in permis:
        raise ValueError(f"statut inconnu : {valeur!r}")
    return texte


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


_CLES_SECRETES = frozenset({"password", "passwd", "secret", "token", "credential",
                            "authorization", "api_key", "apikey", "access_key", "private_key"})


def _sans_secret(valeur: str, champ: str) -> str:
    if "://" not in valeur:
        return valeur
    try:
        parties = urlsplit(valeur)
    except ValueError as exc:
        raise ValueError(f"{champ} : URL invalide") from exc
    if parties.username is not None or parties.password is not None or "@" in parties.netloc:
        raise ValueError(f"{champ} : identifiants interdits dans une URL")
    for cle, _ in parse_qsl(parties.query, keep_blank_values=True):
        if cle.strip().lower() in _CLES_SECRETES:
            raise ValueError(f"{champ} : secret interdit dans une URL")
    return valeur


def _identifiant(valeur, prefixe="resolution") -> str:
    texte = _texte(valeur, "identifiant", 1000)
    return f"{prefixe}-{hashlib.sha256(texte.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class Binding:
    """Un lien de configuration : nom logique -> cible, dans un environnement."""

    kind: str
    nom: str
    valeur: str
    environment: str = "inconnu"
    source: str = ""
    evidence_ids: tuple[str, ...] = ()
    owner: str = ""

    def __post_init__(self):
        object.__setattr__(self, "kind", _kind(self.kind))
        object.__setattr__(self, "nom", _texte(self.nom, "nom", 500))
        object.__setattr__(self, "valeur", _sans_secret(
            _texte(self.valeur, "valeur", 1000), "valeur"))
        object.__setattr__(self, "environment", str(self.environment or "inconnu").strip().lower())
        object.__setattr__(self, "source", _sans_secret(
            _texte(self.source, "source", 300, obligatoire=False), "source"))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "owner", _texte(self.owner, "owner", 200, obligatoire=False))

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "nom": self.nom, "valeur": self.valeur,
            "environment": self.environment, "source": self.source,
            "evidence_ids": list(self.evidence_ids), "owner": self.owner,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "Binding":
        if not isinstance(valeur, dict):
            raise ValueError("binding : objet attendu")
        return cls(
            kind=valeur.get("kind"), nom=valeur.get("nom"), valeur=valeur.get("valeur"),
            environment=valeur.get("environment") or "inconnu",
            source=valeur.get("source") or "",
            evidence_ids=tuple(valeur.get("evidence_ids") or ()),
            owner=valeur.get("owner") or "",
        )


@dataclass(frozen=True)
class DestinationResolution:
    status: str = "missing_evidence"
    target_twin_id: str = ""
    target_service: str = ""
    target_operation: str = ""
    candidates: tuple[dict, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    chain: tuple[str, ...] = ()
    missing_evidence: str = ""
    next_check: str = ""

    def __post_init__(self):
        object.__setattr__(self, "status", _statut(self.status, STATUTS_RESOLUTION))
        object.__setattr__(self, "target_twin_id", _texte(
            self.target_twin_id, "target_twin_id", 128, obligatoire=False))
        object.__setattr__(self, "target_service", _texte(
            self.target_service, "target_service", 300, obligatoire=False))
        object.__setattr__(self, "target_operation", _texte(
            self.target_operation, "target_operation", 500, obligatoire=False))
        object.__setattr__(self, "candidates", tuple(self.candidates or ()))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "chain", tuple(str(x) for x in (self.chain or ())))
        object.__setattr__(self, "missing_evidence", _texte(
            self.missing_evidence, "missing_evidence", 1000, obligatoire=False))
        object.__setattr__(self, "next_check", _texte(
            self.next_check, "next_check", 1000, obligatoire=False))

    @property
    def resolved(self) -> bool:
        return self.status == "resolved" and bool(self.target_twin_id)

    def as_dict(self) -> dict:
        return {
            "status": self.status, "target_twin_id": self.target_twin_id,
            "target_service": self.target_service, "target_operation": self.target_operation,
            "candidates": list(self.candidates), "evidence_ids": list(self.evidence_ids),
            "chain": list(self.chain), "missing_evidence": self.missing_evidence,
            "next_check": self.next_check,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "DestinationResolution":
        if not isinstance(valeur, dict):
            raise ValueError("résolution : objet attendu")
        return cls(**{cle: valeur.get(cle) for cle in (
            "status", "target_twin_id", "target_service", "target_operation",
            "candidates", "evidence_ids", "chain", "missing_evidence", "next_check")})


@dataclass(frozen=True)
class CandidatResolution:
    """Une hypothèse de destination, jamais une confirmation."""

    twin_id: str
    service: str = ""
    confidence: float = 0.5
    reason: str = ""
    evidence_ids: tuple[str, ...] = ()
    source: str = "AGENT"
    status: str = "proposed"
    bindings: tuple[dict, ...] = ()
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "twin_id", _texte(self.twin_id, "twin_id", 128))
        object.__setattr__(self, "service", _texte(
            self.service, "service", 300, obligatoire=False))
        try:
            confiance = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("confiance attendue entre 0 et 1") from exc
        if not 0 <= confiance <= 1:
            raise ValueError("confiance attendue entre 0 et 1")
        object.__setattr__(self, "confidence", confiance)
        object.__setattr__(self, "reason", _texte(
            self.reason, "reason", 2000, obligatoire=False))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "status", _statut(self.status, ("proposed", "accepted", "rejected")))
        object.__setattr__(self, "bindings", tuple(self.bindings or ()))
        identifiant = self.id or _identifiant(
            f"{self.twin_id}|{self.service}|{self.source}", "candidat")
        object.__setattr__(self, "id", identifiant)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "twin_id": self.twin_id, "service": self.service,
            "confidence": self.confidence, "reason": self.reason,
            "evidence_ids": list(self.evidence_ids), "source": self.source,
            "status": self.status, "bindings": list(self.bindings),
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "CandidatResolution":
        if not isinstance(valeur, dict):
            raise ValueError("candidat : objet attendu")
        return cls(
            twin_id=valeur.get("twin_id"), service=valeur.get("service") or "",
            confidence=valeur.get("confidence", 0.5), reason=valeur.get("reason") or "",
            evidence_ids=tuple(valeur.get("evidence_ids") or ()),
            source=valeur.get("source") or "AGENT",
            status=valeur.get("status") or "proposed",
            bindings=tuple(valeur.get("bindings") or ()), id=valeur.get("id") or "",
        )


@dataclass(frozen=True)
class ResolutionCase:
    tenant_id: str
    twin_id: str
    reference: str
    environment: str = "inconnu"
    status: str = "open"
    missing_evidence: str = ""
    next_check: str = ""
    owner: str = ""
    attempts: int = 0
    created_at: str = ""
    updated_at: str = ""
    evidence_ids: tuple[str, ...] = ()
    candidates: tuple[dict, ...] = ()
    target_twin_id: str = ""
    resolved_at: str = ""
    id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, "tenant_id", 128))
        object.__setattr__(self, "twin_id", _texte(self.twin_id, "twin_id", 128))
        object.__setattr__(self, "reference", _texte(self.reference, "reference", 500))
        object.__setattr__(self, "environment", str(self.environment or "inconnu").strip().lower())
        object.__setattr__(self, "status", _statut(self.status, STATUTS_CASE))
        object.__setattr__(self, "missing_evidence", _texte(
            self.missing_evidence, "missing_evidence", 1000, obligatoire=False))
        object.__setattr__(self, "next_check", _texte(
            self.next_check, "next_check", 1000, obligatoire=False))
        object.__setattr__(self, "owner", _texte(self.owner, "owner", 200, obligatoire=False))
        object.__setattr__(self, "attempts", max(0, int(self.attempts or 0)))
        object.__setattr__(self, "created_at", _instant(self.created_at))
        object.__setattr__(self, "updated_at", _instant(self.updated_at or self.created_at))
        object.__setattr__(self, "evidence_ids", tuple(
            dict.fromkeys(str(x) for x in (self.evidence_ids or ()) if str(x).strip())))
        object.__setattr__(self, "candidates", tuple(self.candidates or ()))
        object.__setattr__(self, "target_twin_id", _texte(
            self.target_twin_id, "target_twin_id", 128, obligatoire=False))
        object.__setattr__(self, "resolved_at", _instant(self.resolved_at) if self.resolved_at else "")
        identifiant = self.id or _identifiant(
            f"{self.tenant_id}|{self.twin_id}|{self.reference}|{self.environment}")
        object.__setattr__(self, "id", identifiant)

    def as_dict(self) -> dict:
        return {
            "kind": "resolution_case", "id": self.id, "tenant_id": self.tenant_id,
            "twin_id": self.twin_id, "reference": self.reference,
            "environment": self.environment, "status": self.status,
            "missing_evidence": self.missing_evidence, "next_check": self.next_check,
            "owner": self.owner, "attempts": self.attempts,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "evidence_ids": list(self.evidence_ids), "candidates": list(self.candidates),
            "target_twin_id": self.target_twin_id, "resolved_at": self.resolved_at,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "ResolutionCase":
        if not isinstance(valeur, dict):
            raise ValueError("cas de résolution : objet attendu")
        return cls(**{cle: valeur.get(cle) for cle in (
            "tenant_id", "twin_id", "reference", "environment", "status",
            "missing_evidence", "next_check", "owner", "attempts",
            "created_at", "updated_at", "evidence_ids", "candidates",
            "target_twin_id", "resolved_at", "id")})
