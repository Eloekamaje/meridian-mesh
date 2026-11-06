"""Calibration des croyances : résolution, révision et Brier."""
from meridian.application import calibration_croyances as calibration
from meridian.domain import dossier_raisonnement as dossier_domaine
from meridian.domain import epistemie


def _belief(statut="SUPPOSE", confiance=0.7):
    return epistemie.Belief(
        sujet="paiements", predicat="DEPLOYE_A", objet="France",
        statut=statut, confiance=confiance, preuves=("p-1",))


def test_un_outcome_positif_confirme_la_croyance():
    croyance, revision = calibration.resoudre(
        _belief(), outcome=True, motif="observé en production", acteur="demo", preuve="p-2")
    assert croyance.statut == "CONNU"
    assert croyance.confiance == 1.0
    assert revision.ancien_statut == "SUPPOSE"
    assert revision.preuves_ajoutees == ("p-2",)


def test_un_outcome_negatif_contredit_la_croyance():
    croyance, revision = calibration.resoudre(
        _belief(), outcome=False, motif="absent du registre", acteur="demo")
    assert croyance.statut == "CONTREDIT"
    assert croyance.confiance == 0.0
    assert revision.nouveau_statut == "CONTREDIT"


def test_le_brier_ne_porte_que_sur_les_predictions_resolues():
    assert calibration.brier([
        {"confidence": 0.9, "outcome": True},
        {"confidence": 0.2, "outcome": False},
        {"confidence": 0.5, "outcome": None},
    ]) == 0.025


def test_la_revision_est_ajoutee_au_dossier():
    dossier = dossier_domaine.DossierRaisonnement(
        question="paiements ?", beliefs=(_belief(),))
    resultat = calibration.resoudre_dans_dossier(
        dossier, dossier.beliefs[0].id, outcome=True, motif="test", acteur="demo")
    assert resultat.beliefs[0].statut == "CONNU"
    assert len(resultat.revisions) == 1
