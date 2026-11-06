"""Résolution de destination et cas non résolus."""
import asyncio
import os

import pytest

from meridian.adapters.outbound.postgres import decouverte_liens as depot_liens
from meridian.adapters.outbound.postgres import relations_naissance as relations_liens
from meridian.application import decouverte_liens as resolution
from meridian.domain.decouverte_liens import (
    Binding,
    DestinationResolution,
    ResolutionCase,
)
from meridian.domain.naissance_relationnelle import Consommation, ManifesteNaissance


def _consommation(reference="${accounts.base-url}", kind="HTTP", environment="prod"):
    return Consommation(
        kind=kind, logical_ref=reference, environment=environment, portee="EXTERNAL",
        evidence_ids=("claim:1",))


def _bindings():
    return [
        Binding(kind="PROPERTY", nom="accounts.base-url",
                valeur="https://gateway.example/accounts", environment="prod",
                evidence_ids=("config:1",)),
        Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                environment="prod", evidence_ids=("gateway:1",)),
        Binding(kind="SERVICE", nom="comptes-api", valeur="comptes",
                environment="prod", evidence_ids=("catalogue:1",)),
    ]


def test_une_propriete_est_suivie_jusqu_au_twin():
    resultat = resolution.resoudre_destination(_consommation(), _bindings(), environment="prod")

    assert resultat.status == "resolved"
    assert resultat.target_twin_id == "comptes"
    assert resultat.target_service == "comptes-api"
    assert resultat.chain == ("property:accounts.base-url=https://gateway.example/accounts",
                              "gateway:/accounts->comptes-api", "twin:comptes")
    assert {"claim:1", "config:1", "gateway:1", "catalogue:1"} == set(resultat.evidence_ids)


def test_une_url_directe_est_resolue_par_la_route_la_plus_specifique():
    bindings = _bindings() + [
        Binding(kind="GATEWAY_ROUTE", nom="/accounts/admin", valeur="comptes-admin",
                environment="prod"),
        Binding(kind="SERVICE", nom="comptes-admin", valeur="comptes-admin-twin",
                environment="prod"),
    ]
    resultat = resolution.resoudre_destination(
        _consommation("https://gateway.example/accounts/admin/users", environment="prod"),
        bindings, environment="prod")
    assert resultat.status == "resolved"
    assert resultat.target_twin_id == "comptes-admin-twin"


def test_une_propriete_absente_ouvre_un_cas_avec_la_question_exacte():
    resultat = resolution.resoudre_destination(_consommation(), [], environment="prod")
    assert resultat.status == "missing_evidence"
    assert "accounts.base-url" in resultat.missing_evidence
    assert "manifeste" in resultat.next_check

    case = resolution.ouvrir_resolution_case("banque", "antifraude", _consommation(), resultat)
    assert case is not None
    assert case.reference == "${accounts.base-url}"
    assert case.status == "open"
    assert "accounts.base-url" in case.missing_evidence


def test_un_service_ambigu_ne_produit_pas_de_destination():
    bindings = _bindings() + [
        Binding(kind="SERVICE", nom="comptes-api", valeur="autre-twin", environment="prod"),
    ]
    resultat = resolution.resoudre_destination(_consommation("https://gateway.example/accounts/prod"),
                                               bindings, environment="prod")
    assert resultat.status == "ambiguous"
    assert len(resultat.candidates) == 2
    assert "ambiguïté" in resultat.next_check


def test_un_binding_jndi_est_suivi_jusqu_au_twin():
    bindings = [
        Binding(kind="JNDI", nom="jms/PaymentEvents", valeur="PAYMENT.EVENTS",
                environment="prod", evidence_ids=("websphere:1",)),
        Binding(kind="QUEUE", nom="PAYMENT.EVENTS", valeur="comptabilite",
                environment="prod", evidence_ids=("broker:1",)),
        Binding(kind="SERVICE", nom="comptabilite", valeur="comptabilite",
                environment="prod"),
    ]
    resultat = resolution.resoudre_destination(
        _consommation("jms/PaymentEvents", kind="JMS"), bindings, environment="prod")
    assert resultat.status == "resolved"
    assert resultat.target_twin_id == "comptabilite"
    assert "jndi:jms/PaymentEvents=PAYMENT.EVENTS" in resultat.chain


def test_l_environnement_filtre_les_bindings():
    resultat = resolution.resoudre_destination(_consommation(environment="dev"),
                                               _bindings(), environment="dev")
    assert resultat.status == "missing_evidence"


def test_un_cas_resolu_n_est_pas_ouvert():
    resolution_ok = DestinationResolution(status="resolved", target_twin_id="comptes")
    assert resolution.ouvrir_resolution_case(
        "banque", "antifraude", _consommation(), resolution_ok) is None


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_les_bindings_et_cas_sont_persistes(conn):
    for binding in _bindings():
        depot_liens.enregistrer_binding(conn, "banque", binding)
    lus = depot_liens.lire_bindings(conn, "banque", environment="prod")
    assert {b.kind for b in lus} == {"PROPERTY", "GATEWAY_ROUTE", "SERVICE"}

    resultat = resolution.resoudre_destination(_consommation(), lus, environment="prod")
    assert resultat.status == "resolved"
    case = resolution.ouvrir_resolution_case(
        "banque", "antifraude", _consommation(), DestinationResolution(
            status="missing_evidence", missing_evidence="binding absent",
            next_check="export WebSphere"))
    assert case is not None
    depot_liens.enregistrer_resolution_case(conn, case)
    cas = depot_liens.lister_resolution_cases(conn, "banque", twin_id="antifraude")
    assert len(cas) == 1 and cas[0]["status"] == "open"

    resolue = depot_liens.resoudre_case(conn, "banque", case.id, evidence_ids=["export:1"])
    assert resolue["status"] == "resolved" and "export:1" in resolue["evidence_ids"]


class FauxInvestigateur:
    def __init__(self, reponse):
        self.reponse = reponse
        self.demandes = []

    async def proposer(self, demande):
        self.demandes.append(demande)
        return self.reponse


def _cas():
    return ResolutionCase(
        tenant_id="banque", twin_id="antifraude", reference="${accounts.base-url}",
        environment="prod", missing_evidence="propriété absente",
        next_check="manifeste de déploiement", owner="Équipe plateforme")


def _manifestes():
    return [ManifesteNaissance(
        tenant_id="banque", twin_id="comptes", birth_run_id="cmd-comptes",
        application_id="comptes", status="CONFIRMED", owner="Équipe comptes")]


def _reponse_investigation():
    return {
        "candidates": [{
            "twin_id": "comptes", "service": "comptes-api", "confidence": 0.82,
            "reason": "la propriété pointe vers la passerelle et la route correspond au service comptes-api",
            "evidence_ids": ["doc:1"],
            "bindings": [
                Binding(kind="PROPERTY", nom="accounts.base-url",
                        valeur="https://gateway.example/accounts", environment="prod",
                        evidence_ids=("doc:1",)).as_dict(),
                Binding(kind="GATEWAY_ROUTE", nom="/accounts", valeur="comptes-api",
                        environment="prod", evidence_ids=("doc:1",)).as_dict(),
                Binding(kind="SERVICE", nom="comptes-api", valeur="comptes",
                        environment="prod", evidence_ids=("doc:1",)).as_dict(),
            ],
        }],
        "next_check": "",
    }


def test_l_investigateur_ajoute_des_candidats_au_cas():
    investigateur = FauxInvestigateur(_reponse_investigation())
    case = asyncio.run(resolution.investiguer_resolution_async(
        _cas(), [], _manifestes(), investigateur))

    assert case.attempts == 1
    assert len(case.candidates) == 1
    assert case.candidates[0]["twin_id"] == "comptes"
    assert investigateur.demandes[0]["case"]["reference"] == "${accounts.base-url}"


def test_un_candidat_hors_contexte_est_ignore():
    reponse = _reponse_investigation()
    reponse["candidates"][0]["twin_id"] = "inconnu"
    case = asyncio.run(resolution.investiguer_resolution_async(
        _cas(), [], _manifestes(), FauxInvestigateur(reponse)))
    assert case.candidates == ()


def test_accepter_un_candidat_cree_les_bindings_et_resout():
    case = asyncio.run(resolution.investiguer_resolution_async(
        _cas(), [], _manifestes(), FauxInvestigateur(_reponse_investigation())))
    candidate_id = case.candidates[0]["id"]

    tranchee, bindings = resolution.revoir_candidat(
        case, candidate_id, "accepter", "Équipe plateforme")

    assert tranchee.status == "resolved"
    assert tranchee.target_twin_id == "comptes"
    assert tranchee.candidates[0]["status"] == "accepted"
    assert len(bindings) == 3
    resolue = resolution.resoudre_destination(_consommation(), bindings, environment="prod")
    assert resolue.status == "resolved" and resolue.target_twin_id == "comptes"


def test_rejeter_un_candidat_laisse_le_cas_ouvert():
    case = asyncio.run(resolution.investiguer_resolution_async(
        _cas(), [], _manifestes(), FauxInvestigateur(_reponse_investigation())))
    candidate_id = case.candidates[0]["id"]

    tranchee, bindings = resolution.revoir_candidat(
        case, candidate_id, "rejeter", "Équipe plateforme", motif="route interne")

    assert tranchee.status == "open"
    assert tranchee.candidates[0]["status"] == "rejected"
    assert bindings == []


@pytest.mark.skipif(not os.environ.get("JUMEAU_PG_DSN"), reason="JUMEAU_PG_DSN non défini")
def test_investigation_et_revue_persistent_les_bindings(conn):
    relations_liens.enregistrer_manifeste(conn, ManifesteNaissance(
        tenant_id="banque", twin_id="antifraude", birth_run_id="cmd-antifraude",
        application_id="antifraude", status="CONFIRMED", owner="Équipe antifraude"))
    relations_liens.enregistrer_manifeste(conn, _manifestes()[0])
    case = _cas()
    depot_liens.enregistrer_resolution_case(conn, case)

    investigation = asyncio.run(depot_liens.investiguer_case(
        conn, "banque", case.id, FauxInvestigateur(_reponse_investigation())))
    assert len(investigation["candidates"]) == 1
    candidate_id = investigation["candidates"][0]["id"]

    tranchee = depot_liens.revoir_case(
        conn, "banque", case.id, candidate_id, "accepter", "Équipe plateforme")
    assert tranchee["status"] == "resolved"
    assert tranchee["target_twin_id"] == "comptes"

    bindings = depot_liens.lire_bindings(conn, "banque", environment="prod")
    resolue = resolution.resoudre_destination(_consommation(), bindings, environment="prod")
    assert resolue.status == "resolved" and resolue.target_twin_id == "comptes"
    propositions = relations_liens.lister_propositions(conn, "banque")
    assert len(propositions) == 1
    assert propositions[0]["state"] == "supposee"
    assert propositions[0]["mode"] == "INFERRED"
    assert propositions[0]["consumer_id"] == "antifraude"
    assert propositions[0]["provider_id"] == "comptes"


def test_un_binding_avec_secret_est_refuse():
    with pytest.raises(ValueError):
        Binding(kind="PROPERTY", nom="accounts.base-url",
                valeur="https://user:pw@example.test/accounts")
