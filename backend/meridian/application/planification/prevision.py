"""Moteur de prévision probabiliste, indépendant de tout outil de gestion.

Le calcul est déterministe pour une graine donnée : le LLM ne fait jamais l'arithmétique et ne décide
jamais d'une date. Sans historique suffisant, le moteur s'abstient explicitement.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean
from typing import Any

METHODE_VITESSE = "velocite_sprint"
METHODE_DEBIT = "debit_hebdomadaire"
METHODE_CYCLE = "cycle_time"
METHODE_ABSTENTION = "abstention"
VERSION = "1.0.0"


@dataclass(frozen=True)
class EntreePrevision:
    date_depart: date = field(default_factory=date.today)
    restant_items: int | None = None
    restant_points: float | None = None
    historique_debit: tuple[float, ...] = ()
    historique_velocite: tuple[float, ...] = ()
    duree_cycle_jours: float = 10.0
    historique_cycle: tuple[float, ...] = ()
    delai_fixe_jours: float = 0.0
    seed: int = 42
    simulations: int = 2000

    def __post_init__(self):
        if self.restant_items is not None and int(self.restant_items) < 0:
            raise ValueError("restant_items doit être positif ou nul")
        if self.restant_points is not None and float(self.restant_points) < 0:
            raise ValueError("restant_points doit être positif ou nul")
        object.__setattr__(self, "historique_debit", tuple(float(x) for x in self.historique_debit))
        object.__setattr__(self, "historique_velocite", tuple(float(x) for x in self.historique_velocite))
        object.__setattr__(self, "historique_cycle", tuple(float(x) for x in self.historique_cycle))
        object.__setattr__(self, "simulations", max(200, min(int(self.simulations), 20000)))


def _quantile(valeurs: list[float], q: float) -> float:
    if not valeurs:
        raise ValueError("quantile sans valeur")
    tri = sorted(valeurs)
    position = (len(tri) - 1) * q
    bas, haut = math.floor(position), math.ceil(position)
    if bas == haut:
        return tri[bas]
    return tri[bas] + (tri[haut] - tri[bas]) * (position - bas)


def _hash(entree: EntreePrevision) -> str:
    charge = {
        "restant_items": entree.restant_items, "restant_points": entree.restant_points,
        "debit": entree.historique_debit, "velocite": entree.historique_velocite,
        "cycle": entree.historique_cycle, "duree_cycle": entree.duree_cycle_jours,
        "delai": entree.delai_fixe_jours, "seed": entree.seed, "date": entree.date_depart.isoformat(),
    }
    return hashlib.sha256(json.dumps(charge, sort_keys=True, default=str).encode()).hexdigest()


def _resultat(entree: EntreePrevision, methode: str, jours: list[float],
              hypotheses: list[str], exclusions: list[str] | None = None) -> dict[str, Any]:
    total = [max(0.0, float(j)) for j in jours]
    p50, p85, p95 = (_quantile(total, q) for q in (0.5, 0.85, 0.95))
    base = 0.55 + min(0.35, len(entree.historique_debit or entree.historique_velocite
                                  or entree.historique_cycle) * 0.05)
    def date_de(jours_valeur: float) -> str:
        return (entree.date_depart + timedelta(days=math.ceil(jours_valeur))).isoformat()
    return {
        "ok": True, "methode": methode, "version": VERSION,
        "date_depart": entree.date_depart.isoformat(),
        "p50": date_de(p50), "p85": date_de(p85), "p95": date_de(p95),
        "jours": {"p50": round(p50, 2), "p85": round(p85, 2), "p95": round(p95, 2)},
        "confiance": round(min(0.9, base), 2),
        "hypotheses": hypotheses, "exclusions": exclusions or [],
        "entree_hash": _hash(entree), "seed": entree.seed,
        "simulations": entree.simulations,
    }


def _abstention(entree: EntreePrevision, raison: str) -> dict[str, Any]:
    return {"ok": False, "methode": METHODE_ABSTENTION, "version": VERSION,
            "raison": raison, "confiance": 0.0, "entree_hash": _hash(entree),
            "hypotheses": [], "exclusions": [raison]}


def prevoir(entree: EntreePrevision) -> dict[str, Any]:
    """Prévoit une date P50/P85/P95 à partir d'un historique, ou s'abstient."""
    if not isinstance(entree, EntreePrevision):
        raise TypeError("EntreePrevision attendue")
    rng = random.Random(entree.seed)
    delai = max(0.0, float(entree.delai_fixe_jours))
    if entree.restant_points is not None and entree.restant_points > 0:
        if len(entree.historique_velocite) < 2 or mean(entree.historique_velocite) <= 0:
            return _abstention(entree, "historique de vélocité insuffisant")
        jours = []
        for _ in range(entree.simulations):
            vitesse = max(0.1, rng.choice(entree.historique_velocite))
            iterations = math.ceil(entree.restant_points / vitesse)
            jours.append(delai + iterations * max(1.0, entree.duree_cycle_jours))
        return _resultat(entree, METHODE_VITESSE, jours, [
            f"vélocité moyenne {mean(entree.historique_velocite):.1f} points par cycle",
            f"durée de cycle {entree.duree_cycle_jours:g} jours",
        ])
    if entree.restant_items is not None and entree.restant_items > 0:
        if len(entree.historique_debit) >= 2 and mean(entree.historique_debit) > 0:
            jours = []
            for _ in range(entree.simulations):
                restant, semaines = entree.restant_items, 0
                while restant > 0 and semaines < 520:
                    debit = max(0.1, rng.choice(entree.historique_debit))
                    restant -= debit
                    semaines += 1
                jours.append(delai + semaines * 7)
            return _resultat(entree, METHODE_DEBIT, jours, [
                f"débit moyen {mean(entree.historique_debit):.1f} items par semaine",
                "capacité et dépendances supposées stables",
            ])
        if len(entree.historique_cycle) >= 2 and mean(entree.historique_cycle) > 0:
            jours = []
            for _ in range(entree.simulations):
                jours.append(delai + sum(rng.choice(entree.historique_cycle)
                                         for _ in range(entree.restant_items)))
            return _resultat(entree, METHODE_CYCLE, jours, [
                f"cycle time moyen {mean(entree.historique_cycle):.1f} jours",
                "hypothèse séquentielle conservatrice",
            ])
        return _abstention(entree, "historique de débit ou de cycle time insuffisant")
    return _abstention(entree, "périmètre restant absent")
