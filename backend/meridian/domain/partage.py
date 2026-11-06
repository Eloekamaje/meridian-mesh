"""Partage de connaissance : le Claim reste privé, `claim_share` est le seul acte de partage.

La visibilité effective est **dérivée** des partages actifs et de la confidentialité la plus forte
entre le Claim et ses preuves. Un partage ne peut jamais élever la visibilité : il ne peut que la
restreindre ou l'ouvrir dans la limite de la confidentialité.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

__all__ = [
    "CONFIDENTIALITES",
    "PROJECTIONS",
    "SCOPES",
    "Consommateur",
    "Partage",
    "PartageInvalide",
    "autoriser",
    "confidentialite_effective",
    "external_autorise",
    "projeter",
    "scope_correspond",
]

SCOPES = ("TEAM", "TWIN", "PORTFOLIO", "TENANT", "EXTERNAL")
_EXTERNAL_VRAI = ("1", "true", "oui", "yes")
PROJECTIONS = ("SUMMARY", "EVIDENCE")
CONFIDENTIALITES = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET")
_RANG = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "SECRET": 3}


class PartageInvalide(ValueError):
    """Un partage ne respecte pas les invariants de visibilité."""


def external_autorise() -> bool:
    """La publication hors tenant est opt-in : désactivée tant que la variable ne l'ouvre pas."""
    valeur = str(os.environ.get("JUMEAU_EXTERNAL_PUBLICATION", "") or "").strip().lower()
    return valeur in _EXTERNAL_VRAI


@dataclass(frozen=True)
class Consommateur:
    """Identité de lecture : le tenant est la frontière dure, les autres champs sont les scopes."""

    tenant_id: str
    team_id: str = ""
    twin_id: str = ""
    portfolio_id: str = ""
    external_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.tenant_id or "").strip():
            raise PartageInvalide("tenant_id obligatoire")
        for champ in ("team_id", "twin_id", "portfolio_id", "external_id"):
            object.__setattr__(self, champ, str(getattr(self, champ) or "").strip())


@dataclass(frozen=True)
class Partage:
    """Un acte de partage daté et révocable ; jamais une propriété permanente du Claim."""

    claim_id: int
    scope_type: str
    scope_id: str
    projection: str = "SUMMARY"
    granted_by: str = ""
    reviewed_by: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        type_ = str(self.scope_type or "").strip().upper()
        projection = str(self.projection or "").strip().upper()
        if type_ not in SCOPES:
            raise PartageInvalide(
                f"scope_type inconnu : {self.scope_type!r} (attendus : {', '.join(SCOPES)})"
            )
        if projection not in PROJECTIONS:
            raise PartageInvalide(
                f"projection inconnue : {self.projection!r} (attendues : {', '.join(PROJECTIONS)})"
            )
        if not str(self.scope_id or "").strip():
            raise PartageInvalide("scope_id obligatoire")
        if not str(self.granted_by or "").strip():
            raise PartageInvalide("granted_by obligatoire")
        object.__setattr__(self, "scope_type", type_)
        object.__setattr__(self, "projection", projection)


def _get(objet: Any, nom: str, defaut: Any = None) -> Any:
    if objet is None:
        return defaut
    if isinstance(objet, Mapping):
        valeur = objet.get(nom, defaut)
    else:
        valeur = getattr(objet, nom, defaut)
    return defaut if valeur is None else valeur


def _texte(objet: Any, nom: str, defaut: str = "") -> str:
    return str(_get(objet, nom, defaut) or defaut).strip()


def _enum(objet: Any, nom: str, defaut: str = "") -> str:
    return _texte(objet, nom, defaut).upper()


def _instant(valeur: Any) -> datetime:
    """Datetime UTC depuis un datetime, une date ISO ou une chaîne vide."""
    if valeur is None or valeur == "":
        return datetime.now(timezone.utc)
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    try:
        resultat = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PartageInvalide(f"date invalide : {valeur!r}") from exc
    return resultat if resultat.tzinfo else resultat.replace(tzinfo=timezone.utc)


def confidentialite_effective(claim: Any, preuves=()) -> str:
    """La confidentialité la plus forte entre le Claim et ses preuves.

    Une preuve `CONFIDENTIAL` rend le Claim `CONFIDENTIAL` ; une preuve `SECRET` le rend
    intransmissible, même si le Claim est déclaré `PUBLIC`.
    """
    niveaux = [_enum(claim, "confidentialite", "INTERNAL")]
    niveaux.extend(_enum(preuve, "confidentialite", "INTERNAL") for preuve in preuves)
    inconnues = sorted({n for n in niveaux if n not in _RANG})
    if inconnues:
        raise PartageInvalide(
            f"confidentialité inconnue : {', '.join(inconnues)} "
            f"(attendues : {', '.join(CONFIDENTIALITES)})"
        )
    return max(niveaux, key=lambda niveau: _RANG[niveau])


def scope_correspond(partage: Any, consommateur: Consommateur) -> bool:
    """Le consommateur appartient-il au scope du partage ?"""
    type_ = _enum(partage, "scope_type")
    scope_id = _texte(partage, "scope_id")
    if type_ == "TENANT":
        return scope_id == consommateur.tenant_id
    if type_ == "TEAM":
        return bool(consommateur.team_id) and scope_id == consommateur.team_id
    if type_ == "TWIN":
        return bool(consommateur.twin_id) and scope_id == consommateur.twin_id
    if type_ == "PORTFOLIO":
        return bool(consommateur.portfolio_id) and scope_id == consommateur.portfolio_id
    if type_ == "EXTERNAL":
        return bool(consommateur.external_id) and scope_id == consommateur.external_id
    return False


def _actif(partage: Any, reference: datetime) -> bool:
    if _get(partage, "revoked_at") is not None:
        return False
    debut = _get(partage, "valid_from")
    fin = _get(partage, "valid_to")
    if debut is not None and reference < _instant(debut):
        return False
    if fin is not None and reference >= _instant(fin):
        return False
    return True


def autoriser(
    claim: Any,
    preuves=(),
    partages=(),
    consommateur: Consommateur | None = None,
    *,
    reference: Any = None,
) -> str | None:
    """Niveau de projection autorisé pour ce consommateur, ou None.

    Règles :
    - le tenant est une frontière dure ;
    - l'owner voit toujours son propre Claim ;
    - `SECRET` n'est jamais partagé ;
    - `CONFIDENTIAL` n'est partagé qu'en `SUMMARY`, et seulement avec une revue ;
    - un partage ne peut pas élever la confidentialité.
    """
    if consommateur is None:
        raise PartageInvalide("consommateur obligatoire")
    if _texte(claim, "tenant_id") != consommateur.tenant_id:
        return None
    if consommateur.twin_id and _texte(claim, "jumeau_id") == consommateur.twin_id:
        return "EVIDENCE"
    if _enum(claim, "confidentialite", "INTERNAL") == "SECRET":
        return None
    effective = confidentialite_effective(claim, preuves)
    if effective == "SECRET":
        return None
    instant = _instant(reference) if reference is not None else datetime.now(timezone.utc)
    niveaux: set[str] = set()
    for partage in partages:
        if not _actif(partage, instant) or not scope_correspond(partage, consommateur):
            continue
        projection = _enum(partage, "projection", "SUMMARY")
        if projection not in PROJECTIONS:
            continue
        if effective == "CONFIDENTIAL":
            if projection == "SUMMARY" and _texte(partage, "reviewed_by"):
                niveaux.add("SUMMARY")
            continue
        niveaux.add(projection)
    if "EVIDENCE" in niveaux:
        return "EVIDENCE"
    if "SUMMARY" in niveaux:
        return "SUMMARY"
    return None


def projeter(claim: Any, preuves=(), niveau: str | None = None) -> dict[str, Any] | None:
    """Vue d'un Claim pour un niveau donné ; `EVIDENCE` ajoute les localisateurs de preuve."""
    if niveau not in PROJECTIONS:
        return None
    champs = (
        "id", "jumeau_id", "sujet", "predicat", "objet", "type", "statut", "maturite",
        "confiance", "confidentialite", "valide_depuis", "valide_jusqua",
    )
    resultat = {champ: _get(claim, champ) for champ in champs if _get(claim, champ) is not None}
    resultat["projection"] = niveau
    if niveau == "EVIDENCE":
        resultat["preuves"] = [
            {champ: _get(preuve, champ) for champ in
             ("locator", "chemin", "sha", "ligne_debut", "ligne_fin", "hash")}
            for preuve in preuves
        ]
    return resultat
