"""Boucle d'enquête : budget, outils, arrêt et candidats."""
from __future__ import annotations

import pytest

from meridian.application.boucle_investigation import (
    BudgetEnquete,
    PlanificateurRegles,
    executer,
)
from meridian.domain.decouverte_liens import ResolutionCase


class FauxOutil:
    def __init__(self, nom, reponses):
        self.nom = nom
        self.reponses = list(reponses)
        self.appels = []

    def appeler(self, arguments):
        self.appels.append(dict(arguments))
        if not self.reponses:
            return {"resume": "vide", "candidats": [], "evidence_ids": []}
        return self.reponses.pop(0)


class FauxPlanificateur:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.appels = []

    def prochain(self, cas, historique):
        self.appels.append((cas, historique))
        if not self.decisions:
            return {"stop": True, "raison": "fini"}
        return self.decisions.pop(0)


def _cas(reference="${comptes.base-url}", missing="propriété absente"):
    return ResolutionCase(
        tenant_id="banque", twin_id="antifraude", reference=reference,
        environment="prod", missing_evidence=missing,
        next_check="consulter le déploiement")


def _candidat(twin_id="comptes"):
    return {
        "twin_id": twin_id, "service": "comptes-api", "confidence": 0.8,
        "reason": "configuration et route concordent",
        "evidence_ids": ["config:1"],
    }


def test_la_boucle_produit_un_candidat_et_s_arrete():
    outil = FauxOutil("configuration", [{
        "resume": "propriété trouvée",
        "evidence_ids": ["config:1"],
        "candidats": [_candidat()],
    }])
    planificateur = FauxPlanificateur([
        {"outil": "configuration", "arguments": {"reference": "${comptes.base-url}"}},
        {"stop": True, "raison": "candidat trouvé"},
    ])

    resultat = executer(_cas(), planificateur, {"configuration": outil})

    assert resultat.arret == "candidat trouvé"
    assert len(resultat.etapes) == 1
    assert resultat.etapes[0].outil == "configuration"
    assert resultat.candidats[0]["twin_id"] == "comptes"
    assert resultat.evidence_ids == ("config:1",)
    assert outil.appels == [{"reference": "${comptes.base-url}"}]
    assert resultat.budget_atteint is False


def test_le_budget_etapes_arrete_la_boucle():
    reponse = {"resume": "rien", "candidats": [], "evidence_ids": []}
    outils = {nom: FauxOutil(nom, [reponse]) for nom in ("code", "contrats", "configuration")}
    planificateur = FauxPlanificateur([
        {"outil": "code", "arguments": {}},
        {"outil": "contrats", "arguments": {}},
        {"outil": "configuration", "arguments": {}},
    ])

    resultat = executer(_cas(), planificateur, outils,
                        budget=BudgetEnquete(max_etapes=2))

    assert len(resultat.etapes) == 2
    assert resultat.arret == "budget_etapes"
    assert resultat.budget_atteint is True


def test_un_outil_inconnu_arrete_sans_appel():
    planificateur = FauxPlanificateur([{"outil": "inconnu", "arguments": {}}])

    resultat = executer(_cas(), planificateur, {})

    assert resultat.arret == "outil_inconnu"
    assert resultat.etapes == ()
    assert resultat.erreurs == ("outil inconnu : inconnu",)


def test_un_outil_ne_peut_pas_etre_rejoue():
    outil = FauxOutil("code", [{"resume": "ok", "candidats": [], "evidence_ids": []}])
    planificateur = FauxPlanificateur([
        {"outil": "code", "arguments": {}},
        {"outil": "code", "arguments": {}},
    ])

    resultat = executer(_cas(), planificateur, {"code": outil})

    assert resultat.arret == "outil_deja_utilise"
    assert len(resultat.etapes) == 1


def test_une_erreur_d_outil_est_conservee_sans_casser_la_boucle():
    class OutilEnPanne:
        def appeler(self, arguments):
            raise TimeoutError("source indisponible")

    planificateur = FauxPlanificateur([{"outil": "code", "arguments": {}}])

    resultat = executer(_cas(), planificateur, {"code": OutilEnPanne()})

    assert resultat.arret == "erreur_outil"
    assert resultat.etapes[0].statut == "erreur"
    assert "TimeoutError" in resultat.etapes[0].resume
    assert resultat.erreurs == ("code : TimeoutError",)


def test_le_planificateur_de_regles_choisit_la_source_selon_le_manque():
    planificateur = PlanificateurRegles()

    propriete = planificateur.prochain(_cas(missing="propriété absente"), ())
    service = planificateur.prochain(_cas(missing="service non rattaché"), ())
    trace = planificateur.prochain(_cas(missing="usage runtime non observé"), ())
    epuise = planificateur.prochain(_cas(), tuple(
        type("Etape", (), {"outil": outil})() for outil in
        ("configuration", "deploiement", "gateway", "contrats", "code",
         "messagerie", "traces", "runtime", "annuaire", "portail")))

    assert propriete["outil"] == "configuration"
    assert service["outil"] == "deploiement"
    assert trace["outil"] == "traces"
    assert epuise["stop"] is True


def test_un_candidat_invalide_est_ignore_et_trace():
    outil = FauxOutil("configuration", [{
        "resume": "bruit",
        "evidence_ids": ["config:1"],
        "candidats": [{"service": "sans-twin"}],
    }])
    planificateur = FauxPlanificateur([
        {"outil": "configuration", "arguments": {}},
        {"stop": True, "raison": "fini"},
    ])

    resultat = executer(_cas(), planificateur, {"configuration": outil})

    assert resultat.candidats == ()
    assert resultat.erreurs
    assert "candidat invalide" in resultat.erreurs[0]
