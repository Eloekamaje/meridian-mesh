"""Boucle P1 canonique : liens, transitions, mesures, tenants et persistance Postgres."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from meridian.adapters.outbound.postgres import boucle, entreprise_depot, rls
from meridian.domain.modele_entreprise import ModeleInvalide
from meridian.tests.conftest import DSN, besoin_pg

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

    from meridian.adapters.outbound.postgres import entreprise_depot
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


# --------------------------------------------------------------------------- #
# Façade Postgres réelle : création exclusive, verrous, version et RLS.
# --------------------------------------------------------------------------- #


def _schema(conn) -> str:
    return conn.execute("SELECT current_schema()").fetchone()[0]


@besoin_pg
def test_pg_creation_exclusive_refuse_un_doublon(conn):
    objet = {
        "id": "sit-pg-doublon", "tenant_id": TENANT, "famille": "emergence",
        "type": "SITUATION", "mode": "OBSERVED", "titre": "Original",
        "donnees": {"description": "avant"},
    }
    cree = entreprise_depot.enregistrer_objet(conn, TENANT, objet, creer=True)
    assert cree["version"] == 1

    with pytest.raises(entreprise_depot.ObjetExistant):
        entreprise_depot.enregistrer_objet(
            conn, TENANT,
            {**objet, "titre": "Écrasement", "donnees": {"description": "après"}},
            creer=True)

    relu = entreprise_depot.lire_objet(conn, TENANT, "sit-pg-doublon")
    assert relu["titre"] == "Original"
    assert relu["donnees"] == {"description": "avant"}
    assert relu["version"] == 1


@besoin_pg
def test_pg_deux_creations_concurrentes_du_meme_id(conn):
    schema = _schema(conn)
    barrier = threading.Barrier(2)
    resultats = []

    def creer(connexion, marqueur):
        barrier.wait(timeout=15)
        try:
            entreprise_depot.enregistrer_objet(
                connexion, TENANT,
                {"id": "sit-pg-course", "tenant_id": TENANT, "famille": "emergence",
                 "type": "SITUATION", "mode": "OBSERVED", "titre": marqueur,
                 "donnees": {"marqueur": marqueur}}, creer=True)
            resultats.append(("ok", marqueur))
        except entreprise_depot.ObjetExistant:
            resultats.append(("conflit", marqueur))

    def creer_sur_nouvelle_connexion(marqueur):
        with psycopg.connect(DSN, autocommit=True) as connexion:
            connexion.execute(f"SET search_path TO {schema}")
            creer(connexion, marqueur)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futurs = [
            pool.submit(creer, conn, "a"),
            pool.submit(creer_sur_nouvelle_connexion, "b"),
        ]
        for futur in futurs:
            futur.result(timeout=15)

    assert sorted(statut for statut, _ in resultats) == ["conflit", "ok"]
    assert entreprise_depot.lire_objet(conn, TENANT, "sit-pg-course") is not None


@besoin_pg
def test_pg_enregistrer_donnees_refuse_une_version_perimee(conn):
    entreprise_depot.enregistrer_objet(conn, TENANT, {
        "id": "dec-pg-version", "tenant_id": TENANT, "famille": "decision",
        "type": "DECISION", "mode": "DECLARED", "titre": "Décision",
        "donnees": {"investigation_id": "inv-1", "options": ["A"],
                    "statut": "PROPOSED", "legacy": "avant"}})

    ligne = entreprise_depot.enregistrer_donnees(
        conn, TENANT, "dec-pg-version",
        {"investigation_id": "inv-1", "options": ["A"], "statut": "DECIDED",
         "legacy": "après"},
        version_attendue=1)
    assert ligne["version"] == 2

    with pytest.raises(entreprise_depot.VersionRefusee):
        entreprise_depot.enregistrer_donnees(
            conn, TENANT, "dec-pg-version",
            {"investigation_id": "inv-1", "options": ["A"], "statut": "ÉCRASÉ",
             "legacy": "jamais"},
            version_attendue=1)

    relu = entreprise_depot.lire_objet(conn, TENANT, "dec-pg-version")
    assert relu["version"] == 2
    assert relu["donnees"]["statut"] == "DECIDED"
    assert relu["donnees"]["legacy"] == "après"


@besoin_pg
def test_pg_for_update_bloque_un_update_concurrent(conn):
    entreprise_depot.enregistrer_objet(conn, TENANT, {
        "id": "sit-pg-lock", "tenant_id": TENANT, "famille": "emergence",
        "type": "SITUATION", "mode": "OBSERVED", "titre": "Verrou",
        "donnees": {"description": "initial"}})
    schema = _schema(conn)

    with conn.transaction():
        verrouille = entreprise_depot.lire_objet(
            conn, TENANT, "sit-pg-lock", for_update=True)
        assert verrouille is not None
        with psycopg.connect(DSN, autocommit=True) as autre:
            autre.execute(f"SET search_path TO {schema}")
            autre.execute("SET lock_timeout = '250ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                entreprise_depot.enregistrer_donnees(
                    autre, TENANT, "sit-pg-lock",
                    {"description": "concurrent"}, version_attendue=1)

    relu = entreprise_depot.lire_objet(conn, TENANT, "sit-pg-lock")
    assert relu["donnees"]["description"] == "initial"


@besoin_pg
def test_pg_fusionner_donnees_preserve_le_legacy(conn):
    legacy = {
        "decision_id": "dec-1", "niveau": "strategique", "genre": "a_confirmer",
        "raison": "legacy", "quand": "2026-10-01T08:00:00+00:00",
        "travail_id": "case-1", "jumeau_cible": "paiements",
        "urgence": "haute", "reponse": {"par": "paiements"},
    }
    entreprise_depot.enregistrer_objet(conn, TENANT, {
        "id": "ini-pg-legacy", "tenant_id": TENANT, "famille": "decision",
        "type": "INITIATIVE", "mode": "DECLARED", "titre": "Initiative",
        "donnees": legacy})

    ligne = boucle.fusionner_donnees(
        conn, TENANT, "ini-pg-legacy", {"outcome_ids": ["out-1"]},
        historique=True, ajouter=("outcome_ids",), version_attendue=1)
    assert ligne["version"] == 2

    relu = entreprise_depot.lire_objet(conn, TENANT, "ini-pg-legacy")
    for cle, valeur in legacy.items():
        assert relu["donnees"][cle] == valeur
    assert relu["donnees"]["outcome_ids"] == ["out-1"]
    assert relu["donnees"]["_historique"][0]["version"] == 1
    assert relu["donnees"]["_historique"][0]["donnees"]["niveau"] == "strategique"


@besoin_pg
def test_pg_rls_isole_objet_entreprise_avec_un_role_non_superuser(conn):
    role = rls.role_courant(conn)
    if not role["superuser"]:
        pytest.skip("SET ROLE de vérification nécessite un rôle superuser de test")
    surveillant = conn.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = 'pg_monitor' "
        "AND NOT rolsuper AND NOT rolbypassrls"
    ).fetchone()
    if surveillant is None:
        pytest.skip("rôle pg_monitor indisponible")

    rls.activer(conn, tables=("objet_entreprise",))
    entreprise_depot.enregistrer_objet(conn, "tenant-a", {
        "id": "oa", "tenant_id": "tenant-a", "famille": "emergence",
        "type": "SITUATION", "mode": "OBSERVED", "titre": "A"})
    entreprise_depot.enregistrer_objet(conn, "tenant-b", {
        "id": "ob", "tenant_id": "tenant-b", "famille": "emergence",
        "type": "SITUATION", "mode": "OBSERVED", "titre": "B"})
    schema = _schema(conn)
    conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO pg_monitor")
    conn.execute("GRANT SELECT, INSERT, UPDATE ON objet_entreprise TO pg_monitor")

    with conn.transaction():
        conn.execute("SET LOCAL ROLE pg_monitor")
        with rls.contexte_tenant(conn, "tenant-a"):
            assert entreprise_depot.lire_objet(conn, "tenant-a", "oa") is not None
            assert entreprise_depot.lire_objet(conn, "tenant-b", "ob") is None
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                entreprise_depot.enregistrer_objet(conn, "tenant-b", {
                    "id": "ob-2", "tenant_id": "tenant-b", "famille": "emergence",
                    "type": "SITUATION", "mode": "OBSERVED", "titre": "B2"})
