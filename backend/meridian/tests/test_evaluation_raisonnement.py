"""Évaluation déterministe du dossier de raisonnement."""
from meridian.application import evaluation_raisonnement as evaluation
from meridian.application import noyau_raisonnement as noyau


def test_un_dossier_n3_complet_passe():
    dossier = noyau.analyser_reponse(
        "Conçois une application",
        {"reponse": "OK", "hypotheses": ["h"],
         "options": [{"titre": "A", "risques": ["r"]}, {"titre": "B", "risques": ["r"]}],
         "validation": [{"hypothese": "h", "critere": "c"}]},
        contexte={"sans_questions": True},
    )
    resultat = evaluation.evaluer(dossier)
    assert resultat["niveau"] == "N3"
    assert "options" in resultat["scores"]


def test_un_dossier_sans_options_est_signale():
    dossier = noyau.analyser_reponse(
        "Conçois une application", {"reponse": "OK"}, contexte={"sans_questions": True})
    resultat = evaluation.evaluer(dossier)
    assert resultat["ok"] is False
    assert any("options" in constat for constat in resultat["constats"])


def test_un_dossier_direct_reste_simple():
    dossier = noyau.analyser_reponse("Qui es-tu ?", {"reponse": "Flore"})
    resultat = evaluation.evaluer(dossier)
    assert resultat["niveau"] == "N0"
    assert resultat["score"] >= 0.8
