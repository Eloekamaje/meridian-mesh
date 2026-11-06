"""Socle de l'écosystème tiers : types, prédicats, autorités et validation des Claims.

Ce module applique ADR-0030 sans base, sans réseau et sans modèle. Une responsabilité n'est
jamais un champ libre : c'est un ``ClaimTiers`` qui porte un sujet, un prédicat, un objet, un
statut, une preuve localisée, une autorité de source et une temporalité. Le nom affiché n'est
jamais une identité : ``twin_id`` reste l'identifiant canonique et ``application_id`` est
optionnel, jamais généré.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
from typing import Any
import unicodedata

__all__ = [
    "AUTORITE_SOURCES",
    "ClaimTiers",
    "ClaimTiersInvalide",
    "IdentifiantsTiers",
    "PREDICATS",
    "PREDICATS_RESPONSABILITE",
    "PreuveLocalisee",
    "ROLE_PAR_TYPE",
    "SOURCES",
    "STATUTS",
    "STATUTS_CLAIM",
    "TYPES_TIERS",
    "TYPES_TWIN",
    "TYPES_TWIN_TIERS",
    "TwinTiers",
    "TwinTiersInvalide",
    "autorite_autorisee",
    "est_application_candidate",
    "est_application_non_resolue",
    "est_actif_a",
    "est_claim_de_responsabilite",
    "est_non_applicatif",
    "etat_a_date",
    "identifiant_canonique",
    "normaliser_autorite",
    "normaliser_predicat",
    "normaliser_statut",
    "normaliser_statut_identite",
    "normaliser_type_twin",
    "preuve_de",
    "preuve_est_localisee",
    "valider_claim",
    "valider_twin_tiers",
]

TYPES_TIERS = ("APPLICATION", "TEAM", "RESOURCE", "SUPPLIER", "ECOSYSTEM")
TYPES_TWIN = TYPES_TIERS
TYPES_TWIN_TIERS = TYPES_TIERS

ROLE_PAR_TYPE = {
    "TEAM": "equipe",
    "SUPPLIER": "fournisseur",
    "RESOURCE": "ressource",
    "APPLICATION": "application",
}

PREDICATS = (
    "FOURNISSEUR_FOURNIT",
    "EQUIPE_EST_ACCOUNTABLE_DE",
    "EQUIPE_EST_RESPONSABLE_DE",
    "CONTRAT_COUVRE",
    "RESOURCE_SUPPORTE_APPLICATION",
    "APPLICATION_DEPEND_DE_RESSOURCE",
    "RESPONSABILITE_LIMITEE_A",
)
PREDICATS_RESPONSABILITE = PREDICATS

STATUTS = ("ETABLI", "HISTORIQUE", "SUPPOSE", "CONTESTE", "INCONNU")
STATUTS_CLAIM = STATUTS

SOURCES = ("CONTRAT", "CMDB", "ITSM", "DOCUMENTATION", "TEAMS")

# Une autorité n'est admise que pour les prédicats qu'elle peut réellement prouver.
AUTORITE_SOURCES = {
    "FOURNISSEUR_FOURNIT": ("CONTRAT", "CMDB", "ITSM", "DOCUMENTATION"),
    "EQUIPE_EST_ACCOUNTABLE_DE": ("ITSM", "DOCUMENTATION", "TEAMS"),
    "EQUIPE_EST_RESPONSABLE_DE": ("ITSM", "DOCUMENTATION", "TEAMS", "CONTRAT"),
    "CONTRAT_COUVRE": ("CONTRAT",),
    "RESOURCE_SUPPORTE_APPLICATION": ("CMDB", "ITSM", "DOCUMENTATION"),
    "APPLICATION_DEPEND_DE_RESSOURCE": ("CMDB", "ITSM", "DOCUMENTATION"),
    "RESPONSABILITE_LIMITEE_A": ("CONTRAT", "DOCUMENTATION", "TEAMS"),
}

STATUTS_IDENTITE = ("CANONIQUE", "CANDIDAT", "NON_RESOLU")
_CHAMPS_IDENTIFIANTS = ("application_id", "resource_id", "supplier_id", "team_id")


class ClaimTiersInvalide(ValueError):
    """Un Claim de l'écosystème tiers ne respecte pas un invariant d'ADR-0030."""


class TwinTiersInvalide(ValueError):
    """Un Twin de l'écosystème tiers ne respecte pas un invariant d'ADR-0030."""


def _normaliser_cle(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")
    return texte.upper()


def _texte(valeur: Any) -> str:
    if valeur is None or isinstance(valeur, (bytes, bytearray, Mapping)):
        return ""
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()


def _texte_ou_none(valeur: Any) -> str | None:
    texte = _texte(valeur)
    return texte or None


def _texte_obligatoire(valeur: Any, champ: str) -> str:
    texte = _texte(valeur)
    if not texte:
        raise ClaimTiersInvalide(f"{champ} obligatoire")
    return texte


def normaliser_type_twin(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def normaliser_predicat(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def normaliser_statut(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def normaliser_autorite(valeur: Any) -> str:
    return _normaliser_cle(valeur)


def normaliser_statut_identite(valeur: Any) -> str:
    cle = _normaliser_cle(valeur) or "CANONIQUE"
    return "NON_RESOLU" if cle == "UNRESOLVED" else cle


def _en_datetime(valeur: Any) -> datetime | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime(valeur.year, valeur.month, valeur.day, tzinfo=timezone.utc)
    elif isinstance(valeur, str):
        try:
            instant = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


@dataclass(frozen=True)
class PreuveLocalisee:
    """Preuve d'un Claim : l'emplacement de la source et le localisateur exact dans celle-ci."""

    emplacement: str = ""
    localisateur: str = ""
    extrait: str | None = None
    ligne_debut: int | None = None
    ligne_fin: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "emplacement": self.emplacement,
            "localisateur": self.localisateur,
            "extrait": self.extrait,
            "ligne_debut": self.ligne_debut,
            "ligne_fin": self.ligne_fin,
        }


@dataclass(frozen=True)
class IdentifiantsTiers:
    """Identités métier externes d'un Twin ; aucune n'est déduite du nom ni générée."""

    application_id: str | None = None
    resource_id: str | None = None
    supplier_id: str | None = None
    team_id: str | None = None
    externes: tuple[tuple[str, str], ...] = ()

    @classmethod
    def depuis(cls, valeur: Any) -> "IdentifiantsTiers":
        if valeur is None:
            return cls()
        if isinstance(valeur, cls):
            return valeur
        if not isinstance(valeur, Mapping):
            raise TwinTiersInvalide("identifiants doit être un mapping ou IdentifiantsTiers")
        connus: dict[str, str] = {}
        externes: list[tuple[str, str]] = []
        for cle, brut in valeur.items():
            nom = str(cle or "").strip()
            texte = _texte_ou_none(brut)
            if not nom or texte is None:
                continue
            if nom in _CHAMPS_IDENTIFIANTS:
                connus[nom] = texte
            else:
                externes.append((nom, texte))
        return cls(**connus, externes=tuple(sorted(externes)))

    def valeur(self, nom: str) -> str | None:
        if nom in _CHAMPS_IDENTIFIANTS:
            return getattr(self, nom)
        return dict(self.externes).get(nom)

    def comme_dict(self) -> dict[str, str]:
        resultat = {
            nom: getattr(self, nom)
            for nom in _CHAMPS_IDENTIFIANTS
            if getattr(self, nom)
        }
        resultat.update(dict(self.externes))
        return resultat


@dataclass(frozen=True)
class ClaimTiers:
    """Affirmation temporelle et prouvée sur l'écosystème, jamais un champ libre.

    Les valeurs sont conservées telles quelles : ``valider_claim`` valide les invariants sans
    muter le Claim, ce qui permet aux projections de référencer l'objet d'origine.
    """

    sujet: str
    predicat: str
    objet: str
    statut: str = "SUPPOSE"
    preuve: PreuveLocalisee | Mapping[str, Any] | None = None
    autorite: str | None = None
    valid_from: str | date | datetime | None = None
    valid_to: str | date | datetime | None = None
    confiance: float | None = None
    texte: str = ""
    id: str | None = None


@dataclass(frozen=True)
class TwinTiers:
    """Twin de l'écosystème : identité stable, type explicite et Claims attachés par référence."""

    twin_id: str
    type: str
    nom: str = ""
    perimetre: str = ""
    identifiants: IdentifiantsTiers | Mapping[str, Any] | None = None
    sources: tuple[str, ...] = ()
    statut_identite: str = "CANONIQUE"
    claims: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        identifiant = _texte(self.twin_id)
        if not identifiant:
            raise TwinTiersInvalide("twin_id obligatoire")
        type_twin = normaliser_type_twin(self.type)
        if type_twin not in TYPES_TIERS:
            raise TwinTiersInvalide(
                f"type de Twin inconnu : {self.type!r} (attendus : {', '.join(TYPES_TIERS)})"
            )
        identifiants = IdentifiantsTiers.depuis(self.identifiants)
        statut = normaliser_statut_identite(self.statut_identite)
        if statut not in STATUTS_IDENTITE:
            raise TwinTiersInvalide(
                f"statut d'identité inconnu : {self.statut_identite!r} "
                f"(attendus : {', '.join(STATUTS_IDENTITE)})"
            )
        if type_twin == "APPLICATION":
            if identifiants.application_id is None and statut == "CANONIQUE":
                # Sans App ID, une application reste candidate : jamais promue, jamais
                # identifiée par son nom et aucun application_id n'est généré.
                statut = "CANDIDAT"
        elif statut != "CANONIQUE":
            raise TwinTiersInvalide(
                "le statut d'identité CANDIDAT ou NON_RESOLU est réservé aux APPLICATIONS"
            )
        sources = self.sources
        if isinstance(sources, str):
            sources = (sources,)
        claims = self.claims
        if claims is None:
            claims = ()
        elif isinstance(claims, (ClaimTiers, Mapping)):
            claims = (claims,)
        object.__setattr__(self, "twin_id", identifiant)
        object.__setattr__(self, "type", type_twin)
        object.__setattr__(self, "nom", _texte(self.nom))
        object.__setattr__(self, "perimetre", _texte(self.perimetre))
        object.__setattr__(self, "identifiants", identifiants)
        object.__setattr__(self, "sources", tuple(_texte(s) for s in sources if _texte(s)))
        object.__setattr__(self, "statut_identite", statut)
        object.__setattr__(self, "claims", tuple(claims))

    @property
    def application_id(self) -> str | None:
        return self.identifiants.application_id

    @property
    def est_application(self) -> bool:
        return self.type == "APPLICATION"

    @property
    def est_non_applicatif(self) -> bool:
        return self.type != "APPLICATION"

    def identifiant(self) -> str:
        return self.twin_id


def valider_twin_tiers(twin: Any) -> TwinTiers:
    """Valide un Twin de l'écosystème et le rend inchangé, sans générer d'identité."""
    if not isinstance(twin, TwinTiers):
        raise TwinTiersInvalide("TwinTiers attendu")
    return twin


def _localisateur_lignes(debut: Any, fin: Any) -> str:
    if debut in (None, ""):
        return ""
    if fin in (None, ""):
        return f"#L{debut}"
    return f"#L{debut}-L{fin}"


def _preuve_lue(preuve: Any) -> PreuveLocalisee | None:
    if preuve is None:
        return None
    if isinstance(preuve, PreuveLocalisee):
        emplacement = _texte(preuve.emplacement)
        localisateur = _texte(preuve.localisateur)
        if not localisateur and "#" in emplacement:
            emplacement, localisateur = emplacement.rsplit("#", 1)
            localisateur = f"#{localisateur.strip()}"
            emplacement = emplacement.strip()
        elif not emplacement and "#" in localisateur:
            emplacement, localisateur = localisateur.rsplit("#", 1)
            localisateur = f"#{localisateur.strip()}"
            emplacement = emplacement.strip()
        if not localisateur and emplacement:
            localisateur = _localisateur_lignes(preuve.ligne_debut, preuve.ligne_fin)
        if (emplacement, localisateur) == (
                _texte(preuve.emplacement), _texte(preuve.localisateur)):
            return preuve
        return PreuveLocalisee(
            emplacement=emplacement,
            localisateur=localisateur,
            extrait=preuve.extrait,
            ligne_debut=preuve.ligne_debut,
            ligne_fin=preuve.ligne_fin,
        )
    if isinstance(preuve, str):
        texte = _texte(preuve)
        if not texte:
            return None
        if "#" in texte:
            emplacement, localisateur = texte.rsplit("#", 1)
            return PreuveLocalisee(
                emplacement=emplacement.strip(),
                localisateur=f"#{localisateur.strip()}",
            )
        if "://" in texte:
            return PreuveLocalisee(emplacement=texte, localisateur=texte)
        return PreuveLocalisee(emplacement=texte, localisateur="")
    if isinstance(preuve, Mapping):
        emplacement = _texte(preuve.get("emplacement") or preuve.get("source")
                             or preuve.get("chemin"))
        localisateur = _texte(preuve.get("localisateur") or preuve.get("locator")
                              or preuve.get("localisation"))
        debut = preuve.get("ligne_debut")
        fin = preuve.get("ligne_fin")
        if not emplacement and "#" in localisateur:
            emplacement, localisateur = localisateur.rsplit("#", 1)
            localisateur = f"#{localisateur.strip()}"
            emplacement = emplacement.strip()
        if not localisateur and emplacement:
            localisateur = _localisateur_lignes(debut, fin)
        return PreuveLocalisee(
            emplacement=emplacement,
            localisateur=localisateur,
            extrait=_texte_ou_none(preuve.get("extrait")),
            ligne_debut=debut,
            ligne_fin=fin,
        )
    raise ClaimTiersInvalide("preuve localisée attendue (PreuveLocalisee, mapping ou locator)")


def preuve_de(claim: Any) -> PreuveLocalisee | None:
    if isinstance(claim, Mapping):
        return _preuve_lue(claim.get("preuve") or claim.get("preuve_localisee"))
    return _preuve_lue(getattr(claim, "preuve", None))


def _entier_positif(valeur: Any, champ: str) -> int | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, bool):
        raise ClaimTiersInvalide(f"{champ} doit être un entier positif")
    try:
        entier = int(valeur)
    except (TypeError, ValueError) as exc:
        raise ClaimTiersInvalide(f"{champ} doit être un entier positif") from exc
    if entier < 1:
        raise ClaimTiersInvalide(f"{champ} doit être un entier positif")
    return entier


def preuve_est_localisee(preuve: Any) -> bool:
    """Vrai seulement si l'emplacement et le localisateur exact sont tous deux renseignés."""
    try:
        lue = _preuve_lue(preuve)
    except ClaimTiersInvalide:
        return False
    if lue is None:
        return False
    emplacement = _texte(lue.emplacement)
    localisateur = _texte(lue.localisateur)
    if not emplacement or not localisateur:
        return False
    try:
        debut = _entier_positif(lue.ligne_debut, "ligne_debut")
        fin = _entier_positif(lue.ligne_fin, "ligne_fin")
    except ClaimTiersInvalide:
        return False
    return not (debut is not None and fin is not None and debut > fin)


def autorite_autorisee(predicat: Any, autorite: Any) -> bool:
    cle = normaliser_predicat(predicat)
    source = normaliser_autorite(autorite)
    return source in AUTORITE_SOURCES.get(cle, ())


def est_claim_de_responsabilite(claim: Any) -> bool:
    """Tous les prédicats d'ADR-0030 sont des responsabilités ou des liens de responsabilité."""
    predicat = claim.get("predicat") if isinstance(claim, Mapping) else getattr(claim, "predicat", None)
    return normaliser_predicat(predicat) in PREDICATS


def _verifier_temporalite(claim: ClaimTiers) -> None:
    debut = _en_datetime(claim.valid_from)
    fin = _en_datetime(claim.valid_to)
    if claim.valid_from not in (None, "") and debut is None:
        raise ClaimTiersInvalide("valid_from doit être une date ISO")
    if claim.valid_to not in (None, "") and fin is None:
        raise ClaimTiersInvalide("valid_to doit être une date ISO")
    if debut is not None and fin is not None and fin <= debut:
        raise ClaimTiersInvalide("valid_to doit suivre valid_from (fin exclue)")


def valider_claim(claim: ClaimTiers) -> ClaimTiers:
    """Valide un Claim de responsabilité, sans le muter.

    Refuse notamment un Claim sans preuve localisée, sans autorité, avec une autorité inconnue
    ou non admise pour son prédicat. Une temporalité invalide est également refusée.
    """
    if not isinstance(claim, ClaimTiers):
        raise ClaimTiersInvalide("ClaimTiers attendu")
    _texte_obligatoire(claim.sujet, "sujet")
    _texte_obligatoire(claim.objet, "objet")
    predicat = normaliser_predicat(claim.predicat)
    if predicat not in PREDICATS:
        raise ClaimTiersInvalide(
            f"prédicat inconnu : {claim.predicat!r} (attendus : {', '.join(PREDICATS)})"
        )
    statut = normaliser_statut(claim.statut)
    if statut not in STATUTS:
        raise ClaimTiersInvalide(
            f"statut inconnu : {claim.statut!r} (attendus : {', '.join(STATUTS)})"
        )
    if not preuve_est_localisee(claim.preuve):
        raise ClaimTiersInvalide(
            f"{predicat} exige une preuve localisée (emplacement et localisateur)"
        )
    autorite = normaliser_autorite(claim.autorite)
    if not autorite:
        raise ClaimTiersInvalide(f"{predicat} exige une autorité de source")
    if autorite not in SOURCES:
        raise ClaimTiersInvalide(
            f"autorité inconnue : {claim.autorite!r} (attendues : {', '.join(SOURCES)})"
        )
    autorisees = AUTORITE_SOURCES[predicat]
    if autorite not in autorisees:
        raise ClaimTiersInvalide(
            f"autorité {autorite} non admise pour {predicat} "
            f"(admises : {', '.join(autorisees)})"
        )
    _verifier_temporalite(claim)
    if claim.confiance is not None:
        try:
            confiance = float(claim.confiance)
        except (TypeError, ValueError) as exc:
            raise ClaimTiersInvalide("confiance doit être un nombre entre 0 et 1") from exc
        if not 0.0 <= confiance <= 1.0:
            raise ClaimTiersInvalide("confiance doit être comprise entre 0 et 1")
    return claim


def est_actif_a(claim: ClaimTiers, reference: Any) -> bool:
    """Validité temporelle du Claim : début inclus, fin exclue ; une date invalide vaut faux."""
    if reference is None:
        return True
    instant = _en_datetime(reference)
    if instant is None:
        return False
    debut = _en_datetime(claim.valid_from)
    fin = _en_datetime(claim.valid_to)
    if claim.valid_from not in (None, "") and debut is None:
        return False
    if claim.valid_to not in (None, "") and fin is None:
        return False
    if debut is not None and instant < debut:
        return False
    if fin is not None and instant >= fin:
        return False
    return True


def etat_a_date(claim: ClaimTiers, reference: Any = None) -> str:
    """État effectif : un Claim hors de sa période devient HISTORIQUE, jamais établi."""
    statut = normaliser_statut(claim.statut)
    if statut == "HISTORIQUE":
        return "HISTORIQUE"
    if reference is not None and not est_actif_a(claim, reference):
        return "HISTORIQUE"
    return statut


def _type_de(twin: Any) -> str:
    if isinstance(twin, TwinTiers):
        return twin.type
    if isinstance(twin, Mapping):
        return normaliser_type_twin(twin.get("type"))
    return normaliser_type_twin(getattr(twin, "type", None))


def _identifiants_de(twin: Any) -> IdentifiantsTiers:
    if isinstance(twin, TwinTiers):
        return twin.identifiants
    if isinstance(twin, Mapping):
        return IdentifiantsTiers.depuis(twin.get("identifiants"))
    return IdentifiantsTiers.depuis(getattr(twin, "identifiants", None))


def _est_candidat(twin: Any, type_twin: str | None = None) -> bool:
    type_twin = type_twin or _type_de(twin)
    if type_twin != "APPLICATION":
        return False
    statut = normaliser_statut_identite(
        twin.get("statut_identite") if isinstance(twin, Mapping)
        else getattr(twin, "statut_identite", "CANONIQUE")
    )
    return (
        _identifiants_de(twin).application_id is None
        and statut in ("CANONIQUE", "CANDIDAT")
    )


def _est_non_resolue(twin: Any, type_twin: str | None = None) -> bool:
    type_twin = type_twin or _type_de(twin)
    if type_twin != "APPLICATION":
        return False
    statut = normaliser_statut_identite(
        twin.get("statut_identite") if isinstance(twin, Mapping)
        else getattr(twin, "statut_identite", "CANONIQUE")
    )
    return _identifiants_de(twin).application_id is None and statut == "NON_RESOLU"


def est_application_candidate(twin: Any) -> bool:
    """APPLICATION sans application_id : candidate par défaut, jamais promue automatiquement."""
    return _est_candidat(twin)


def est_application_non_resolue(twin: Any) -> bool:
    """APPLICATION sans application_id et explicitement non résolue."""
    return _est_non_resolue(twin)


def est_non_applicatif(twin: Any) -> bool:
    type_twin = _type_de(twin)
    return type_twin in TYPES_TIERS and type_twin != "APPLICATION"


def identifiant_canonique(twin: Any) -> str:
    """Le twin_id est l'identité canonique ; le nom affiché n'est jamais utilisé à sa place."""
    if isinstance(twin, TwinTiers):
        return twin.twin_id
    if isinstance(twin, Mapping):
        identifiant = _texte(twin.get("twin_id") or twin.get("id"))
    else:
        identifiant = _texte(getattr(twin, "twin_id", None) or getattr(twin, "id", None))
    if not identifiant:
        raise TwinTiersInvalide("twin_id obligatoire")
    return identifiant
