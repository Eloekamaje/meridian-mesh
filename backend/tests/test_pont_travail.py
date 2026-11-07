"""Pont Travail → canonique C2 : logique pure, idempotence et extraction de trace.

Ces tests n'ouvrent ni Mongo ni Postgres. Ils fixent le contrat du service pur appelé par
les routes legacy (`/situations/{sid}/action`, `/situations/{sid}/decision`) et par le
producteur `GET /cases/{id}`.
"""
from __future__ import annotations

import pytest

from meridian.application import pont_canonique as pont
from meridian.application import pont_travail as pont_travail

TENANT = "banque"
AUTRE = "assurance"
DATE = "2026-11-05T09:00:00+00:00"
DECIDE_LE = "2026-11-06T10:00:00+00:00"


@pytest.fixture(autouse=True)
def _cles_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, "cle-de-test-pont-canonique-32")
    monkeypatch.setenv(pont.PONT_KEY_INTERNE_ENV, "cle-de-test-pont-interne-32")


def une_situation(**champs):
    base = {
        "id": "sit-1",
        "tenant_id": TENANT,
        "titre": "Latence des paiements",
        "resume": "Le délai dépasse la cible.",
        "statut": "active",
        "priorite": "haute",
        "jumeaux": ["paiements"],
        "cree_le": DATE,
    }
    base.update(champs)
    return base


def un_case(**champs):
    base = {
        "id": "case-1",
        "tenant_id": TENANT,
        "titre": "Travail latence",
        "situations": ["sit-1"],
        "jumeaux": ["paiements"],
        "decisions": [{"texte": "Automatiser", "par": "alice", "quand": DECIDE_LE}],
        "cree_le": DATE,
        "maj_le": DECIDE_LE,
    }
    base.update(champs)
    return base


def _objets(evenement):
    return pont.objets_depuis_evenement(
        evenement, tenant_id=evenement["tenant_id"], maintenant=DATE)


# ---------------------------------------------------------------------------
# Événement de situation (action / décision)
# ---------------------------------------------------------------------------


def test_evenement_action_est_idempotent_et_porte_le_nouveau_statut():
    situation = une_situation(statut="en investigation", maj_le=DATE)

    premier = pont_travail.evenement_action_situation(
        situation, "investiguer", tenant_id=TENANT, maintenant=DATE)
    rejeu = pont_travail.evenement_action_situation(
        situation, "investiguer", tenant_id=TENANT, maintenant=DATE)

    assert premier["_id"] == rejeu["_id"]
    assert premier["operation"] == pont.OPERATION_SITUATION
    assert premier["canonical_id"] == "sit-1"
    objets = _objets(premier)
    assert {objet["type"] for objet in objets} >= {"SITUATION", "INVESTIGATION"}
    investigation = next(objet for objet in objets if objet["type"] == "INVESTIGATION")
    assert investigation["id"] == pont.investigation_id("sit-1")
    assert investigation["donnees"]["statut"] == "OPEN"


def test_evenement_action_differente_change_la_cle_d_idempotence():
    situation = une_situation(statut="en investigation")

    investiguer = pont_travail.evenement_action_situation(
        situation, "investiguer", tenant_id=TENANT, maintenant=DATE)
    qualifier = pont_travail.evenement_action_situation(
        situation, "qualifier", tenant_id=TENANT, maintenant=DATE)

    assert investiguer["_id"] != qualifier["_id"]


def test_evenement_decision_produit_une_decision_decidee():
    situation = une_situation(
        statut="décidée", decision="Automatiser la pièce", decidee_par="alice",
        decidee_le=DECIDE_LE, options=[{"titre": "Automatiser la pièce"}])

    evenement = pont_travail.evenement_decision_situation(
        situation, tenant_id=TENANT, maintenant=DATE)

    assert evenement["operation"] == pont.OPERATION_SITUATION
    objets = _objets(evenement)
    decision = next(objet for objet in objets if objet["type"] == "DECISION")
    assert decision["id"] == pont.decision_situation_id("sit-1", 1)
    assert decision["donnees"]["statut"] == "DECIDED"
    assert decision["donnees"]["choix"] == "Automatiser la pièce"
    assert decision["donnees"]["acteur"] == "alice"


def test_evenement_decision_est_idempotent_meme_si_l_horodatage_change():
    situation = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE)

    premier = pont_travail.evenement_decision_situation(
        situation, tenant_id=TENANT, maintenant=DATE)
    rejeu = pont_travail.evenement_decision_situation(
        situation, tenant_id=TENANT, maintenant="2026-11-07T08:00:00+00:00")

    assert premier["_id"] == rejeu["_id"]


def test_evenement_decision_differente_change_la_cle_d_idempotence():
    premiere = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE)
    seconde = une_situation(
        statut="décidée", decision="Externaliser", decidee_par="alice",
        decidee_le=DECIDE_LE)

    ev1 = pont_travail.evenement_decision_situation(
        premiere, tenant_id=TENANT, maintenant=DATE)
    ev2 = pont_travail.evenement_decision_situation(
        seconde, tenant_id=TENANT, maintenant=DATE)

    assert ev1["_id"] != ev2["_id"]


def test_evenement_decision_sans_texte_ne_produit_rien():
    situation = une_situation(statut="décidée", decision="", decidee_par="alice")

    assert pont_travail.evenement_decision_situation(
        situation, tenant_id=TENANT, maintenant=DATE) is None


def test_un_document_d_un_autre_tenant_est_refuse():
    situation = une_situation(tenant_id=AUTRE)

    with pytest.raises(pont.TenantMismatch):
        pont_travail.evenement_action_situation(
            situation, "surveiller", tenant_id=TENANT, maintenant=DATE)


# ---------------------------------------------------------------------------
# Case lié : seul `situations[0]` produit des objets (ADR-0008)
# ---------------------------------------------------------------------------


def test_case_lie_produit_sa_decision_avec_l_ancre_de_la_situation():
    evenement = pont_travail.evenement_case_lie(
        un_case(), une_situation(), tenant_id=TENANT, maintenant=DATE)

    assert evenement is not None
    assert evenement["operation"] == pont.OPERATION_CASE
    objets = _objets(evenement)
    assert [objet["type"] for objet in objets] == [
        "SITUATION", "INVESTIGATION", "DECISION"]
    decision = objets[-1]
    assert decision["id"] == pont.decision_case_id("case-1", 1)
    assert decision["donnees"]["statut"] == "DECIDED"
    assert decision["donnees"]["situation_id"] == "sit-1"


def test_case_lie_utilise_le_snapshot_anterieur_comme_ancre():
    avant = une_situation(statut="active", maj_le=DATE)
    apres = une_situation(statut="décidée", decision="Automatiser",
                          decidee_par="alice", decidee_le=DECIDE_LE,
                          maj_le=DECIDE_LE)

    evenement = pont_travail.evenement_case_lie(
        un_case(), apres, tenant_id=TENANT, situation_contexte=avant,
        maintenant=DATE)
    objets = _objets(evenement)

    situation = next(objet for objet in objets if objet["type"] == "SITUATION")
    decision = next(objet for objet in objets if objet["type"] == "DECISION")
    assert situation["donnees"]["statut"] == "CANDIDATE"
    assert situation["donnees"]["_pont"]["source_maj_le"] == DATE
    assert decision["donnees"]["_pont"]["source_maj_le"] == DECIDE_LE


def test_case_sans_situation_ne_produit_rien():
    case = un_case(situations=[])

    assert pont_travail.evenement_case_lie(
        case, une_situation(), tenant_id=TENANT, maintenant=DATE) is None


def test_case_non_lie_a_la_situation_ne_produit_rien():
    case = un_case(situations=["sit-autre"])

    assert pont_travail.evenement_case_lie(
        case, une_situation(), tenant_id=TENANT, maintenant=DATE) is None


def test_case_sans_decision_ne_produit_rien():
    case = un_case(decisions=[])

    assert pont_travail.evenement_case_lie(
        case, une_situation(), tenant_id=TENANT, maintenant=DATE) is None


def test_un_case_d_un_autre_tenant_est_refuse():
    case = un_case(tenant_id=AUTRE)

    with pytest.raises(pont.TenantMismatch):
        pont_travail.evenement_case_lie(
            case, une_situation(), tenant_id=TENANT, maintenant=DATE)


# ---------------------------------------------------------------------------
# Résolution de l'objet canonique courant
# ---------------------------------------------------------------------------


def test_candidat_boucle_prefere_la_derniere_decision_du_travail():
    case = un_case(decisions=[{"texte": "A"}, {"texte": "B"}])
    situation = une_situation(statut="décidée", decision="Automatiser")

    assert pont_travail.candidat_boucle(case, situation) == pont.decision_case_id(
        "case-1", 2)


def test_candidat_boucle_retombe_sur_la_decision_de_la_situation():
    case = un_case(decisions=[])
    situation = une_situation(
        statut="décidée", decision="Automatiser", decisions=[{"texte": "A"}, {"texte": "B"}])

    assert pont_travail.candidat_boucle(case, situation) == pont.decision_situation_id(
        "sit-1", 2)


def test_candidat_boucle_retombe_sur_l_investigation():
    case = un_case(decisions=[])
    situation = une_situation(statut="en investigation")

    assert pont_travail.candidat_boucle(case, situation) == pont.investigation_id(
        "sit-1")


def test_candidat_boucle_sans_situation_est_absent():
    assert pont_travail.candidat_boucle(un_case(situations=[]), une_situation()) is None


# ---------------------------------------------------------------------------
# Extraction de la trace publique
# ---------------------------------------------------------------------------


def _ligne(identifiant, type_, titre=None, statut=None, **extra):
    ligne = {"id": identifiant, "type": type_, "donnees": dict(extra)}
    if titre is not None:
        ligne["titre"] = titre
    if statut is not None:
        ligne["donnees"]["statut"] = statut
    return ligne


def test_extraire_boucle_respecte_le_contrat_et_ne_fuit_pas_les_donnees():
    ligne = {
        **_ligne("dec-1", "DECISION", "Automatiser", "DECIDED", secret="ne-doit-pas-sortir"),
        "tenant_id": TENANT,
        "chaine": [
            _ligne("sit-1", "SITUATION", "Latence des paiements", "DECIDED"),
            _ligne("inv-sit-1", "INVESTIGATION", "Comprendre le goulot", "OPEN"),
            _ligne("dec-1", "DECISION", "Automatiser", "DECIDED", secret="x"),
        ],
    }

    trace = pont_travail.extraire_boucle(ligne)

    assert trace == {
        "id": "dec-1",
        "statut": "DECIDED",
        "chaine": [
            {"id": "sit-1", "type": "SITUATION", "titre": "Latence des paiements",
             "statut": "DECIDED"},
            {"id": "inv-sit-1", "type": "INVESTIGATION", "titre": "Comprendre le goulot",
             "statut": "OPEN"},
            {"id": "dec-1", "type": "DECISION", "titre": "Automatiser",
             "statut": "DECIDED"},
        ],
    }


def test_extraire_boucle_sans_chaine_utilise_l_objet_courant():
    ligne = _ligne("inv-sit-1", "INVESTIGATION", "Comprendre", "OPEN")

    trace = pont_travail.extraire_boucle(ligne)

    assert trace == {
        "id": "inv-sit-1",
        "statut": "OPEN",
        "chaine": [{"id": "inv-sit-1", "type": "INVESTIGATION",
                    "titre": "Comprendre", "statut": "OPEN"}],
    }


def test_extraire_boucle_ignore_les_etapes_incompletes():
    ligne = {
        "id": "dec-1",
        "type": "DECISION",
        "chaine": [{"id": "sit-1"}, {"id": "dec-1", "type": "DECISION"}],
    }

    trace = pont_travail.extraire_boucle(ligne)

    assert trace["chaine"] == [{"id": "dec-1", "type": "DECISION"}]
    assert trace["id"] == "dec-1"


def test_extraire_boucle_absent_rend_none():
    assert pont_travail.extraire_boucle(None) is None
    assert pont_travail.extraire_boucle({}) is None


def test_candidat_boucle_compte_comme_le_builder_pour_les_decisions_scalaires():
    situation = une_situation(statut="décidée", decision="Automatiser")
    case = un_case(decisions=[])

    assert pont_travail.candidat_boucle(case, situation) == pont.decision_situation_id(
        "sit-1", 1)


def test_candidat_boucle_ignore_une_liste_de_decisions_vides_et_retombe_sur_le_champ():
    situation = une_situation(
        statut="décidée", decision="Automatiser", decisions=[{"options": []}, ""])

    assert pont_travail.candidat_boucle(un_case(decisions=[]), situation) == (
        pont.decision_situation_id("sit-1", 1))


def test_extraire_boucle_ne_garde_que_id_type_titre_statut():
    trace = pont_travail.extraire_boucle({
        "id": "sit-1", "type": "SITUATION", "titre": "T", "tenant_id": "banque",
        "famille": "emergence", "mode": "DECLARED", "donnees": {"statut": "CANDIDATE",
                                                                "secret": "x"},
    })

    assert trace == {"id": "sit-1", "statut": "CANDIDATE",
                     "chaine": [{"id": "sit-1", "type": "SITUATION", "titre": "T",
                                  "statut": "CANDIDATE"}]}


def test_situation_liee_refuse_les_formes_ambigues():
    assert pont_travail.situation_liee(None) is None
    assert pont_travail.situation_liee({"situations": "sit-1"}) is None
    assert pont_travail.situation_liee({"situations": [{"situation_id": "sit-2"}]}) == "sit-2"


def test_evenement_action_sans_statut_ne_produit_rien():
    situation = une_situation()
    situation.pop("statut")

    assert pont_travail.evenement_action_situation(
        situation, "surveiller", tenant_id=TENANT, maintenant=DATE) is None


def test_evenement_case_lie_refuse_un_document_non_mapping():
    with pytest.raises(pont.PontInvalide):
        pont_travail.evenement_case_lie("case", une_situation(), tenant_id=TENANT)
    with pytest.raises(pont.PontInvalide):
        pont_travail.evenement_case_lie(un_case(), "situation", tenant_id=TENANT)


def test_candidat_boucle_compte_une_decision_portee_par_ses_options():
    situation = une_situation(
        statut="décidée", decision="", decisions=[{"options": [{"titre": "Automatiser"}]}])

    assert pont_travail.candidat_boucle(un_case(decisions=[]), situation) == (
        pont.decision_situation_id("sit-1", 1))


def test_extraire_boucle_ignore_une_chaine_non_mapping():
    trace = pont_travail.extraire_boucle({
        "id": "sit-1", "type": "SITUATION", "chaine": ["bruit", None,
                                                      {"id": "sit-1", "type": "SITUATION"}],
    })

    assert trace["chaine"] == [{"id": "sit-1", "type": "SITUATION"}]


def test_evenement_action_suit_la_version_maj_le():
    premiere = une_situation(statut="surveillée", maj_le=DATE)
    seconde = une_situation(statut="surveillée", maj_le="2026-11-06T09:00:00+00:00")

    ev1 = pont_travail.evenement_action_situation(
        premiere, "surveiller", tenant_id=TENANT, maintenant=DATE)
    ev2 = pont_travail.evenement_action_situation(
        seconde, "surveiller", tenant_id=TENANT, maintenant=DATE)

    assert ev1["_id"] != ev2["_id"]


def test_candidat_boucle_suit_le_rang_reel_des_decisions_du_travail():
    case = un_case(decisions=[{"texte": "A"}, {"texte": ""}, {"texte": "C"}])

    assert pont_travail.candidat_boucle(case, une_situation()) == (
        pont.decision_case_id("case-1", 3))


def test_candidat_boucle_ignore_une_derniere_decision_blanche():
    case = un_case(decisions=[{"texte": "A"}, {"texte": ""}])

    assert pont_travail.candidat_boucle(case, une_situation()) == (
        pont.decision_case_id("case-1", 1))


def test_filtre_tenant_strict_et_alias_demo():
    local = pont_travail.filtre_tenant("local")
    banque = pont_travail.filtre_tenant("banque")

    assert local == {"tenant_id": {"$in": ["local", "demo"]}}
    assert banque == {"tenant_id": {"$in": ["banque"]}}


def test_la_trace_lue_par_c1_respecte_le_contrat_du_front():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import boucle as boucle_pg
    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    situation = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE, maj_le=DECIDE_LE,
        options=[{"titre": "Automatiser"}])
    evenement = pont_travail.evenement_decision_situation(
        situation, tenant_id=TENANT, maintenant=DECIDE_LE)
    conn = ConnexionPont()

    resultat = pont_pg.appliquer_evenement(conn, evenement, maintenant=DECIDE_LE)
    identifiant = pont.decision_situation_id("sit-1", 1)
    assert identifiant in resultat["ecrits"]

    ligne = boucle_pg.lire_boucle(conn, TENANT, identifiant, historique=True)
    trace = pont_travail.extraire_boucle(ligne)

    assert trace["id"] == identifiant
    assert trace["statut"] == "DECIDED"
    assert [etape["type"] for etape in trace["chaine"]] == [
        "SITUATION", "INVESTIGATION", "DECISION"]
    assert all({"id", "type"} <= set(etape) for etape in trace["chaine"])


# ---------------------------------------------------------------------------
# Correctifs de revue adversariale : tenant strict, alias, version d'ancre
# ---------------------------------------------------------------------------


def test_filtre_tenant_est_strict_par_defaut(monkeypatch):
    monkeypatch.delenv(pont_travail.ADOPTION_ENV, raising=False)
    monkeypatch.delenv(pont_travail.LEGACY_TENANT_ENV, raising=False)

    filtre = pont_travail.filtre_tenant("banque")

    assert filtre == {"tenant_id": {"$in": ["banque"]}}
    assert "$or" not in filtre


def test_adoption_legacy_seulement_pour_le_tenant_configure(monkeypatch):
    monkeypatch.setenv(pont_travail.ADOPTION_ENV, "1")
    monkeypatch.setenv(pont_travail.LEGACY_TENANT_ENV, "legacy")

    adoptif = pont_travail.filtre_tenant("legacy")
    strict = pont_travail.filtre_tenant("autre")

    assert {"tenant_id": {"$exists": False}} in adoptif["$or"]
    assert {"tenant_id": None} in adoptif["$or"]
    assert strict == {"tenant_id": {"$in": ["autre"]}}


def test_adoption_sans_tenant_legacy_configure_est_inactive(monkeypatch):
    monkeypatch.setenv(pont_travail.ADOPTION_ENV, "1")
    monkeypatch.delenv(pont_travail.LEGACY_TENANT_ENV, raising=False)

    assert pont_travail.filtre_tenant("local") == {"tenant_id": {"$in": ["local", "demo"]}}


def test_alias_demo_est_canonise_en_local(monkeypatch):
    monkeypatch.delenv(pont_travail.ADOPTION_ENV, raising=False)

    assert pont_travail.normaliser_tenant("demo") == "local"
    assert pont_travail.filtre_tenant("local") == {
        "tenant_id": {"$in": ["local", "demo"]}}


def test_evenement_d_un_document_demo_parle_le_tenant_local():
    situation = une_situation(tenant_id="demo", maj_le=DATE)
    case = un_case(tenant_id="demo", maj_le=DATE)

    ev_situation = pont_travail.evenement_action_situation(
        situation, "surveiller", tenant_id="local", maintenant=DATE)
    ev_case = pont_travail.evenement_case_lie(
        case, situation, tenant_id="local", maintenant=DATE)

    assert ev_situation["tenant_id"] == "local"
    assert ev_situation["payload"]["situation"]["tenant_id"] == "local"
    assert ev_case["tenant_id"] == "local"
    assert ev_case["payload"]["situation"]["tenant_id"] == "local"


def test_case_event_id_change_avec_le_contenu_meme_si_maj_le_est_identique():
    premier = pont_travail.evenement_case_lie(
        un_case(maj_le=DATE), une_situation(), tenant_id=TENANT, maintenant=DATE)
    second = pont_travail.evenement_case_lie(
        un_case(maj_le=DATE, decisions=[{"texte": "Externaliser", "par": "alice"}]),
        une_situation(), tenant_id=TENANT, maintenant=DATE)

    assert premier["_id"] != second["_id"]


def test_case_event_rejoue_avec_le_meme_contenu_garde_le_meme_id():
    case = un_case(maj_le=DATE)

    premier = pont_travail.evenement_case_lie(
        case, une_situation(), tenant_id=TENANT, maintenant=DATE)
    rejeu = pont_travail.evenement_case_lie(
        case, une_situation(), tenant_id=TENANT, maintenant=DATE)

    assert premier["_id"] == rejeu["_id"]


def test_case_event_versionne_un_snapshot_sans_date_sous_la_situation():
    from datetime import datetime

    avant = une_situation()
    for champ in ("cree_le", "detectee", "observe_le", "maj_le"):
        avant.pop(champ, None)
    apres = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE, maj_le=DECIDE_LE)

    evenement = pont_travail.evenement_case_lie(
        un_case(), apres, tenant_id=TENANT, situation_contexte=avant,
        maintenant=DECIDE_LE)
    objets = _objets(evenement)
    situation = next(objet for objet in objets if objet["type"] == "SITUATION")
    version = situation["donnees"]["_pont"]["source_maj_le"]

    assert datetime.fromisoformat(version) < datetime.fromisoformat(DECIDE_LE)


def test_case_et_situation_sans_date_ne_regressent_jamais_la_chaîne():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import entreprise_depot
    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    avant = une_situation()
    for champ in ("cree_le", "detectee", "observe_le", "maj_le"):
        avant.pop(champ, None)
    apres = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE, maj_le=DECIDE_LE)
    evenement_situation = pont_travail.evenement_decision_situation(
        apres, tenant_id=TENANT, maintenant=DECIDE_LE)
    evenement_case = pont_travail.evenement_case_lie(
        un_case(), apres, tenant_id=TENANT, situation_contexte=avant,
        maintenant=DECIDE_LE)

    def appliquer(ordre):
        conn = ConnexionPont()
        for evenement in ordre:
            pont_pg.appliquer_evenement(conn, evenement, maintenant=DECIDE_LE)
        return conn

    for ordre in ((evenement_case, evenement_situation),
                  (evenement_situation, evenement_case)):
        conn = appliquer(ordre)
        situation = entreprise_depot.lire_objet(conn, TENANT, "sit-1")
        decision_sit = entreprise_depot.lire_objet(
            conn, TENANT, pont.decision_situation_id("sit-1", 1))
        decision_case = entreprise_depot.lire_objet(
            conn, TENANT, pont.decision_case_id("case-1", 1))
        assert situation["donnees"]["statut"] == "DECIDED"
        assert decision_sit is not None
        assert decision_case is not None


def test_la_decision_de_situation_reste_lisible_par_lire_boucle():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import boucle as boucle_pg
    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    apres = une_situation(
        statut="décidée", decision="Automatiser", decidee_par="alice",
        decidee_le=DECIDE_LE, maj_le=DECIDE_LE)
    evenement = pont_travail.evenement_decision_situation(
        apres, tenant_id=TENANT, maintenant=DECIDE_LE)
    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement, maintenant=DECIDE_LE)

    identifiant = pont.decision_situation_id("sit-1", 1)
    trace = pont_travail.extraire_boucle(
        boucle_pg.lire_boucle(conn, TENANT, identifiant, historique=True))

    assert trace["id"] == identifiant
    assert trace["statut"] == "DECIDED"


def test_enfiler_lot_partage_un_seul_budget_de_temps():
    import asyncio
    import time

    from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo

    situation = une_situation(statut="surveillée", maj_le=DATE)
    evenements = [
        pont_travail.evenement_action_situation(
            situation, "surveiller", tenant_id=TENANT, maintenant=DATE),
        pont.evenement_depuis_situation(
            situation, tenant_id=TENANT, source_event_id="autre", maintenant=DATE),
    ]

    class OutboxLente:
        async def update_one(self, *args, **kwargs):
            await asyncio.sleep(5)

    debut = time.monotonic()
    resultat = asyncio.run(pont_mongo.enfiler_lot_best_effort(
        OutboxLente(), evenements, timeout=0.1))
    duree = time.monotonic() - debut

    assert resultat == []
    assert duree < 1.0


def test_un_document_demo_produit_des_objets_canoniques_local_et_un_seul():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    situation = une_situation(tenant_id="demo", statut="surveillée", maj_le=DATE)
    evenement = pont_travail.evenement_action_situation(
        situation, "surveiller", tenant_id="local", maintenant=DATE)
    conn = ConnexionPont()

    pont_pg.appliquer_evenement(conn, evenement, tenant_id="local", maintenant=DATE)

    assert {tenant for tenant, _ in conn.stock} == {"local"}
    assert (("local", "sit-1")) in conn.stock
    assert not any(tenant == "demo" for tenant, _ in conn.stock)


def test_candidat_boucle_couvre_une_decision_scalaire_du_case():
    case = un_case(decisions="Décider")

    assert pont_travail.candidat_boucle(case, une_situation()) == (
        pont.decision_case_id("case-1", 1))


def test_extraire_boucle_sur_une_ligne_scalaire_invalide_rend_none():
    assert pont_travail.extraire_boucle({"chaine": [None, "bruit"]}) is None


def test_une_nouvelle_decision_sans_bump_de_maj_le_est_bien_appliquee():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import entreprise_depot
    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    situation = une_situation(maj_le=DATE)
    premier_case = un_case(maj_le=DATE)
    second_case = un_case(maj_le=DATE, decisions=[
        {"texte": "Automatiser", "par": "alice", "quand": DECIDE_LE},
        {"texte": "Externaliser", "par": "alice", "quand": DECIDE_LE},
    ])
    ev1 = pont_travail.evenement_case_lie(
        premier_case, situation, tenant_id=TENANT, maintenant=DATE)
    ev2 = pont_travail.evenement_case_lie(
        second_case, situation, tenant_id=TENANT, maintenant=DATE)
    assert ev1["_id"] != ev2["_id"]

    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, ev1, maintenant=DATE)
    pont_pg.appliquer_evenement(conn, ev2, maintenant=DATE)

    assert entreprise_depot.lire_objet(
        conn, TENANT, pont.decision_case_id("case-1", 1)) is not None
    assert entreprise_depot.lire_objet(
        conn, TENANT, pont.decision_case_id("case-1", 2)) is not None


def test_le_boundary_canonique_centralise_demo_vers_local():
    from meridian.domain import tenant as domaine_tenant

    assert domaine_tenant.normaliser_tenant_canonique("demo") == "local"
    assert domaine_tenant.normaliser_tenant_canonique("Demo") == "local"
    assert domaine_tenant.normaliser_tenant_canonique("banque") == "banque"
    assert pont.normaliser_tenant("demo") == "local"
    situation = une_situation(tenant_id="demo", maj_le=DATE)
    evenement = pont.evenement_depuis_situation(
        situation, tenant_id="demo", source_event_id="demo-1", maintenant=DATE)
    assert evenement["tenant_id"] == "local"
    assert evenement["payload"]["situation"]["tenant_id"] == "local"


def test_une_situation_incomplete_ne_perd_pas_les_decisions_du_case():
    from aides_pont import ConnexionPont

    from meridian.adapters.outbound.postgres import entreprise_depot
    from meridian.adapters.outbound.postgres import pont_canonique as pont_pg

    avant = une_situation()
    for champ in ("titre", "priorite", "statut"):
        avant.pop(champ, None)
    apres = une_situation(maj_le=DECIDE_LE)
    evenement_case = pont_travail.evenement_case_lie(
        un_case(), apres, tenant_id=TENANT, situation_contexte=avant,
        maintenant=DECIDE_LE)

    assert evenement_case is not None
    objets = _objets(evenement_case)
    situation = next(objet for objet in objets if objet["type"] == "SITUATION")
    assert situation["titre"] == "sit-1"
    assert situation["donnees"]["priorite"] == "MOYENNE"

    conn = ConnexionPont()
    pont_pg.appliquer_evenement(conn, evenement_case, maintenant=DECIDE_LE)
    assert entreprise_depot.lire_objet(
        conn, TENANT, pont.decision_case_id("case-1", 1)) is not None
