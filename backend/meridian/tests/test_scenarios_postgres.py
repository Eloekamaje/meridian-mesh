"""Scénarios canoniques sur Postgres réel : liens inverses, liste et comparaison.

Ces tests sont ignorés sans ``JUMEAU_PG_DSN``. Ils vérifient l'adaptateur réel, notamment
le pluriel ``scenario_ids`` qui permet de comparer plusieurs scénarios d'une même décision.
"""
from __future__ import annotations

from dataclasses import asdict

import copy

import pytest

from meridian.adapters.outbound.postgres import boucle, entreprise_depot
from meridian.adapters.outbound.postgres import objets_exploitation as depot
from meridian.application import commandes_boucle
from meridian.domain import objets_exploitation as exploitation
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
DATES = {
    "cree_le": "2026-10-01T08:00:00+00:00",
    "observe_le": "2026-10-02T09:00:00+00:00",
    "valide_depuis": "2026-10-02T09:00:00+00:00",
}


def _semis(conn):
    situation = boucle.Situation(
        **DATES, id="sit-1", tenant_id=TENANT,
        titre="Délai en hausse", description="Le délai dépasse la cible",
    )
    investigation = boucle.Investigation(
        **DATES, id="inv-1", tenant_id=TENANT, titre="Comprendre",
        question="Pourquoi ?", situation_id=situation.id,
    )
    decision = boucle.Decision(
        **DATES, id="dec-1", tenant_id=TENANT, titre="Choisir",
        investigation_id=investigation.id, statut="DECIDED", acteur="comité",
        choix="Automatiser", decide_le=DATES["observe_le"],
    )
    entreprise_depot.enregistrer_objet(conn, TENANT, situation)
    entreprise_depot.enregistrer_objet(conn, TENANT, investigation)
    entreprise_depot.enregistrer_objet(conn, TENANT, decision)
    return investigation, decision


def _seconde_investigation(conn):
    situation = boucle.Situation(
        **DATES, id="sit-2", tenant_id=TENANT,
        titre="Autre situation", description="Autre",
    )
    investigation = boucle.Investigation(
        **DATES, id="inv-2", tenant_id=TENANT, titre="Autre investigation",
        question="Pourquoi ?", situation_id=situation.id,
    )
    decision = boucle.Decision(
        **DATES, id="dec-2", tenant_id=TENANT, titre="Autre décision",
        investigation_id=investigation.id, statut="DECIDED", acteur="comité",
        choix="Réorganiser", decide_le=DATES["observe_le"],
    )
    entreprise_depot.enregistrer_objet(conn, TENANT, situation)
    entreprise_depot.enregistrer_objet(conn, TENANT, investigation)
    entreprise_depot.enregistrer_objet(conn, TENANT, decision)
    return investigation, decision


@besoin_pg
def test_plusieurs_scenarios_sur_une_decision_et_liste_filtree(conn):
    investigation, decision = _semis(conn)

    premier = commandes_boucle.creer_scenario(
        boucle, conn, TENANT, titre="Automatiser", decision_id=decision.id,
        valeur_estimee=100, cout_estime=50, delai_jours=10, risque=0.2,
    )
    second = commandes_boucle.creer_scenario(
        boucle, conn, TENANT, titre="Réorganiser", investigation_id=investigation.id,
        decision_id=decision.id, valeur_estimee=120, delai_jours=8, risque=0.3,
        reversibilite="PARTIELLE",
    )

    decision_lue = entreprise_depot.lire_objet(conn, TENANT, decision.id)
    investigation_lue = entreprise_depot.lire_objet(conn, TENANT, investigation.id)
    assert sorted(decision_lue["donnees"]["scenario_ids"]) == sorted([
        premier.objet["id"], second.objet["id"],
    ])
    assert decision_lue["donnees"]["scenario_id"] == premier.objet["id"]
    assert investigation_lue["donnees"]["scenario_ids"] == [second.objet["id"]]

    liste = commandes_boucle.lister_scenarios(
        boucle, conn, TENANT, decision_id=decision.id)
    assert sorted(scenario["id"] for scenario in liste) == sorted([
        premier.objet["id"], second.objet["id"],
    ])
    comparaison = commandes_boucle.comparer_scenarios(
        boucle, conn, TENANT,
        [premier.objet["id"], second.objet["id"]],
        reference_id=premier.objet["id"],
    )
    assert comparaison["reference"]["id"] == premier.objet["id"]
    assert comparaison["scenarios"][1]["ecarts"]["valeur_estimee"]["delta"] == 20.0


@besoin_pg
def test_une_decision_hors_investigation_est_refusee_sans_ecriture(conn):
    investigation, _ = _semis(conn)
    _seconde_investigation(conn)
    avant_investigation = copy.deepcopy(
        entreprise_depot.lire_objet(conn, TENANT, investigation.id))
    avant_decision = copy.deepcopy(
        entreprise_depot.lire_objet(conn, TENANT, "dec-2"))

    with pytest.raises(commandes_boucle.TransitionRefusee):
        commandes_boucle.creer_scenario(
            boucle, conn, TENANT, titre="Incohérent",
            investigation_id=investigation.id, decision_id="dec-2")

    assert commandes_boucle.lister_scenarios(
        boucle, conn, TENANT, investigation_id=investigation.id) == []
    assert entreprise_depot.lire_objet(conn, TENANT, investigation.id) == avant_investigation
    assert entreprise_depot.lire_objet(conn, TENANT, "dec-2") == avant_decision


@besoin_pg
def test_une_panne_sur_le_second_parent_annule_tout_le_scenario(conn, monkeypatch):
    investigation, decision = _semis(conn)
    avant_investigation = copy.deepcopy(
        entreprise_depot.lire_objet(conn, TENANT, investigation.id))
    avant_decision = copy.deepcopy(
        entreprise_depot.lire_objet(conn, TENANT, decision.id))
    originale = depot._persister_parent
    appels = []

    def echouer_sur_le_second(conn_, tenant, parent, operations):
        appels.append(parent["id"])
        if len(appels) == 2:
            raise RuntimeError("panne simulée sur le second parent")
        return originale(conn_, tenant, parent, operations)

    monkeypatch.setattr(depot, "_persister_parent", echouer_sur_le_second)

    with pytest.raises(RuntimeError):
        commandes_boucle.creer_scenario(
            boucle, conn, TENANT, titre="Atomique",
            investigation_id=investigation.id, decision_id=decision.id)

    assert commandes_boucle.lister_scenarios(
        boucle, conn, TENANT, investigation_id=investigation.id) == []
    assert entreprise_depot.lire_objet(conn, TENANT, investigation.id) == avant_investigation
    assert entreprise_depot.lire_objet(conn, TENANT, decision.id) == avant_decision


@besoin_pg
def test_la_chaine_lue_d_un_scenario_est_complete(conn):
    investigation, decision = _semis(conn)
    scenario = commandes_boucle.creer_scenario(
        boucle, conn, TENANT, titre="Chaîne",
        investigation_id=investigation.id, decision_id=decision.id)

    assert [element["type"] for element in scenario.chaine] == [
        "SITUATION", "INVESTIGATION", "DECISION", "SCENARIO",
    ]
    lu = boucle.lire_boucle(
        conn, TENANT, scenario.objet["id"], historique=True, as_dict=True)
    assert [element["type"] for element in lu["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "SCENARIO",
    ]
    objet = boucle.lire_boucle(conn, TENANT, scenario.objet["id"], as_dict=False)
    assert objet.type == "SCENARIO"
    assert objet.decision_id == decision.id
    assert boucle.donnees_de(objet)["investigation_id"] == investigation.id


@besoin_pg
def test_enregistrer_boucle_persiste_et_relit_un_scenario(conn):
    investigation, decision = _semis(conn)
    scenario = exploitation.nouveau_scenario(
        investigation=investigation, decision=decision, titre="Canonique")
    parents = []
    for parent in (investigation, decision):
        charge = asdict(parent)
        charge.pop("version", None)
        parents.append(charge)

    boucle.enregistrer_boucle(
        conn, TENANT, [*parents, scenario], historique=True)

    relu = boucle.lire_boucle(conn, TENANT, scenario.id, as_dict=False)
    assert relu.type == "SCENARIO"
    assert boucle.donnees_de(relu)["decision_id"] == decision.id
    decision_lue = entreprise_depot.lire_objet(conn, TENANT, decision.id)
    assert decision_lue["donnees"]["scenario_ids"] == [scenario.id]
    assert decision_lue["donnees"]["scenario_id"] == scenario.id


@besoin_pg
def test_retirer_le_premier_scenario_promeut_le_suivant(conn):
    investigation, decision = _semis(conn)
    _, decision_2 = _seconde_investigation(conn)
    premier = commandes_boucle.creer_scenario(
        boucle, conn, TENANT, titre="Premier", decision_id=decision.id)
    second = commandes_boucle.creer_scenario(
        boucle, conn, TENANT, titre="Second", decision_id=decision.id)

    objet = depot.lire_objet_exploitation(
        conn, TENANT, premier.objet["id"], as_dict=False)
    objet.decision_id = decision_2.id
    depot.enregistrer_objets_exploitation(conn, TENANT, objet)

    ancienne = entreprise_depot.lire_objet(conn, TENANT, decision.id)
    nouvelle = entreprise_depot.lire_objet(conn, TENANT, decision_2.id)
    assert ancienne["donnees"]["scenario_ids"] == [second.objet["id"]]
    assert ancienne["donnees"]["scenario_id"] == second.objet["id"]
    assert nouvelle["donnees"]["scenario_ids"] == [premier.objet["id"]]
    assert nouvelle["donnees"]["scenario_id"] == premier.objet["id"]


@besoin_pg
def test_un_scenario_hors_tenant_est_refuse(conn):
    _semis(conn)
    autre = boucle.Investigation(
        **DATES, id="inv-autre", tenant_id="assurance", titre="Autre",
        question="Pourquoi ?", situation_id="sit-autre",
    )
    entreprise_depot.enregistrer_objet(conn, "assurance", autre)
    with pytest.raises(commandes_boucle.SourceIntrouvable):
        commandes_boucle.creer_scenario(
            boucle, conn, TENANT, titre="Hors tenant", investigation_id=autre.id)
