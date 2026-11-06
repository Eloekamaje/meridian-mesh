"""Mémoire prospective : intentions, échéances et rappels.

Une intention est une action future vérifiable. Elle n'est ni une croyance, ni un
fait : elle porte une échéance, un propriétaire, une source et un statut. Le modèle
est pur et ne lit aucune base.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Mapping

__all__ = [
    "PRIORITES",
    "SCOPES",
    "STATUTS",
    "Intention",
    "est_due",
]

STATUTS = ("a_faire", "en_cours", "fait", "annule", "expire")
SCOPES = ("tenant", "user", "session", "twin", "situation")
PRIORITES = ("basse", "normale", "haute", "critique")


def _texte(valeur, maximum=1000, obligatoire=False) -> str:
    texte = " ".join(str(valeur or "").split())[:maximum]
    if obligatoire and not texte:
        raise ValueError("texte obligatoire")
    return texte


def _choix(valeur, permis, champ) -> str:
    texte = str(valeur or "").strip().lower()
    for autorise in permis:
        if texte == autorise:
            return autorise
    raise ValueError(f"{champ} inconnu : {valeur!r}")


def _instant(valeur, champ: str) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise ValueError(f"{champ} obligatoire")
    try:
        instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{champ} : date ISO attendue") from exc
    if instant.tzinfo is None:
        raise ValueError(f"{champ} : fuseau horaire attendu")
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds")


def _identifiant(*parties) -> str:
    brut = "|".join(str(partie or "") for partie in parties)
    return "intention-" + hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Intention:
    tenant_id: str
    objet: str
    echeance: str
    scope: str = "tenant"
    scope_id: str = ""
    source: str = ""
    owner: str = ""
    statut: str = "a_faire"
    priorite: str = "normale"
    evidence_ids: tuple[str, ...] = ()
    donnees: Mapping[str, object] = field(default_factory=dict)
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        object.__setattr__(self, "tenant_id", _texte(self.tenant_id, 128, True))
        object.__setattr__(self, "objet", _texte(self.objet, 1000, True))
        object.__setattr__(self, "echeance", _instant(self.echeance, "echeance"))
        object.__setattr__(self, "scope", _choix(self.scope, SCOPES, "scope"))
        object.__setattr__(self, "scope_id", _texte(self.scope_id, 200))
        object.__setattr__(self, "source", _texte(self.source, 500))
        object.__setattr__(self, "owner", _texte(self.owner, 200))
        object.__setattr__(self, "statut", _choix(self.statut, STATUTS, "statut"))
        object.__setattr__(self, "priorite", _choix(self.priorite, PRIORITES, "priorite"))
        object.__setattr__(self, "evidence_ids", tuple(dict.fromkeys(
            str(valeur).strip() for valeur in (self.evidence_ids or ())
            if str(valeur).strip())))
        object.__setattr__(self, "donnees", dict(self.donnees or {}))
        object.__setattr__(self, "created_at", _instant(self.created_at, "created_at")
                           if self.created_at else "")
        object.__setattr__(self, "updated_at", _instant(self.updated_at, "updated_at")
                           if self.updated_at else "")
        object.__setattr__(self, "id", self.id or _identifiant(
            self.tenant_id, self.scope, self.scope_id, self.objet,
            self.source, self.echeance))

    def as_dict(self) -> dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id, "objet": self.objet,
            "echeance": self.echeance, "scope": self.scope, "scope_id": self.scope_id,
            "source": self.source, "owner": self.owner, "statut": self.statut,
            "priorite": self.priorite, "evidence_ids": list(self.evidence_ids),
            "donnees": dict(self.donnees), "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def depuis_dict(cls, valeur) -> "Intention":
        if not isinstance(valeur, Mapping):
            raise ValueError("intention : objet attendu")
        return cls(**{cle: valeur.get(cle) for cle in (
            "tenant_id", "objet", "echeance", "scope", "scope_id", "source",
            "owner", "statut", "priorite", "evidence_ids", "donnees",
            "id", "created_at", "updated_at")})


def est_due(intention, maintenant=None) -> bool:
    """Vrai si l'intention est encore ouverte et que son échéance est atteinte."""
    valeur = intention.as_dict() if isinstance(intention, Intention) else dict(intention)
    if str(valeur.get("statut") or "") not in ("a_faire", "en_cours"):
        return False
    try:
        echeance = datetime.fromisoformat(
            str(valeur.get("echeance") or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    instant = maintenant or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return echeance <= instant
