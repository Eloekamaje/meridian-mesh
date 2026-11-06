"""Contrat de décision : le serveur refuse une décision invalide, jamais en silence."""
import pytest

from meridian.application.decision_tour import (
    AppelOutil, Clarification, DecisionInvalide, DecisionTour, valider,
)


def test_meta_ne_peut_pas_demander_une_clarification():
    with pytest.raises(DecisionInvalide):
        valider(DecisionTour(
            action="clarifier", acte="meta",
            clarification=Clarification("perimetre", "Quel périmètre ?", "changer le livrable"),
        ), slots_connus=("perimetre",))


def test_clarification_exige_slot_effet_et_une_seule_question():
    with pytest.raises(DecisionInvalide):
        valider(DecisionTour(action="clarifier", clarification=Clarification("x", "", "y")))
    with pytest.raises(DecisionInvalide):
        valider(DecisionTour(action="clarifier", clarification=Clarification("x", "q", "")))
    with pytest.raises(DecisionInvalide):
        valider(DecisionTour(action="clarifier", clarification=Clarification("x", "q", "e")),
                deja_une_question=True)


def test_outil_doit_etre_autorise_et_respecter_le_budget():
    decision = DecisionTour(action="outil", appels=(AppelOutil("lire_code", {"x": 1}),))
    assert valider(decision, outils_autorises={"lire_code"}, budget_outils=1) is decision
    with pytest.raises(DecisionInvalide):
        valider(decision, outils_autorises={"autre"})
    with pytest.raises(DecisionInvalide):
        valider(decision, budget_outils=0)


def test_repondre_ne_melange_pas_outils_et_conclusion():
    with pytest.raises(DecisionInvalide):
        valider(DecisionTour(action="repondre", appels=(AppelOutil("lire_code"),)))
