"""Boucle P1 canonique : liens, transitions, mesures, tenants et persistance Postgres."""
import json

import pytest

from jumeau import boucle
from jumeau.modele_entreprise import ModeleInvalide
from jumeau.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
DATES = {
    "cree_le": "2026-10-01T08:00:00+00:00",
    "observe_le": "2026-10-02T09:00:00+00:00",
    "valide_depuis": "2026-10-02T09:00:00+00:00",
}


def situation(identifiant="sit-1", tenant=TENANT, titre="Délai de traitement en hausse", **champs):
    valeurs = {**DATES, "id": identifiant, "tenant_id": tenant, "titre": titre,
               "resume": "Le délai dépasse la cible", "twin_ids": ["twin-process"]}
    valeurs.update(champs)
    return boucle.Situation(**valeurs)


def chaine(prefixe="cb", tenant=TENANT):
    sit = situation(f"sit-{prefixe}", tenant=tenant)
    investigation = boucle.ouvrir_investigation(
        sit, id=f"inv-{prefixe}", titre="Comprendre le délai", question="Pourquoi 12 jours ?")
    proposition = boucle.proposer_decision(
        investigation, ["Automatiser", "Réorganiser"], ["coût", "délai"], ["qualité des données"],
        id=f"dec-{prefixe}")
    decision = boucle.trancher_decision(proposition, "comité-cartes", "Automatiser",
                                        rationale="Réduire le délai sans ajouter d'effectif")
    initiative = boucle.lancer_initiative(
        decision, id=f"ini-{prefixe}", titre="Automatiser la pièce", outcome_attendu_ids=["out-attendu"])
    outcome = boucle.mesurer_outcome(
        initiative, {"metrique": "delai_moyen_jours", "valeur": 4.2, "source": "suivi-cartes"},
        id=f"out-{prefixe}", valeur_attendue=5, interpretation="Le délai baisse")
    learning = boucle.capitaliser_learning(
        outcome, id=f"lea-{prefixe}", enonce="Automatiser la pièce réduit le délai de traitement",
        scope="cartes", conditions_applicabilite=["volume stable"])
    return sit, investigation, proposition, decision, initiative, outcome, learning


def test_chaine_complete_et_interdiction_des_raccourcis():
    sit, investigation, proposition, decision, initiative, outcome, learning = chaine()

    assert (investigation.type, investigation.situation_id) == ("INVESTIGATION", sit.id)
    assert (proposition.type, proposition.investigation_id, proposition.statut) == (
        "DECISION", investigation.id, "PROPOSED")
    assert (decision.statut, decision.acteur, decision.choix) == ("DECIDED", "comité-cartes", "Automatiser")
    assert proposition.statut == "PROPOSED" and decision is not proposition
    assert (initiative.decision_id, initiative.statut) == (decision.id, "PLANNED")
    assert (outcome.initiative_id, outcome.mesure["valeur"], outcome.statut) == (
        initiative.id, 4.2, "OBSERVED")
    assert learning.outcome_ids == [outcome.id] and learning.investigation_ids == []

    learning_investigation = boucle.capitaliser_learning(
        investigation, id="lea-inv", enonce="L'enquête elle-même est réutilisable")
    assert learning_investigation.outcome_ids == []
    assert learning_investigation.investigation_ids == [investigation.id]

    assert investigation.famille == "investigation"
    assert decision.famille == "decision" and initiative.famille == "decision"
    assert outcome.famille == learning.famille == "resultat_apprentissage"

    with pytest.raises(boucle.BoucleInvalide):
        boucle.trancher_decision(decision, "autre-comité", "Automatiser")


@besoin_pg
def test_tenant_mismatch_refuse_a_chaque_etape(conn):
    sit = situation()
    autre = situation("sit-autre", tenant=AUTRE_TENANT)

    with pytest.raises(boucle.BoucleInvalide):
        boucle.ouvrir_investigation(sit, tenant_id=AUTRE_TENANT)

    investigation = boucle.ouvrir_investigation(sit, id="inv-1")
    with pytest.raises(boucle.BoucleInvalide):
        boucle.proposer_decision(investigation, ["A"], ["coût"], tenant_id=AUTRE_TENANT)

    proposition = boucle.proposer_decision(investigation, ["A"], ["coût"], id="dec-1")
    with pytest.raises(boucle.BoucleInvalide):
        boucle.trancher_decision(proposition, "acteur", "A", tenant_id=AUTRE_TENANT)

    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, AUTRE_TENANT, sit)
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, [sit, autre])
    assert boucle.lire_boucle(conn, TENANT, sit.id) is None


@besoin_pg
def test_decision_non_tranchee_refuse_initiative(conn):
    sit = situation()
    investigation = boucle.ouvrir_investigation(sit, id="inv-1")
    proposition = boucle.proposer_decision(investigation, ["A", "B"], ["coût"], id="dec-1")

    with pytest.raises(boucle.BoucleInvalide):
        boucle.lancer_initiative(proposition, id="ini-refusee")

    boucle.enregistrer_boucle(conn, TENANT, [sit, investigation, proposition])
    initiative = boucle.Initiative(
        id="ini-persistee", tenant_id=TENANT, decision_id=proposition.id,
        titre="Initiative prématurée", **DATES)
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, initiative)
    assert boucle.lire_boucle(conn, TENANT, initiative.id) is None


@besoin_pg
def test_outcome_sans_mesure_ou_sans_initiative_refuse(conn):
    with pytest.raises(ModeleInvalide):
        boucle.Outcome(id="out-sans-mesure", tenant_id=TENANT, titre="Sans mesure", **DATES)

    with pytest.raises(ModeleInvalide):
        boucle.Outcome(id="out-sans-lien", tenant_id=TENANT, titre="Sans initiative",
                       mesure={"valeur": 1}, **DATES)

    sit, investigation, _, decision, initiative, _, _ = chaine()
    with pytest.raises(boucle.BoucleInvalide):
        boucle.mesurer_outcome(initiative, {})
    with pytest.raises(boucle.BoucleInvalide):
        boucle.mesurer_outcome(initiative, None)

    boucle.enregistrer_boucle(conn, TENANT, [sit, investigation, decision, initiative])
    # Les liens restent obligatoires même via un dictionnaire non typé.
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, {
            "id": "out-dict", "type": "OUTCOME", "tenant_id": TENANT,
            "titre": "Outcome sans mesure", "donnees": {"initiative_id": initiative.id},
        })
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, {
            "id": "out-dict-2", "type": "OUTCOME", "tenant_id": TENANT,
            "titre": "Outcome sans initiative", "donnees": {"mesure": {"valeur": 2}},
        })


@besoin_pg
def test_learning_sans_source_refuse(conn):
    with pytest.raises(ModeleInvalide):
        boucle.Learning(id="lea-sans-source", tenant_id=TENANT, enonce="Une leçon", **DATES)

    with pytest.raises(boucle.BoucleInvalide):
        boucle.capitaliser_learning(None, enonce="Une leçon")

    _, _, _, _, initiative, _, _ = chaine()
    with pytest.raises(boucle.BoucleInvalide):
        boucle.capitaliser_learning(initiative, enonce="Une leçon")

    outcome_vide = {"id": "out-vide", "type": "OUTCOME", "tenant_id": TENANT, "donnees": {}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.capitaliser_learning(outcome_vide, enonce="Une leçon")

    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, {
            "id": "lea-dict", "type": "LEARNING", "tenant_id": TENANT,
            "titre": "Learning sans source", "donnees": {"enonce": "Une leçon"},
        })


@besoin_pg
def test_persistance_relecture_des_objets_et_liens(conn):
    sit, investigation, proposition, decision, initiative, outcome, learning = chaine()
    stockes = boucle.enregistrer_boucle(
        conn, TENANT, [learning, outcome, initiative, decision, investigation, sit])

    assert [objet["type"] for objet in stockes] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]

    lu_inv = boucle.lire_boucle(conn, TENANT, investigation.id)
    lu_dec = boucle.lire_boucle(conn, TENANT, decision.id)
    lu_ini = boucle.lire_boucle(conn, TENANT, initiative.id)
    lu_out = boucle.lire_boucle(conn, TENANT, outcome.id)
    lu_lea = boucle.lire_boucle(conn, TENANT, learning.id)

    assert lu_inv["donnees"]["situation_id"] == sit.id
    assert lu_dec["donnees"]["investigation_id"] == investigation.id
    assert lu_dec["donnees"]["statut"] == "DECIDED"
    assert lu_dec["donnees"]["initiative_id"] == initiative.id
    assert lu_ini["donnees"]["decision_id"] == decision.id
    assert lu_ini["donnees"]["outcome_ids"] == [outcome.id]
    assert lu_out["donnees"]["initiative_id"] == initiative.id
    assert lu_out["donnees"]["mesure"]["valeur"] == 4.2
    assert lu_lea["donnees"]["outcome_ids"] == [outcome.id]
    assert proposition.statut == "PROPOSED"

    canonique = boucle.lire_boucle(conn, TENANT, outcome.id, as_dict=False)
    assert isinstance(canonique, boucle.Outcome)
    assert canonique.liens == {"initiative_id": initiative.id}
    assert canonique.mesure["metrique"] == "delai_moyen_jours"

    parcours = boucle.lire_boucle(conn, TENANT, learning.id, historique=True)
    assert [objet["type"] for objet in parcours["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]
    assert parcours["historique"] == []
    assert boucle.lire_boucle(conn, TENANT, "absent") is None


@besoin_pg
def test_deux_tenants_isoles(conn):
    sit_a, inv_a, _, dec_a, ini_a, out_a, lea_a = chaine("a", tenant=TENANT)
    sit_b, inv_b, _, dec_b, ini_b, out_b, lea_b = chaine("b", tenant=AUTRE_TENANT)
    boucle.enregistrer_boucle(conn, TENANT, [sit_a, inv_a, dec_a, ini_a, out_a, lea_a])
    boucle.enregistrer_boucle(conn, AUTRE_TENANT, [sit_b, inv_b, dec_b, ini_b, out_b, lea_b])

    assert boucle.lire_boucle(conn, TENANT, sit_a.id)["titre"] == sit_a.titre
    assert boucle.lire_boucle(conn, AUTRE_TENANT, sit_b.id)["titre"] == sit_b.titre
    assert boucle.lire_boucle(conn, TENANT, sit_b.id) is None
    assert boucle.lire_boucle(conn, AUTRE_TENANT, sit_a.id) is None

    from jumeau import entreprise_depot
    assert len(entreprise_depot.lister_objets(conn, TENANT)) == 6
    assert len(entreprise_depot.lister_objets(conn, AUTRE_TENANT)) == 6

    with pytest.raises(boucle.BoucleInvalide):
        boucle.ouvrir_investigation(sit_b, tenant_id=TENANT)


@besoin_pg
def test_historique_et_as_dict(conn):
    sit = situation(titre="Version 1")
    boucle.enregistrer_boucle(conn, TENANT, sit, historique=True)
    sit_v2 = situation(titre="Version 2")
    boucle.enregistrer_boucle(conn, TENANT, sit_v2, historique=True)

    courant = boucle.lire_boucle(conn, TENANT, sit.id, historique=False, as_dict=False)
    assert isinstance(courant, boucle.Situation) and courant.titre == "Version 2"

    avec_historique = boucle.lire_boucle(conn, TENANT, sit.id, historique=True)
    assert avec_historique["version"] == 2
    assert [entree["titre"] for entree in avec_historique["historique"]] == ["Version 1"]
    assert [objet["id"] for objet in avec_historique["chaine"]] == [sit.id]

    modele = boucle.lire_boucle(conn, TENANT, sit.id, historique=True, as_dict=False)
    assert isinstance(modele, boucle.Situation)
    assert modele.historique[0]["titre"] == "Version 1"
    assert [objet.id for objet in modele.chaine] == [sit.id]


def test_objets_et_boucle_serialisables_en_json():
    sit, investigation, _, decision, initiative, outcome, learning = chaine()
    objets = (sit, investigation, decision, initiative, outcome, learning)
    for objet in objets:
        texte = json.dumps(objet.to_dict(), ensure_ascii=False)
        assert json.loads(texte)["id"] == objet.id

    texte = json.dumps([objet.to_dict() for objet in objets], ensure_ascii=False)
    boucle_json = json.loads(texte)
    assert [objet["type"] for objet in boucle_json] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]
    assert boucle_json[4]["mesure"]["valeur"] == 4.2
    assert boucle_json[5]["outcome_ids"] == [objets[4].id]
