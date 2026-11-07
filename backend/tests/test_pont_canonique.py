"""Pont canonique C1 : événements, idempotence, bail/fencing, application transactionnelle.

Ces tests n'exigent ni Mongo ni Postgres réels : la collection `pont_canonique` est simulée avec
les opérateurs utilisés par l'adaptateur, et Postgres avec des transactions imbriquées qui annulent
réellement les écritures d'un bloc qui échoue.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re

import pytest

from aides_pont import CollectionPont, ConnexionPont, document_evenement, instant

from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.adapters.outbound.postgres import boucle, entreprise_depot
from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont

TENANT = "banque"
AUTRE = "assurance"
DATE = "2026-11-05T09:00:00+00:00"
DECIDE_LE = "2026-11-06T10:00:00+00:00"

SITUATION = {
    "id": "sit-1",
    "tenant_id": TENANT,
    "titre": "Délai de traitement en hausse",
    "resume": "Le délai dépasse la cible de 40 minutes.",
    "statut": "poursuivie",
    "priorite": "haute",
    "decision": "Automatiser la pièce",
    "decidee_le": DECIDE_LE,
    "decidee_par": "comité-cartes",
    "jumeaux": ["paiements", "comptes"],
    "detectee": DATE,
    "cree_le": DATE,
    "options": [{"titre": "Automatiser la pièce"}],
    "password": "hunter2-ne-doit-pas-fuiter",
}

CASE = {
    "id": "case-1",
    "tenant_id": TENANT,
    "titre": "Travail sur le délai",
    "statut": "ouvert",
    "situations": ["sit-1"],
    "jumeaux": ["paiements"],
    "decisions": [{
        "texte": "Choisir l'option libre",
        "type": "arbitrage",
        "quand": DECIDE_LE,
        "par": "alice",
    }],
    "options": [{"titre": "Option A"}],
    "cree_le": DATE,
}

PROPOSITION = {
    "id": "init-sit-1",
    "tenant_id": TENANT,
    "titre": "Traiter : Délai de traitement en hausse",
    "raison": "Le délai dépasse la cible.",
    "statut": "en_attente",
    "urgence": "haute",
    "jumeaux": ["paiements"],
    "situation_id": "sit-1",
    "quand": DATE,
    "cree_le": DATE,
}

REPONSE = {
    "choix": "créer un travail",
    "par": "alice",
    "quand": DECIDE_LE,
}


def _evenement_situation(document=None, **champs):
    return pont.evenement_depuis_situation(document or SITUATION, **champs)


def _evenement_case(document, **champs):
    return pont.evenement_depuis_case(document, **champs)


def _evenement_initiative(document, **champs):
    return pont.evenement_depuis_initiative(document, **champs)


def test_identifiant_evenement_est_deterministe_et_suit_le_contrat():
    attendu = hashlib.sha256(f"{TENANT}|situation.maj|sit-1|src-1".encode()).hexdigest()[:32]

    identifiant = pont.identifiant_evenement(TENANT, "situation.maj", "sit-1", "src-1")

    assert identifiant == attendu
    assert len(identifiant) == 32
    assert identifiant == pont.identifiant_evenement(TENANT, "situation.maj", "sit-1", "src-1")
    assert identifiant != pont.identifiant_evenement(AUTRE, "situation.maj", "sit-1", "src-1")
    assert identifiant != pont.identifiant_evenement(TENANT, "situation.maj", "sit-1", "src-2")
    assert identifiant != pont.identifiant_evenement(TENANT, "case.maj", "sit-1", "src-1")


def test_hash_contenu_est_stable_et_independant_de_l_ordre_des_cles():
    a = pont.hash_contenu({"b": 2, "a": [1, {"d": 4, "c": 3}]})
    b = pont.hash_contenu({"a": [1, {"c": 3, "d": 4}], "b": 2})

    assert a == b
    assert a == pont.hash_contenu({"a": [1, {"c": 3, "d": 4}], "b": 2})
    assert a != pont.hash_contenu({"a": [1, {"c": 3, "d": 5}], "b": 2})


def test_evenement_porte_le_contrat_outbox_et_le_hash_de_contenu():
    evenement = _evenement_situation(source_event_id="maj-1")

    assert evenement["_id"] == pont.identifiant_evenement(
        TENANT, pont.OPERATION_SITUATION, "sit-1", "maj-1")
    assert evenement["tenant_id"] == TENANT
    assert evenement["operation"] == pont.OPERATION_SITUATION
    assert evenement["canonical_ids"] == ["sit-1", "inv-sit-1", "dec-sit-sit-1-1", "ini-dec-sit-sit-1-1"]
    assert evenement["etat"] == "pending"
    assert evenement["tentatives"] == 0
    assert evenement["prochaine_tentative"] is None
    assert evenement["locked_until"] is None and evenement["lock_token"] is None
    assert evenement["fencing_token"] == 0
    assert evenement["hash"] == pont.hash_contenu(evenement["payload"])


def test_enqueue_est_idempotent_avec_set_on_insert_et_ne_reecrit_pas():
    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection)
        evenement = _evenement_situation(source_event_id="maj-1")
        premier = await depot.enfiler(evenement)
        await depot.enfiler(evenement)
        collection.documents[0]["etat"] = "done"
        collection.documents[0]["tentatives"] = 3
        second = await depot.enfiler(evenement)
        return collection, premier, second

    collection, premier, second = asyncio.run(scenario())

    assert len(collection.documents) == 1
    assert collection.documents[0]["etat"] == "done"
    assert collection.documents[0]["tentatives"] == 3
    assert premier["id"] == second["id"] == collection.documents[0]["_id"]
    assert premier["cree"] is True and second["cree"] is False
    mises_a_jour = [appel for appel in collection.appels if appel[0] == "update_one"]
    assert mises_a_jour and all("$setOnInsert" in appel[2] for appel in mises_a_jour)
    assert all("$set" not in appel[2] for appel in mises_a_jour)


def test_enqueue_best_effort_ne_leve_pas_si_mongo_est_en_panne():
    class CollectionEnPanne:
        async def update_one(self, *args, **kwargs):
            raise RuntimeError("mongo indisponible")

    depot = pont_mongo.DepotPontCanonique(CollectionEnPanne())

    assert asyncio.run(depot.enfiler_best_effort(
        _evenement_situation(source_event_id="maj-1"))) is None


def test_claim_concurrent_un_seul_worker_obtient_l_evenement():
    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement_situation(source_event_id="maj-1"))
        return await asyncio.gather(
            depot.reclamer("worker-a", bail_secondes=30),
            depot.reclamer("worker-b", bail_secondes=30),
        )

    premier, second = asyncio.run(scenario())

    obtenus = [evenement for evenement in (premier, second) if evenement]
    assert len(obtenus) == 1
    gagnant = obtenus[0]
    assert gagnant["lock_token"]
    assert gagnant["locked_until"] > instant()
    assert gagnant["fencing_token"] == 1


def test_bail_expire_est_repris_et_le_fencing_bloque_l_ancien_worker():
    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement_situation(source_event_id="maj-1"))
        premier = await depot.reclamer("worker-a", bail_secondes=30)
        # Le worker A est trop lent : son bail expire et B reprend l'événement.
        collection.documents[0]["locked_until"] = "2026-11-06T11:59:00+00:00"
        second = await depot.reclamer("worker-b", bail_secondes=30)
        fin_a = await depot.terminer(premier["_id"], premier["lock_token"],
                                     canonical_ids=["trop-tard"])
        fin_b = await depot.terminer(second["_id"], second["lock_token"],
                                     canonical_ids=["ok"])
        return collection, premier, second, fin_a, fin_b

    collection, premier, second, fin_a, fin_b = asyncio.run(scenario())

    assert premier["lock_token"] != second["lock_token"]
    assert second["fencing_token"] == 2
    assert fin_a is False
    assert fin_b is True
    assert collection.documents[0]["etat"] == "done"
    assert collection.documents[0]["canonical_ids"] == ["ok"]


def test_echec_programme_un_retry_avec_backoff_borne_et_ne_retente_pas_done():
    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement_situation(source_event_id="maj-1"))
        evenement = await depot.reclamer("worker-a", bail_secondes=30)
        echec = await depot.echouer(evenement["_id"], evenement["lock_token"], "panne temporaire")
        # Un jeton périmé ne peut pas écraser l'état.
        echec_perime = await depot.echouer(evenement["_id"], "jeton-perime", "autre panne")
        # La prochaine tentative est encore dans le futur : aucun claim.
        avant_echeance = await depot.reclamer("worker-b", bail_secondes=30)
        collection.documents[0]["prochaine_tentative"] = "2026-11-06T11:00:00+00:00"
        repris = await depot.reclamer("worker-b", bail_secondes=30)
        fini = await depot.terminer(repris["_id"], repris["lock_token"], canonical_ids=["ok"])
        apres_done = await depot.reclamer("worker-c", bail_secondes=30)
        echec_done = await depot.echouer(repris["_id"], repris["lock_token"], "ne doit pas arriver")
        return collection, echec, echec_perime, avant_echeance, repris, fini, apres_done, echec_done

    (collection, echec, echec_perime, avant_echeance, repris, fini, apres_done,
     echec_done) = asyncio.run(scenario())

    assert echec is True and echec_perime is False
    assert avant_echeance is None
    assert repris and repris["tentatives"] == 1
    assert fini is True
    assert apres_done is None
    assert echec_done is False
    assert collection.documents[0]["etat"] == "done"
    assert collection.documents[0]["tentatives"] == 1


def test_backoff_exponentiel_est_borne():
    assert pont.backoff_secondes(1, base=5, maximum=60) == 5
    assert pont.backoff_secondes(2, base=5, maximum=60) == 10
    assert pont.backoff_secondes(3, base=5, maximum=60) == 20
    assert pont.backoff_secondes(5, base=5, maximum=60) == 60
    assert pont.backoff_secondes(50, base=5, maximum=60) == 60


@pytest.mark.parametrize(("legacy", "canonique"), [
    ("active", "CANDIDATE"),
    ("en observation", "OBSERVING"),
    ("surveillée", "WATCHED"),
    ("en investigation", "INVESTIGATING"),
    ("qualifiée", "QUALIFIED"),
    ("décidée", "DECIDED"),
    ("poursuivie", "DECIDED"),
    ("reportée", "DEFERRED"),
    ("écartée", "DISMISSED"),
    ("classée", "DISMISSED"),
    ("ignorée", "DISMISSED"),
    ("archivee", "ARCHIVED"),
    ("archivée", "ARCHIVED"),
    ("inconnu", "CANDIDATE"),
    (None, "CANDIDATE"),
])
def test_mapping_des_statuts_legacy(legacy, canonique):
    assert pont.statut_canonique(legacy) == canonique


@pytest.mark.parametrize(("legacy", "canonique"), [
    ("critique", "HAUTE"),
    ("haute", "HAUTE"),
    ("normale", "MOYENNE"),
    ("moyenne", "MOYENNE"),
    ("basse", "BASSE"),
    (None, "MOYENNE"),
])
def test_mapping_des_priorites(legacy, canonique):
    assert pont.priorite_canonique(legacy) == canonique


def test_succes_ordre_des_objets_et_ecriture_complete():
    evenement = _evenement_situation(source_event_id="maj-1")
    objets = pont.objets_depuis_evenement(evenement)
    conn = ConnexionPont()

    resultat = pont_pg.appliquer_evenement(conn, evenement)

    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]
    assert [objet["id"] for objet in objets] == evenement["canonical_ids"]
    assert resultat["canonical_ids"] == evenement["canonical_ids"]
    assert set(conn.stock) == {
        (TENANT, "sit-1"), (TENANT, "inv-sit-1"),
        (TENANT, "dec-sit-sit-1-1"), (TENANT, "ini-dec-sit-sit-1-1"),
    }
    situation = boucle.lire_boucle(conn, TENANT, "sit-1", as_dict=False)
    decision = boucle.lire_boucle(conn, TENANT, "dec-sit-sit-1-1", as_dict=False)
    initiative = boucle.lire_boucle(conn, TENANT, "ini-dec-sit-sit-1-1", as_dict=False)
    assert situation.statut == "DECIDED" and situation.priorite == "HAUTE"
    assert decision.statut == "DECIDED" and decision.choix == "Automatiser la pièce"
    assert initiative.decision_id == decision.id


def test_rollback_si_le_troisieme_objet_echoue_aucun_objet_partiel(monkeypatch):
    evenement = _evenement_situation(source_event_id="maj-1")
    conn = ConnexionPont()
    vrai = entreprise_depot.enregistrer_objet
    compteur = {"appels": 0}

    def echouer_au_troisieme(conn_, tenant, objet):
        compteur["appels"] += 1
        if compteur["appels"] == 3:
            raise RuntimeError("panne injectée au 3e objet")
        return vrai(conn_, tenant, objet)

    monkeypatch.setattr(entreprise_depot, "enregistrer_objet", echouer_au_troisieme)

    with pytest.raises(RuntimeError, match="panne injectée"):
        pont_pg.appliquer_evenement(conn, evenement)

    assert compteur["appels"] == 3
    assert conn.stock == {}


def test_conflit_d_identifiant_avec_origine_non_legacy_echoue_sans_ecraser():
    conn = ConnexionPont()
    existant = {
        "id": "sit-1", "tenant_id": TENANT, "famille": "emergence", "type": "SITUATION",
        "mode": "DECLARED", "titre": "Version canonique", "donnees": {"origine": "api-canonique"},
        "version": 7, "observe_le": DATE, "valide_depuis": DATE, "cree_le": DATE, "maj_le": DATE,
    }
    conn.stock[(TENANT, "sit-1")] = copy.deepcopy(existant)

    with pytest.raises(pont_pg.ConflitCanonique):
        pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))

    assert conn.stock[(TENANT, "sit-1")] == existant
    assert conn.ecritures == []


def test_origine_pont_non_legacy_est_aussi_un_conflit():
    conn = ConnexionPont()
    existant = {
        "id": "sit-1", "tenant_id": TENANT, "famille": "emergence", "type": "SITUATION",
        "mode": "DECLARED", "titre": "Version canonique", "donnees": {
            "_pont": {"origine": "import-externe", "hash": "x" * 64}},
        "version": 2, "observe_le": DATE, "valide_depuis": DATE, "cree_le": DATE, "maj_le": DATE,
    }
    conn.stock[(TENANT, "sit-1")] = copy.deepcopy(existant)

    with pytest.raises(pont_pg.ConflitCanonique):
        pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))


def test_tenant_absent_ou_mismatch_refuse_avant_toute_ecriture():
    with pytest.raises(pont.PontInvalide):
        pont.construire_evenement("situation.maj", None, "sit-1", {"situation": SITUATION})

    with pytest.raises(pont.TenantMismatch):
        _evenement_situation({**SITUATION, "tenant_id": AUTRE}, tenant_id=TENANT)

    conn = ConnexionPont()
    evenement = _evenement_situation(source_event_id="maj-1")
    evenement["payload"]["situation"]["tenant_id"] = AUTRE
    with pytest.raises(pont.TenantMismatch):
        pont_pg.appliquer_evenement(conn, evenement)
    assert conn.stock == {} and conn.ecritures == []


def test_decision_libre_est_ajoutee_aux_options_sans_faire_echouer_la_transition():
    situation = {**SITUATION, "options": [{"titre": "Réorganiser"}], "decision": "Automatiser"}
    evenement = _evenement_situation(situation, source_event_id="maj-1")
    conn = ConnexionPont()

    pont_pg.appliquer_evenement(conn, evenement)

    decision = boucle.lire_boucle(conn, TENANT, "dec-sit-sit-1-1", as_dict=False)
    ligne = boucle.lire_boucle(conn, TENANT, "dec-sit-sit-1-1")
    assert decision.options == ["Réorganiser", "Automatiser"]
    assert decision.choix == "Automatiser"
    assert ligne["donnees"]["choix_hors_options"] is True
    assert ligne["donnees"]["_pont"]["origine"] == "legacy"


def test_init_sans_decision_humaine_ne_produit_aucune_initiative():
    proposition = _evenement_initiative(PROPOSITION, source_event_id="maj-1")
    assert pont.objets_depuis_evenement(proposition) == []
    assert proposition["canonical_ids"] == []

    acceptee_sans_choix = {**PROPOSITION, "statut": "acceptee", "reponse": {}}
    assert pont.objets_depuis_evenement(
        _evenement_initiative(acceptee_sans_choix, source_event_id="maj-2")) == []

    conn = ConnexionPont()
    resultat = pont_pg.appliquer_evenement(conn, proposition)
    assert resultat["canonical_ids"] == []
    assert conn.stock == {}


def test_init_acceptee_avec_choix_humain_produit_decision_puis_initiative():
    acceptee = {**PROPOSITION, "statut": "acceptee", "reponse": REPONSE}
    evenement = _evenement_initiative(acceptee, situation=SITUATION, source_event_id="maj-1")
    objets = pont.objets_depuis_evenement(evenement)

    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE"]
    assert "dec-init-init-sit-1" in evenement["canonical_ids"]
    assert "ini-dec-init-init-sit-1" in evenement["canonical_ids"]
    assert all(not identifiant.startswith("init-") for identifiant in evenement["canonical_ids"])

    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement)
    decision = boucle.lire_boucle(conn, TENANT, "dec-init-init-sit-1", as_dict=False)
    initiative = boucle.lire_boucle(conn, TENANT, "ini-dec-init-init-sit-1", as_dict=False)
    assert decision.choix == REPONSE["choix"]
    assert initiative.decision_id == decision.id


def test_init_refusee_produit_une_decision_sans_initiative():
    refusee = {**PROPOSITION, "statut": "refusee", "reponse": {"choix": "ignorer", "par": "alice",
                                                               "quand": DECIDE_LE}}
    evenement = _evenement_initiative(refusee, situation=SITUATION, source_event_id="maj-1")
    objets = pont.objets_depuis_evenement(evenement)

    assert [objet["type"] for objet in objets] == ["SITUATION", "INVESTIGATION", "DECISION"]
    assert all("INITIATIVE" != objet["type"] for objet in objets)


def test_learning_peut_referencer_un_outcome_deja_persiste_sans_recopier_la_mesure():
    evenement = pont.evenement_learning(
        tenant_id=TENANT, source_id="out-deja-persiste", source_type="OUTCOME",
        enseignement="Leçon déjà explicite", source_event_id="lecon-1")

    assert evenement["canonical_ids"] == ["lea-out-deja-persiste"]
    assert "mesure" not in evenement["payload"]


def test_aucun_learning_automatique_sans_enseignement():
    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))

    assert not [ligne for ligne in conn.stock.values() if ligne["type"] == "LEARNING"]
    with pytest.raises(pont.PontInvalide, match="enseignement"):
        pont.evenement_learning(tenant_id=TENANT, source_id="out-1", enseignement="")
    with pytest.raises(pont.PontInvalide, match="enseignement"):
        pont.objets_depuis_evenement(document_evenement(
            operation="learning.capitalisation", payload={"source_id": "out-1", "source_type": "OUTCOME"}))


def test_outcome_puis_learning_sont_chaines_et_idempotents():
    conn = ConnexionPont()
    situation = {**SITUATION, "statut": "poursuivie"}
    pont_pg.appliquer_evenement(
        conn, _evenement_situation(situation, source_event_id="maj-1"))
    initiative_id = "ini-dec-sit-sit-1-1"

    outcome = pont.evenement_outcome(
        tenant_id=TENANT, initiative_id=initiative_id,
        mesure={"metrique": "delai_moyen_jours", "valeur": 4.2},
        metrique="delai_moyen_jours", periode="2026-11",
        source_event_id="mesure-1")
    assert outcome["canonical_ids"] == [f"out-{initiative_id}-delai_moyen_jours-2026-11"]
    pont_pg.appliquer_evenement(conn, outcome)

    outcome_id = outcome["canonical_ids"][0]
    learning = pont.evenement_learning(
        tenant_id=TENANT, source_id=outcome_id, source_type="OUTCOME",
        mesure={"metrique": "delai_moyen_jours", "valeur": 4.2},
        enseignement="Automatiser réduit le délai", source_event_id="lecon-1")
    assert learning["canonical_ids"] == [f"lea-{outcome_id}"]
    pont_pg.appliquer_evenement(conn, learning)

    assert boucle.lire_boucle(conn, TENANT, outcome_id)["type"] == "OUTCOME"
    lecon = boucle.lire_boucle(conn, TENANT, f"lea-{outcome_id}", as_dict=False)
    assert lecon.enonce == "Automatiser réduit le délai"
    assert lecon.outcome_ids == [outcome_id]


def test_case_sans_situation_ne_produit_rien_et_case_avec_situation_produit_sa_decision():
    sans_situation = {**CASE, "situations": []}
    evenement_vide = _evenement_case(sans_situation, source_event_id="maj-1")
    assert pont.objets_depuis_evenement(evenement_vide) == []
    assert evenement_vide["canonical_ids"] == []

    evenement = _evenement_case(CASE, situation=SITUATION, source_event_id="maj-2")
    objets = pont.objets_depuis_evenement(evenement)
    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION"]
    assert "dec-case-case-1-1" in evenement["canonical_ids"]

    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement)
    decision = boucle.lire_boucle(conn, TENANT, "dec-case-case-1-1", as_dict=False)
    ligne = boucle.lire_boucle(conn, TENANT, "dec-case-case-1-1")
    assert decision.choix == "Choisir l'option libre"
    assert ligne["donnees"]["choix_hors_options"] is True


def test_deux_applications_identiques_ne_reecrivent_pas_et_ne_font_pas_monter_la_version():
    evenement = _evenement_situation(source_event_id="maj-1")
    conn = ConnexionPont()

    premier = pont_pg.appliquer_evenement(conn, evenement)
    versions = {cle: ligne["version"] for cle, ligne in conn.stock.items()}
    deuxieme = pont_pg.appliquer_evenement(conn, evenement)

    assert set(premier["ecrits"]) == set(evenement["canonical_ids"])
    assert deuxieme["ecrits"] == []
    assert {cle: ligne["version"] for cle, ligne in conn.stock.items()} == versions
    assert all("_historique" not in ligne["donnees"] for ligne in conn.stock.values())


def test_une_mise_a_jour_live_ne_force_pas_version_1():
    conn = ConnexionPont()
    existant = {
        "id": "sit-1", "tenant_id": TENANT, "famille": "emergence", "type": "SITUATION",
        "mode": "DECLARED", "titre": "Ancienne version", "donnees": {"_pont": {"origine": "legacy",
                                                                               "hash": "ancien"}},
        "version": 5, "observe_le": DATE, "valide_depuis": DATE, "valide_jusqua": None,
        "cree_le": DATE, "maj_le": DATE,
    }
    conn.stock[(TENANT, "sit-1")] = copy.deepcopy(existant)

    pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))

    assert conn.stock[(TENANT, "sit-1")]["version"] == 6


def test_rls_pose_le_contexte_tenant_dans_la_meme_transaction(monkeypatch):
    from contextlib import contextmanager

    appels = []

    @contextmanager
    def faux_contexte(conn, tenant):
        appels.append((tenant, len(conn._snapshots)))
        yield tenant

    monkeypatch.setattr(pont_pg.rls, "est_actif", lambda: True)
    monkeypatch.setattr(pont_pg.rls, "contexte_tenant", faux_contexte)
    conn = ConnexionPont()

    pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))

    assert [tenant for tenant, _ in appels] == [TENANT]
    # Le contexte est posé à l'intérieur de la transaction ouverte par l'application.
    assert appels[0][1] >= 1
    assert (TENANT, "sit-1") in conn.stock


def test_un_objet_migre_sans_origine_reste_mis_a_jour_par_le_pont():
    conn = ConnexionPont()
    existant = {
        "id": "sit-1", "tenant_id": TENANT, "famille": "emergence", "type": "SITUATION",
        "mode": "DECLARED", "titre": "Objet migré", "donnees": {"_historique": []},
        "version": 1, "observe_le": DATE, "valide_depuis": DATE, "valide_jusqua": None,
        "cree_le": DATE, "maj_le": DATE,
    }
    conn.stock[(TENANT, "sit-1")] = copy.deepcopy(existant)

    pont_pg.appliquer_evenement(conn, _evenement_situation(source_event_id="maj-1"))

    assert conn.stock[(TENANT, "sit-1")]["version"] == 2
    assert conn.stock[(TENANT, "sit-1")]["donnees"]["_pont"]["origine"] == "legacy"


def test_le_payload_ne_contient_aucun_secret_legacy():
    situation = {
        **SITUATION,
        "password": "hunter2",
        "token": "abc-secret",
        "indicateurs": {"confiance": 80, "token": "abc-secret"},
        "url": "https://user:pass@example.test/x?token=abc-secret",
    }
    evenement = _evenement_situation(situation, source_event_id="maj-1")

    texte = json.dumps(evenement, ensure_ascii=False)
    assert "hunter2" not in texte
    assert "abc-secret" not in texte
    assert "user:pass" not in texte


def test_un_champ_texte_legacy_non_scalaire_ne_fuite_pas_dans_le_canonique():
    situation = {
        **SITUATION,
        "titre": {"token": "abc-secret"},
        "resume": {"password": "hunter2"},
        "decision": {"texte": "hunter2"},
    }
    evenement = _evenement_situation(situation, source_event_id="maj-1")
    objets = pont.objets_depuis_evenement(evenement)

    texte = json.dumps(objets, ensure_ascii=False)
    assert "abc-secret" not in texte and "hunter2" not in texte
    assert objets[0]["titre"] == "sit-1"
    assert [objet["type"] for objet in objets] == ["SITUATION", "INVESTIGATION"]


def test_objets_explicites_sont_ordonnes_et_estampilles_du_hash_pont():
    situation = boucle.Situation(
        id="sit-2", tenant_id=TENANT, titre="Situation", description="desc",
        observe_le=DATE, valide_depuis=DATE, cree_le=DATE)
    investigation = boucle.ouvrir_investigation(situation, id="inv-sit-2")
    decision_proposee = boucle.proposer_decision(investigation, ["A"], id="dec-sit-2-1")
    decision = boucle.trancher_decision(decision_proposee, "alice", "A")
    initiative = boucle.lancer_initiative(decision, id="ini-dec-sit-2-1")
    outcome = boucle.mesurer_outcome(
        initiative, {"valeur": 1}, id="out-ini-dec-sit-2-1-m-2026-11", metrique="m", periode="2026-11")
    learning = boucle.capitaliser_learning(outcome, id="lea-out-ini-dec-sit-2-1-m-2026-11",
                                           enonce="Leçon")
    evenement = pont.construire_evenement(
        pont.OPERATION_OBJETS, TENANT, "sit-2",
        {"objets": [learning, outcome, initiative, decision, investigation, situation]},
        source_event_id="explicite-1")

    objets = pont.objets_depuis_evenement(evenement)

    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "OUTCOME", "LEARNING"]
    assert all(objet["donnees"]["_pont"]["origine"] == "legacy" for objet in objets)
    assert all(re.fullmatch(r"[0-9a-f]{64}", objet["donnees"]["_pont"]["hash"]) for objet in objets)
    assert all("version" not in objet for objet in objets)
