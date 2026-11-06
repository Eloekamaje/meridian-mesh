"""Planificateur LLM : liste blanche, repli et arrêt."""
from __future__ import annotations

from meridian.adapters.outbound.llm.planificateur_liens import (
    DecisionPlanificateur,
    PlanificateurLLM,
)
from meridian.application.boucle_investigation import EtapeInvestigation
from meridian.domain.decouverte_liens import ResolutionCase


def _cas():
    return ResolutionCase(
        tenant_id="banque", twin_id="app-a", reference="${comptes.base-url}",
        environment="prod", missing_evidence="propriété absente")


def test_le_planificateur_accepte_une_decision_valide():
    planificateur = PlanificateurLLM(
        outils=("configuration", "deploiement"),
        decider=lambda cas, historique: {
            "outil": "configuration", "arguments": {"reference": "${comptes.base-url}"}})

    decision = planificateur.prochain(_cas(), ())

    assert decision["outil"] == "configuration"
    assert decision["arguments"] == {"reference": "${comptes.base-url}"}


def test_un_outil_hors_liste_blanche_declenche_le_repli():
    planificateur = PlanificateurLLM(
        outils=("configuration",),
        decider=lambda cas, historique: {"outil": "serveur", "arguments": {}})

    decision = planificateur.prochain(_cas(), ())

    assert decision["outil"] == "configuration"


def test_une_erreur_du_planificateur_declenche_le_repli():
    def panne(cas, historique):
        raise TimeoutError("modèle indisponible")

    planificateur = PlanificateurLLM(
        outils=("configuration", "deploiement"), decider=panne)

    decision = planificateur.prochain(_cas(), ())

    assert decision["outil"] == "configuration"


def test_un_candidat_deja_trouve_arrete_sans_appeler_le_modele():
    planificateur = PlanificateurLLM(
        outils=("configuration",),
        decider=lambda cas, historique: (_ for _ in ()).throw(AssertionError("appelé")))
    historique = (EtapeInvestigation(
        numero=1, outil="configuration", candidats=({"id": "c1"},)),)

    decision = planificateur.prochain(_cas(), historique)

    assert decision["stop"] is True
    assert decision["raison"] == "candidat trouvé"


def test_une_decision_d_arret_est_respectee():
    planificateur = PlanificateurLLM(
        outils=("configuration",),
        decider=lambda cas, historique: DecisionPlanificateur(
            stop=True, raison="plus de source utile"))

    decision = planificateur.prochain(_cas(), ())

    assert decision["stop"] is True
    assert decision["raison"] == "plus de source utile"


def test_sans_outil_la_boucle_s_arrete():
    planificateur = PlanificateurLLM(outils=())

    decision = planificateur.prochain(_cas(), ())

    assert decision["stop"] is True
    assert decision["raison"] == "aucun outil autorisé"
