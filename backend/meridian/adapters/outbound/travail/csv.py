"""Adapters CSV : secours, migration et preuve de généricité du port SourceTravail."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _lire(chemin: str | Path) -> list[dict[str, str]]:
    with Path(chemin).open(newline="", encoding="utf-8-sig") as flux:
        return [{str(cle).strip(): (valeur or "").strip() for cle, valeur in ligne.items()}
                for ligne in csv.DictReader(flux)]


def _nombre(valeur):
    if valeur in (None, ""):
        return None
    try:
        return float(str(valeur).replace(",", "."))
    except (TypeError, ValueError):
        return None


class CsvTravail:
    provider = "csv"

    def __init__(self, configuration: dict | None = None, *_args, **_kwargs):
        self.configuration = dict(configuration or {})
        self.chemin = self.configuration.get("chemin") or self.configuration.get("path")
        self.dependances_chemin = self.configuration.get("dependances") or self.configuration.get("dependencies")
        self.equipe = self.configuration.get("equipe_id") or self.configuration.get("equipe") or "equipe-csv"
        self.temps_chemin = self.configuration.get("temps") or self.configuration.get("worklogs")

    def capacites(self) -> dict[str, bool]:
        colonnes = set()
        if self.chemin and Path(self.chemin).exists():
            with Path(self.chemin).open(newline="", encoding="utf-8-sig") as flux:
                colonnes = {str(c).strip() for c in (csv.DictReader(flux).fieldnames or [])}
        return {
            "equipes": True,
            "sprints": "cycle_id" in colonnes,
            "points": "estimation" in colonnes and "unite" in colonnes,
            "heures": True,
            "worklogs": bool(self.temps_chemin),
            "dependances": bool(self.dependances_chemin),
            "releases": "release_id" in colonnes,
            "historique": "maj_source" in colonnes,
        }

    def lister_equipes(self) -> list[dict[str, Any]]:
        equipes = {}
        for ligne in self._lignes():
            identifiant = ligne.get("equipe_id") or self.equipe
            equipes[identifiant] = {"id": identifiant, "nom": ligne.get("equipe_nom") or identifiant}
        return list(equipes.values())

    def _lignes(self) -> list[dict[str, str]]:
        if not self.chemin:
            raise RuntimeError("chemin CSV requis")
        return _lire(self.chemin)

    def lister_elements(self, depuis: str | None = None, limite: int = 500) -> list[dict[str, Any]]:
        elements = []
        for ligne in self._lignes():
            maj = ligne.get("maj_source") or ligne.get("updated")
            if depuis and maj and maj <= depuis:
                continue
            estimation = None
            valeur = _nombre(ligne.get("estimation"))
            if valeur is not None:
                estimation = {"valeur": valeur, "unite": ligne.get("unite") or "points",
                              "methode": ligne.get("methode") or "declaree"}
            elements.append({
                "external_id": ligne.get("external_id") or ligne.get("id"),
                "titre": ligne.get("titre") or ligne.get("summary") or ligne.get("id"),
                "type": ligne.get("type") or "item",
                "statut": ligne.get("statut") or ligne.get("status"),
                "priorite": ligne.get("priorite") or ligne.get("priority") or "inconnue",
                "equipe_id": ligne.get("equipe_id") or self.equipe,
                "parent_id": ligne.get("parent_id") or None,
                "cycle_id": ligne.get("cycle_id") or None,
                "release_id": ligne.get("release_id") or None,
                "categorie_charge": ligne.get("categorie_charge") or "planifiee",
                "estimation": estimation,
                "assigne": ligne.get("assigne") or None,
                "maj_source": maj or None,
                "donnees": {},
            })
            if len(elements) >= max(1, int(limite)):
                break
        return elements

    def lister_cycles(self) -> list[dict[str, Any]]:
        cycles = {}
        for ligne in self._lignes():
            identifiant = ligne.get("cycle_id")
            if identifiant:
                cycles[identifiant] = {
                    "id": identifiant, "equipe_id": ligne.get("equipe_id") or self.equipe,
                    "nom": ligne.get("cycle_nom") or identifiant,
                    "debut": ligne.get("cycle_debut") or None,
                    "fin": ligne.get("cycle_fin") or None,
                    "termine": str(ligne.get("cycle_termine", "")).lower() in {"1", "true", "oui", "yes"},
                }
        return list(cycles.values())

    def lister_releases(self) -> list[dict[str, Any]]:
        releases = {}
        for ligne in self._lignes():
            identifiant = ligne.get("release_id")
            if identifiant:
                releases[identifiant] = {
                    "id": identifiant, "nom": ligne.get("release_nom") or identifiant,
                    "date_cible": ligne.get("release_date") or None,
                    "statut": ligne.get("release_statut") or None,
                }
        return list(releases.values())

    def lister_dependances(self) -> list[dict[str, Any]]:
        if not self.dependances_chemin:
            return []
        return [{"source_element_id": l.get("source") or l.get("source_id"),
                 "cible_element_id": l.get("cible") or l.get("target_id"),
                 "type": l.get("type") or "lie"}
                for l in _lire(self.dependances_chemin)
                if (l.get("source") or l.get("source_id")) and (l.get("cible") or l.get("target_id"))]

    def lister_temps(self) -> list[dict[str, Any]]:
        if not self.temps_chemin:
            return []
        return [{
            "id": l.get("id") or f"{l.get('external_id')}@{l.get('date_travail') or l.get('date')}",
            "element_id": l.get("element_id") or l.get("external_id"),
            "equipe_id": l.get("equipe_id") or self.equipe,
            "acteur": l.get("acteur") or None,
            "date_travail": l.get("date_travail") or l.get("date"),
            "periode": l.get("periode") or None,
            "valeur": _nombre(l.get("valeur") or l.get("heures") or l.get("temps")) or 0,
            "unite": l.get("unite") or "heures", "source": "csv",
        } for l in _lire(self.temps_chemin)]


class CsvPeople:
    provider = "csv"

    def __init__(self, configuration: dict | None = None, *_args, **_kwargs):
        self.configuration = dict(configuration or {})
        self.chemin = self.configuration.get("chemin") or self.configuration.get("path")

    def _lignes(self):
        if not self.chemin:
            raise RuntimeError("chemin CSV people requis")
        return _lire(self.chemin)

    def lister_equipes(self):
        equipes = {}
        for l in self._lignes():
            if l.get("equipe_id"):
                equipes[l["equipe_id"]] = {"id": l["equipe_id"], "nom": l.get("equipe_nom") or l["equipe_id"],
                                            "domaine": l.get("domaine") or None}
        return list(equipes.values())

    def lister_membres(self, equipe_id=None):
        return [{"equipe_id": l.get("equipe_id"), "acteur": l.get("acteur"),
                 "fte": _nombre(l.get("fte")) or 1, "role": l.get("role")}
                for l in self._lignes() if l.get("acteur") and (not equipe_id or l.get("equipe_id") == equipe_id)]

    def lister_capacites(self, debut=None, fin=None):
        return [{"equipe_id": l.get("equipe_id"), "debut": l.get("debut"), "fin": l.get("fin"),
                 "unite": l.get("unite") or "jours", "valeur": _nombre(l.get("capacite")) or 0,
                 "confiance": _nombre(l.get("confiance")) or 0.5, "source": "csv"}
                for l in self._lignes() if _nombre(l.get("capacite")) is not None]

    def lister_competences(self, equipe_id=None):
        return [{"equipe_id": l.get("equipe_id"), "competence": l.get("competence"),
                 "niveau": int(_nombre(l.get("niveau")) or 0)}
                for l in self._lignes() if l.get("competence")
                and (not equipe_id or l.get("equipe_id") == equipe_id)]

    def lister_allocations(self, equipe_id=None):
        chemin = self.configuration.get("allocations")
        if not chemin:
            return []
        return [{"id": l.get("id"), "equipe_id": l.get("equipe_id") or equipe_id,
                 "acteur": l.get("acteur") or None, "element_id": l.get("element_id") or None,
                 "initiative_id": l.get("initiative_id") or None, "debut": l.get("debut") or None,
                 "fin": l.get("fin") or None, "valeur": _nombre(l.get("valeur")) or 0,
                 "unite": l.get("unite") or "pourcentage", "source": "people"}
                for l in _lire(chemin) if l.get("id")]

    def lister_absences(self, equipe_id=None, debut=None, fin=None):
        chemin = self.configuration.get("absences")
        if not chemin:
            return []
        return [{"id": l.get("id"), "equipe_id": l.get("equipe_id") or equipe_id,
                 "acteur": l.get("acteur") or None, "debut": l.get("debut"), "fin": l.get("fin"),
                 "valeur": _nombre(l.get("valeur")) or 0, "unite": l.get("unite") or "jours",
                 "source": "people"} for l in _lire(chemin) if l.get("id")]


class CsvFinance:
    provider = "csv"

    def __init__(self, configuration: dict | None = None, *_args, **_kwargs):
        self.configuration = dict(configuration or {})
        self.budgets_chemin = self.configuration.get("budgets") or self.configuration.get("chemin")
        self.couts_chemin = self.configuration.get("couts") or self.configuration.get("costs")

    def lister_budgets(self):
        if not self.budgets_chemin:
            return []
        return [{"id": l.get("id"), "initiative_id": l.get("initiative_id") or None,
                 "libelle": l.get("libelle") or l.get("id"), "devise": l.get("devise") or "EUR",
                 "enveloppe": _nombre(l.get("enveloppe")) or 0, "periode": l.get("periode") or None,
                 "source": "csv"} for l in _lire(self.budgets_chemin) if l.get("id")]

    def lister_couts(self):
        if not self.couts_chemin:
            return []
        return [{"id": l.get("id"), "budget_id": l.get("budget_id"), "equipe_id": l.get("equipe_id") or None,
                 "periode": l.get("periode") or None, "prevu": _nombre(l.get("prevu")) or 0,
                 "engage": _nombre(l.get("engage")) or 0, "reel": _nombre(l.get("reel")) or 0,
                 "forecast": _nombre(l.get("forecast")) or 0, "source": "csv"}
                for l in _lire(self.couts_chemin) if l.get("id") and l.get("budget_id")]

    def lister_taux(self):
        chemin = self.configuration.get("taux") or self.configuration.get("rates")
        if not chemin:
            return []
        return [{"id": l.get("id"), "equipe_id": l.get("equipe_id") or None,
                 "role": l.get("role") or None, "devise": l.get("devise") or "EUR",
                 "cout_heure": _nombre(l.get("cout_heure")) or 0, "debut": l.get("debut") or None,
                 "fin": l.get("fin") or None, "source": "csv"}
                for l in _lire(chemin) if l.get("id")]


class CsvIncidents:
    provider = "csv"

    def __init__(self, configuration: dict | None = None, *_args, **_kwargs):
        self.configuration = dict(configuration or {})
        self.chemin = self.configuration.get("chemin") or self.configuration.get("path")
        self.equipe = self.configuration.get("equipe_id") or "equipe-csv"

    def lister_equipes(self):
        return [{"id": self.equipe, "nom": self.equipe}]

    def lister_charge_non_planifiee(self, debut=None, fin=None):
        return [{
            "external_id": l.get("external_id") or l.get("id"),
            "titre": l.get("titre") or l.get("description") or l.get("id"),
            "equipe_id": l.get("equipe_id") or self.equipe,
            "type": "incident", "statut": l.get("statut") or "en_cours",
            "categorie_charge": "non_planifiee",
            "estimation": ({"valeur": _nombre(l.get("estimation")), "unite": l.get("unite") or "heures",
                            "methode": "declaree"} if _nombre(l.get("estimation")) is not None else None),
            "maj_source": l.get("maj_source") or l.get("updated") or None,
        } for l in _lire(self.chemin) if l.get("external_id") or l.get("id")]
