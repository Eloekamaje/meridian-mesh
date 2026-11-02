"""Scénarios de capacité, scope et délai : comparaison sans modifier les sources."""
from __future__ import annotations

from typing import Any

from meridian.application.planification import previsions


def _ajuster(base: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    entree = dict(base)
    scope = float(scenario.get("scope_delta_pct") or 0) / 100
    capacite = float(scenario.get("capacite_delta_pct") or 0) / 100
    if entree.get("restant_points") is not None:
        entree["restant_points"] = max(0.0, float(entree["restant_points"]) * (1 + scope))
    if entree.get("restant_items") is not None:
        entree["restant_items"] = max(0, int(round(float(entree["restant_items"]) * (1 + scope))))
    for cle in ("historique_velocite", "historique_debit"):
        if entree.get(cle):
            entree[cle] = [float(v) * (1 + capacite) for v in entree[cle]]
    entree["delai_fixe_jours"] = float(entree.get("delai_fixe_jours") or 0) + float(
        scenario.get("delai_supplementaire_jours") or 0)
    if scenario.get("seed") is not None:
        entree["seed"] = scenario["seed"]
    return entree


def comparer(base: dict[str, Any], scenarios: list[dict[str, Any]], *,
             date_depart=None) -> dict[str, Any]:
    resultats = []
    for scenario in scenarios:
        entree = _ajuster(base, scenario)
        resultat = previsions.prevoir_explicite(entree, date_depart=date_depart)
        resultats.append({"nom": scenario.get("nom") or "scénario", "resultat": resultat})
    reference = previsions.prevoir_explicite(base, date_depart=date_depart)
    return {"reference": reference, "scenarios": resultats}
