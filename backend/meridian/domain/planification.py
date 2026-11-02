"""Modèle canonique de capacité, charge, planification et prévision.

Aucun champ d'éditeur (Jira, Azure DevOps, etc.) n'entre ici : les adapters normalisent leurs
données vers ces objets. Les story points restent relatifs à une équipe et ne sont jamais additionnés
entre équipes ni convertis en devise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from typing import Any, Iterable

UNITES = ("points", "heures", "jours", "items")
STATUTS = ("a_faire", "en_cours", "termine", "annule", "inconnu")
CATEGORIES_CHARGE = ("engagee", "planifiee", "non_planifiee", "inconnue")
ROLES = (
    "observateur", "membre", "scrum_master", "engineering_manager", "po",
    "pmo", "finance", "sponsor", "architecte", "ops", "audit", "admin",
)
NIVEAUX = ("lecture", "proposition", "approbation", "decision")
ACTIONS = (
    "lire_resume", "lire_equipe", "lire_charge", "lire_prevision", "lire_budget",
    "simuler", "proposer_plan", "gerer_roles", "synchroniser",
)


def _texte(valeur: Any, nom: str, *, vide: bool = False) -> str:
    texte = str(valeur or "").strip()
    if not texte and not vide:
        raise ValueError(f"{nom} requis")
    return texte[:500]


def normaliser_unite(valeur: Any) -> str:
    unite = str(valeur or "").strip().lower()
    if unite not in UNITES:
        raise ValueError(f"unité inconnue : {valeur!r} (attendues : {', '.join(UNITES)})")
    return unite


def normaliser_statut(valeur: Any) -> str:
    """Normalise les statuts les plus fréquents sans prétendre à une sémantique unique par outil."""
    texte = str(valeur or "").strip().lower().replace("-", "_").replace(" ", "_")
    if texte in STATUTS:
        return texte
    if texte in {"done", "closed", "resolved", "terminée", "termine", "terminé", "livre", "livré"}:
        return "termine"
    if texte in {"in_progress", "inprogress", "doing", "en_cours", "en_cours_developpement", "active"}:
        return "en_cours"
    if texte in {"cancelled", "canceled", "annule", "annulé", "rejected"}:
        return "annule"
    if texte in {"to_do", "todo", "backlog", "open", "a_faire", "à_faire", "new"}:
        return "a_faire"
    return "inconnu"


def normaliser_categorie(valeur: Any) -> str:
    texte = str(valeur or "inconnue").strip().lower()
    return texte if texte in CATEGORIES_CHARGE else "inconnue"


def normaliser_role(valeur: Any) -> str:
    role = str(valeur or "").strip().lower()
    if role not in ROLES:
        raise ValueError(f"rôle inconnu : {valeur!r}")
    return role


@dataclass(frozen=True)
class Estimation:
    valeur: float
    unite: str
    methode: str = "declaree"

    def __post_init__(self):
        if not isfinite(float(self.valeur)) or float(self.valeur) < 0:
            raise ValueError("estimation : valeur positive ou nulle attendue")
        object.__setattr__(self, "valeur", float(self.valeur))
        object.__setattr__(self, "unite", normaliser_unite(self.unite))
        object.__setattr__(self, "methode", _texte(self.methode, "méthode", vide=True) or "declaree")


@dataclass(frozen=True)
class ElementTravail:
    id: str
    source: str
    external_id: str
    equipe_id: str
    titre: str
    statut: str = "inconnu"
    priorite: str = "inconnue"
    type: str = "item"
    estimation: Estimation | None = None
    categorie_charge: str = "planifiee"
    cycle_id: str | None = None
    release_id: str | None = None
    parent_id: str | None = None
    assigne: str | None = None
    observe_le: str | None = None
    actif: bool = True

    def __post_init__(self):
        for nom in ("id", "source", "external_id", "equipe_id", "titre"):
            object.__setattr__(self, nom, _texte(getattr(self, nom), nom))
        object.__setattr__(self, "statut", normaliser_statut(self.statut))
        object.__setattr__(self, "categorie_charge", normaliser_categorie(self.categorie_charge))
        object.__setattr__(self, "priorite", str(self.priorite or "inconnue").strip().lower())


@dataclass(frozen=True)
class Capacite:
    equipe_id: str
    debut: date
    fin: date
    unite: str
    valeur: float
    confiance: float = 0.5
    source: str = "declaree"
    fraicheur: str | None = None

    def __post_init__(self):
        if self.fin < self.debut:
            raise ValueError("capacité : fin antérieure au début")
        if not isfinite(float(self.valeur)) or float(self.valeur) < 0:
            raise ValueError("capacité : valeur positive ou nulle attendue")
        object.__setattr__(self, "unite", normaliser_unite(self.unite))
        object.__setattr__(self, "valeur", float(self.valeur))
        object.__setattr__(self, "confiance", min(1.0, max(0.0, float(self.confiance))))


@dataclass(frozen=True)
class Charge:
    equipe_id: str
    unite: str
    engagee: float = 0.0
    planifiee: float = 0.0
    non_planifiee: float = 0.0
    inconnue: float = 0.0
    elements_sans_estimation: int = 0

    @property
    def total(self) -> float:
        return self.engagee + self.planifiee + self.non_planifiee + self.inconnue

    @property
    def connue(self) -> float:
        return self.engagee + self.planifiee + self.non_planifiee


def agreger_charge(elements: Iterable[ElementTravail]) -> dict[tuple[str, str], Charge]:
    """Agrège par (équipe, unité). Les éléments sans estimation sont comptés, jamais devinés."""
    resultat: dict[tuple[str, str], Charge] = {}
    for element in elements:
        if not element.actif or element.statut in {"termine", "annule"}:
            continue
        if element.estimation is None:
            cle = (element.equipe_id, "items")
            courant = resultat.get(cle, Charge(element.equipe_id, "items"))
            resultat[cle] = Charge(
                courant.equipe_id, courant.unite, courant.engagee, courant.planifiee,
                courant.non_planifiee, courant.inconnue + 1, courant.elements_sans_estimation + 1)
            continue
        cle = (element.equipe_id, element.estimation.unite)
        courant = resultat.get(cle, Charge(element.equipe_id, element.estimation.unite))
        valeurs = {
            "engagee": courant.engagee, "planifiee": courant.planifiee,
            "non_planifiee": courant.non_planifiee, "inconnue": courant.inconnue,
        }
        categorie = element.categorie_charge
        valeurs[categorie] = valeurs.get(categorie, 0.0) + element.estimation.valeur
        resultat[cle] = Charge(
            element.equipe_id, element.estimation.unite,
            valeurs["engagee"], valeurs["planifiee"], valeurs["non_planifiee"],
            valeurs["inconnue"], courant.elements_sans_estimation)
    return resultat


def marge(capacite: float | None, charge: float | None) -> float | None:
    """Marge dans la même unité ; None si l'une des deux valeurs est inconnue."""
    if capacite is None or charge is None:
        return None
    return float(capacite) - float(charge)


def role_autorise(role: str, action: str) -> bool:
    """Matrice minimale ; les détails de périmètre restent dans l'application."""
    role = normaliser_role(role)
    if role == "admin":
        return True
    if role == "observateur":
        return action in {"lire_resume", "lire_equipe", "lire_charge"}
    if role == "membre":
        return action in {"lire_resume", "lire_equipe", "lire_charge"}
    if role == "scrum_master":
        return action in {"lire_resume", "lire_equipe", "lire_charge", "simuler"}
    if role in {"engineering_manager", "po"}:
        return action in {"lire_resume", "lire_equipe", "lire_charge", "lire_prevision",
                          "lire_budget", "simuler", "proposer_plan"}
    if role == "pmo":
        return action in {"lire_resume", "lire_equipe", "lire_charge", "lire_prevision",
                          "lire_budget", "simuler", "proposer_plan"}
    if role == "finance":
        return action in {"lire_resume", "lire_prevision", "lire_budget", "simuler"}
    if role == "sponsor":
        return action in {"lire_resume", "lire_prevision", "lire_budget"}
    if role == "architecte":
        return action in {"lire_resume", "lire_equipe", "lire_charge", "lire_prevision",
                          "simuler"}
    if role == "ops":
        return action in {"lire_resume", "lire_equipe", "lire_charge"}
    if role == "audit":
        return action in {"lire_resume", "lire_equipe", "lire_charge", "lire_prevision",
                          "lire_budget"}
    return False


def role_depuis_valeur(valeur: Any) -> str:
    try:
        return normaliser_role(valeur)
    except ValueError:
        return "observateur"


def date_ou_none(valeur: Any) -> date | None:
    if valeur is None or valeur == "":
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    return date.fromisoformat(str(valeur)[:10])
