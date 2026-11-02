"""Prévision probabiliste déterministe et abstention."""
from datetime import date

from meridian.application.planification import prevision


def test_previson_par_velocite_donne_trois_quantiles_ordonnes():
    entree = prevision.EntreePrevision(
        date_depart=date(2026, 1, 1), restant_points=30,
        historique_velocite=(8, 10, 12, 9), duree_cycle_jours=14, seed=7, simulations=500)
    resultat = prevision.prevoir(entree)
    assert resultat["ok"] is True
    assert resultat["methode"] == prevision.METHODE_VITESSE
    assert resultat["p50"] <= resultat["p85"] <= resultat["p95"]
    assert resultat["entree_hash"] and resultat["seed"] == 7


def test_previson_par_debit_quand_les_points_manquent():
    entree = prevision.EntreePrevision(
        date_depart=date(2026, 1, 1), restant_items=20,
        historique_debit=(4, 5, 3, 6), seed=1, simulations=500)
    resultat = prevision.prevoir(entree)
    assert resultat["methode"] == prevision.METHODE_DEBIT
    assert resultat["p50"] <= resultat["p95"]


def test_sans_historique_le_moteur_s_abstient():
    resultat = prevision.prevoir(prevision.EntreePrevision(restant_items=10))
    assert resultat["ok"] is False
    assert resultat["methode"] == prevision.METHODE_ABSTENTION
    assert "historique" in resultat["raison"]


def test_meme_graine_meme_resultat():
    entree = prevision.EntreePrevision(restant_points=20, historique_velocite=(5, 7, 6),
                                       duree_cycle_jours=10, seed=99, simulations=300)
    assert prevision.prevoir(entree)["p85"] == prevision.prevoir(entree)["p85"]
