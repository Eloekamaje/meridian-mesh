"""Outcomes mesurés et Learnings réutilisables : chaîne complète, refus sans leçon, tenants et classement."""
import pytest

from jumeau import boucle, calibration, entreprise_depot, outcomes
from jumeau.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
DATES = {
    "cree_le": "2026-10-01T08:00:00+00:00",
    "observe_le": "2026-10-02T09:00:00+00:00",
    "valide_depuis": "2026-10-02T09:00:00+00:00",
}


def _chaine(conn, prefixe, tenant=TENANT):
    situation = boucle.Situation(
        id=f"sit-{prefixe}", tenant_id=tenant, titre="Délai de traitement en hausse",
        resume="Le délai dépasse la cible", twin_ids=["twin-process"], **DATES)
    investigation = boucle.ouvrir_investigation(
        situation, id=f"inv-{prefixe}", titre="Comprendre le délai",
        question="Pourquoi 12 jours ?")
    proposition = boucle.proposer_decision(
        investigation, ["Automatiser", "Réorganiser"], ["coût", "délai"],
        id=f"dec-{prefixe}")
    decision = boucle.trancher_decision(
        proposition, "comité-cartes", "Automatiser",
        rationale="Réduire le délai sans ajouter d'effectif")
    initiative = boucle.lancer_initiative(
        decision, id=f"ini-{prefixe}", titre="Automatiser la pièce")
    boucle.enregistrer_boucle(conn, tenant, [situation, investigation, decision, initiative])
    return situation, investigation, decision, initiative


def _learning_direct(identifiant, enonce, outcome_id, *, situations=(), twins=(), cree_le):
    return {
        "id": identifiant, "type": "LEARNING", "tenant_id": TENANT, "titre": enonce,
        "cree_le": cree_le, "observe_le": cree_le, "valide_depuis": cree_le,
        "donnees": {
            "enonce": enonce, "resume": enonce, "outcome_ids": [outcome_id],
            "situation_ids": list(situations), "twin_ids": list(twins),
            "situation_id": situations[0] if situations else None,
        },
    }


@besoin_pg
def test_mesurer_et_capitaliser_chaine_complete(conn):
    situation, investigation, decision, initiative = _chaine(conn, "ok")

    resultat = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id,
        {"metrique": "delai_moyen_jours", "valeur": 4.2, "source": "suivi-cartes"},
        cible=5, periode="2026-10", preuve_ids=["preuve-1"],
        situation_ids=[situation.id], twin_ids=["twin-process"],
        enseignement="Automatiser la pièce réduit le délai de traitement",
        conditions_reutilisation=["volume stable"], acteur="comité-cartes")

    outcome, learning = resultat["outcome"], resultat["learning"]
    assert outcome["type"] == "OUTCOME"
    assert outcome["famille"] == "resultat_apprentissage"
    assert outcome["donnees"]["initiative_id"] == initiative.id
    assert outcome["donnees"]["mesure"]["valeur"] == 4.2
    assert outcome["donnees"]["valeur_attendue"] == 5
    assert outcome["donnees"]["periode"] == "2026-10"
    assert outcome["donnees"]["preuves"] == ["preuve-1"]

    donnees = learning["donnees"]
    assert learning["type"] == "LEARNING"
    assert donnees["enonce"] == "Automatiser la pièce réduit le délai de traitement"
    assert donnees["outcome_ids"] == [outcome["id"]]
    assert donnees["investigation_ids"] == [investigation.id]
    assert donnees["situation_id"] == situation.id
    assert donnees["situation_ids"] == [situation.id]
    assert donnees["twin_ids"] == ["twin-process"]
    assert donnees["initiative_id"] == initiative.id
    assert donnees["decision_id"] == decision.id
    assert donnees["conditions_applicabilite"] == ["volume stable"]
    assert donnees["conditions_reutilisation"] == ["volume stable"]
    assert donnees["acteur"] == "comité-cartes"

    relu = boucle.lire_boucle(conn, TENANT, learning["id"])
    assert relu["donnees"]["enonce"] == donnees["enonce"]
    canonique = boucle.lire_boucle(conn, TENANT, learning["id"], as_dict=False)
    assert isinstance(canonique, boucle.Learning)
    assert canonique.outcome_ids == [outcome["id"]]


@besoin_pg
def test_learning_relie_prediction_decision_conditions_et_mesure(conn):
    situation, _, decision, initiative = _chaine(conn, "pred")
    prediction = calibration.enregistrer(
        conn, TENANT, id="pred-1", decision_id=decision.id, confidence=0.7)

    resultat = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"metrique": "delai_moyen_jours", "valeur": 4.2},
        cible=5, periode="2026-10", decision_id=decision.id,
        prediction_id=prediction.id, situation_ids=[situation.id],
        enseignement="Automatiser la pièce réduit le délai",
        conditions_reutilisation=["volume stable"])

    outcome, learning = resultat["outcome"], resultat["learning"]
    donnees = learning["donnees"]
    assert donnees["prediction_id"] == prediction.id
    assert donnees["decision_id"] == decision.id
    assert donnees["conditions_reutilisation"] == ["volume stable"]
    assert donnees["outcome_ids"] == [outcome["id"]]
    assert outcome["donnees"]["mesure"]["valeur"] == 4.2
    assert calibration.lire(conn, TENANT, prediction.id).outcome is None


@besoin_pg
def test_prediction_incoherente_refusee_avant_toute_ecriture(conn):
    _, _, _, initiative = _chaine(conn, "pred-ko")
    calibration.enregistrer(
        conn, TENANT, id="pred-autre", decision_id="dec-autre", confidence=0.4)
    calibration.enregistrer(
        conn, AUTRE_TENANT, id="pred-etranger", decision_id="dec-etranger", confidence=0.4)

    for prediction_id in ("pred-autre", "pred-absent", "pred-etranger"):
        with pytest.raises(boucle.BoucleInvalide):
            outcomes.mesurer_et_capitaliser(
                conn, TENANT, initiative.id, {"valeur": 1},
                prediction_id=prediction_id, enseignement="Leçon refusée")

    assert entreprise_depot.lister_objets(conn, TENANT, type_="OUTCOME") == []
    assert entreprise_depot.lister_objets(conn, TENANT, type_="LEARNING") == []


@besoin_pg
def test_sans_enseignement_refuse_et_n_ecrit_rien(conn):
    _, _, _, initiative = _chaine(conn, "vide")

    for enseignement in (None, "", "   "):
        with pytest.raises(outcomes.EnseignementRequis):
            outcomes.mesurer_et_capitaliser(
                conn, TENANT, initiative.id, {"valeur": 1}, enseignement=enseignement)

    assert entreprise_depot.lister_objets(conn, TENANT, type_="OUTCOME") == []
    assert entreprise_depot.lister_objets(conn, TENANT, type_="LEARNING") == []


@besoin_pg
def test_initiative_et_learning_isoles_par_tenant(conn):
    situation, _, _, initiative = _chaine(conn, "iso")
    resultat = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 1}, situation_ids=[situation.id],
        twin_ids=["twin-process"], enseignement="Leçon du tenant banque")
    learning = resultat["learning"]

    with pytest.raises(boucle.BoucleInvalide):
        outcomes.mesurer_et_capitaliser(
            conn, AUTRE_TENANT, initiative.id, {"valeur": 1},
            enseignement="Leçon inter-tenants refusée")

    assert entreprise_depot.lister_objets(conn, AUTRE_TENANT, type_="OUTCOME") == []
    assert entreprise_depot.lister_objets(conn, AUTRE_TENANT, type_="LEARNING") == []
    assert outcomes.learnings_pour(conn, AUTRE_TENANT, situation_id=situation.id) == []
    assert [ligne["id"] for ligne in outcomes.learnings_pour(
        conn, TENANT, situation_id=situation.id)] == [learning["id"]]

    with pytest.raises(outcomes.LearningIntrouvable):
        outcomes.marquer_reutilise(conn, AUTRE_TENANT, learning["id"], situation.id, "acteur")


@besoin_pg
def test_learnings_pour_classe_situation_exacte_puis_twin(conn):
    situation, _, _, initiative = _chaine(conn, "rank")
    exact = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 1}, situation_ids=[situation.id],
        twin_ids=["twin-carte"], enseignement="Situation exacte")["learning"]
    twin = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 2}, situation_ids=["sit-autre"],
        twin_ids=["twin-carte"], enseignement="Twin partagé")["learning"]
    loin = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 3}, situation_ids=["sit-loin"],
        twin_ids=["twin-autre"], enseignement="Sans lien")["learning"]

    trouves = outcomes.learnings_pour(
        conn, TENANT, situation_id=situation.id, twin_ids=["twin-carte"])
    assert [ligne["id"] for ligne in trouves] == [exact["id"], twin["id"]]
    assert loin["id"] not in [ligne["id"] for ligne in trouves]
    assert [ligne["id"] for ligne in outcomes.learnings_pour(
        conn, TENANT, twin_ids=["twin-carte"])] == [twin["id"], exact["id"]]


@besoin_pg
def test_learnings_pour_recence_deterministe(conn):
    situation, _, _, initiative = _chaine(conn, "rec")
    outcome = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 1}, situation_ids=[situation.id],
        twin_ids=["twin-rec"], enseignement="Base")["outcome"]

    ancien = _learning_direct(
        "lea-ancien", "Ancien", outcome["id"], situations=[situation.id],
        twins=["twin-rec"], cree_le="2026-10-01T08:00:00+00:00")
    recent = _learning_direct(
        "lea-recent", "Récent", outcome["id"], situations=[situation.id],
        twins=["twin-rec"], cree_le="2026-10-05T08:00:00+00:00")
    boucle.enregistrer_boucle(conn, TENANT, [recent, ancien])

    identifiants = [
        ligne["id"] for ligne in outcomes.learnings_pour(
            conn, TENANT, twin_ids=["twin-rec"], limite=10)
    ]
    assert identifiants.index("lea-recent") < identifiants.index("lea-ancien")


@besoin_pg
def test_marquer_reutilise_ajoute_audit_sans_changer_le_sens(conn):
    situation, _, _, initiative = _chaine(conn, "reuse")
    learning = outcomes.mesurer_et_capitaliser(
        conn, TENANT, initiative.id, {"valeur": 1}, situation_ids=[situation.id],
        enseignement="Leçon réutilisable")["learning"]
    avant = boucle.lire_boucle(conn, TENANT, learning["id"])

    marque = outcomes.marquer_reutilise(
        conn, TENANT, learning["id"], situation.id, "comité-cartes")

    assert marque["donnees"]["enonce"] == avant["donnees"]["enonce"]
    assert marque["donnees"]["outcome_ids"] == avant["donnees"]["outcome_ids"]
    assert marque["version"] == avant["version"] + 1
    reutilisation = marque["donnees"]["reutilisations"][-1]
    assert reutilisation["situation_id"] == situation.id
    assert reutilisation["acteur"] == "comité-cartes"
    assert reutilisation["le"]

    encore = outcomes.marquer_reutilise(
        conn, TENANT, learning["id"], situation.id, "équipe-cartes")
    assert len(encore["donnees"]["reutilisations"]) == 2
    assert encore["donnees"]["reutilisations"][-1]["acteur"] == "équipe-cartes"
    assert encore["donnees"]["enonce"] == avant["donnees"]["enonce"]

    nouvelle = outcomes.marquer_reutilise(
        conn, TENANT, learning["id"], "sit-nouvelle", "veille")
    assert nouvelle["donnees"]["reutilisations"][-1]["situation_id"] == "sit-nouvelle"
