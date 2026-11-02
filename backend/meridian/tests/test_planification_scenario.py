"""Scénarios sans effet de bord."""
from datetime import date

from meridian.application.planification import scenario


def test_un_ajout_de_capacite_ameliore_la_date_ou_reste_identique():
    base = {"restant_points": 30, "historique_velocite": [5, 6, 7],
            "duree_cycle_jours": 14, "seed": 4, "simulations": 300}
    resultat = scenario.comparer(base, [
        {"nom": "capacité +20 %", "capacite_delta_pct": 20},
        {"nom": "scope +50 %", "scope_delta_pct": 50},
    ], date_depart=date(2026, 1, 1))
    reference = resultat["reference"]
    capacite = resultat["scenarios"][0]["resultat"]
    scope = resultat["scenarios"][1]["resultat"]
    assert reference["ok"] and capacite["ok"] and scope["ok"]
    assert capacite["jours"]["p50"] <= reference["jours"]["p50"]
    assert scope["jours"]["p50"] >= reference["jours"]["p50"]
