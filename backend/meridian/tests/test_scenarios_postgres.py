"""Scénarios canoniques sur Postgres réel : liens inverses, liste et comparaison.

Ces tests sont ignorés sans ``JUMEAU_PG_DSN``. Ils vérifient l'adaptateur réel, notamment
le pluriel ``scenario_ids`` qui permet de comparer plusieurs scénarios d'une même décision.
"""
from __future__ import annotations

import pytest

from meridian.adapters.outbound.postgres import boucle, entreprise_depot
from meridian.application import commandes_boucle
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
