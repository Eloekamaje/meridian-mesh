"""C2 : beliefs persistés — objets révisables, confiance érodée, revalidation."""
from datetime import datetime, timezone

import psycopg
import pytest

from meridian.adapters.outbound.postgres import boucle, dossiers_raisonnement, entreprise_depot
from meridian.application import beliefs as beliefs_application
from meridian.domain import modele_entreprise as modele
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
MAINTENANT = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
DATES = {
    "cree_le": "2026-11-01T08:00:00+00:00",
    "observe_le": "2026-11-01T08:00:00+00:00",
    "valide_depuis": "2026-11-01T08:00:00+00:00",
}


def belief(identifiant="belief-1", tenant=TENANT, **champs):
    valeurs = {
        **DATES,
        "id": identifiant,
        "tenant_id": tenant,
        "enonce": "app-cartes · SUPPORTE · capacité-paiement",
        "sujet_id": "twin-app-cartes",
        "confiance": 0.8,
        "source": "RAISONNEMENT",
        "claim_ids": ["claim-1"],
        "revalide_le": "2026-11-01T08:00:00+00:00",
    }
    valeurs.update(champs)
    return modele.Belief(**valeurs)


def dossier(tenant=TENANT):
    return {
        "id": "dossier-1",
        "tenant": tenant,
        "question": "Que sait-on de TBT ?",
        "statut": "reponse",
        "contexte": {"twin_ids": ["twin-app-cartes"], "claim_ids": ["claim-1"]},
        "constats": [
            {"id": "c1", "texte": "TBT dépend de fastapi", "claim_id": "claim-1",
             "twin_id": "twin-app-cartes", "confiance": 0.8},
            {"id": "c2", "texte": "Constat sans claim", "twin_id": "twin-autre"},
        ],
        "beliefs": [
            {"id": "b1", "sujet": "app-cartes", "predicat": "CONSTAT",
             "objet": "TBT dépend de fastapi", "mode": "INFERRED",
             "statut": "CONNU", "confiance": 0.8, "twins": ["twin-app-cartes"]},
            {"id": "b2", "sujet": "x", "predicat": "CONSTAT", "objet": "Hypo",
             "statut": "INCONNU", "confiance": 0.2},
            {"id": "b3", "sujet": "y", "predicat": "CONSTAT",
             "objet": "Constat sans claim", "statut": "SUPPOSE", "confiance": 0.6},
        ],
    }


# --- Modèle : invariants ---

def test_belief_creation_et_invariants():
    b = belief()
    assert (b.type, b.famille, b.mode) == ("BELIEF", "connaissance", "INFERRED")
    assert (b.statut, b.source, b.claim_ids) == ("ACTIF", "RAISONNEMENT", ["claim-1"])
    assert b.revalide_le == "2026-11-01T08:00:00+00:00"
    assert modele.famille_de("BELIEF") == "connaissance"

    with pytest.raises(modele.ModeleInvalide):
        belief(confiance=1.5)
    with pytest.raises(modele.ModeleInvalide):
        belief(enonce="  ")
    with pytest.raises(modele.ModeleInvalide):
        belief(statut="BIZARRE")
    with pytest.raises(modele.ModeleInvalide):
        belief(source="INVENTEE")


def test_belief_raisonnement_sans_claim_refuse():
    # L'invariant central : une inférence sans appui est refusée,
    # un belief de détecteur ou d'humain peut vivre sans claim lié.
    with pytest.raises(modele.ModeleInvalide):
        belief(claim_ids=[])
    assert belief(claim_ids=[], source="DETECTEUR").claim_ids == []
    assert belief(claim_ids=[], source="HUMAIN").claim_ids == []


def test_belief_revalider_et_revoir_domaine():
    b = belief()
    b.revoir("preuve contraire remontée")
    assert (b.statut, b.motif_revision) == ("REVISE", "preuve contraire remontée")
    b.revalider("2026-11-05T10:00:00+00:00")
    assert (b.statut, b.revalide_le) == ("ACTIF", "2026-11-05T10:00:00+00:00")
    with pytest.raises(modele.ModeleInvalide):
        b.revoir("   ")
    caduc = belief("belief-caduc", statut="CADUC")
    with pytest.raises(modele.ModeleInvalide):
        caduc.revalider()
    with pytest.raises(modele.ModeleInvalide):
        caduc.revoir("trop tard")


# --- Confiance effective : érosion par demi-vie ---

def test_confiance_effective_erosion():
    base = {"confiance": 0.8, "statut": "ACTIF",
            "revalide_le": "2026-08-09T12:00:00+00:00"}  # 90 jours avant MAINTENANT
    # À revalide_le : confiance pleine.
    assert beliefs_application.confiance_effective(
        {**base, "revalide_le": "2026-11-07T12:00:00+00:00"}, MAINTENANT,
    ) == pytest.approx(0.8)
    # +90 jours (une demi-vie) : moitié.
    assert beliefs_application.confiance_effective(
        base, MAINTENANT) == pytest.approx(0.4, abs=1e-3)
    # +180 jours : quart.
    assert beliefs_application.confiance_effective(
        {**base, "revalide_le": "2026-05-11T12:00:00+00:00"}, MAINTENANT,
    ) == pytest.approx(0.2, abs=1e-3)
    # REVISE et CADUC : confiance nulle quelle que soit la fraîcheur.
    assert beliefs_application.confiance_effective(
        {**base, "statut": "REVISE"}, MAINTENANT) == 0.0
    assert beliefs_application.confiance_effective(
        {**base, "statut": "CADUC",
         "revalide_le": "2026-11-07T12:00:00+00:00"}, MAINTENANT) == 0.0
    # Demi-vie paramétrable : 45 jours à demi-vie 45 → moitié.
    assert beliefs_application.confiance_effective(
        {**base, "revalide_le": "2026-09-23T12:00:00+00:00"}, MAINTENANT,
        demi_vie_jours=45) == pytest.approx(0.4, abs=1e-3)
    # Jamais au-dessus de la confiance initiale (maintenant < revalide_le).
    assert beliefs_application.confiance_effective(
        {**base, "revalide_le": "2026-12-07T12:00:00+00:00"}, MAINTENANT,
    ) == pytest.approx(0.8)
    # Ligne stockée : les champs vivent dans `donnees`.
    ligne = {"id": "belief-x", "donnees": dict(base)}
    assert beliefs_application.confiance_effective(
        ligne, MAINTENANT) == pytest.approx(0.4, abs=1e-3)
    # Un objet canonique fonctionne aussi.
    assert beliefs_application.confiance_effective(
        belief(revalide_le="2026-08-09T12:00:00+00:00"),
        MAINTENANT) == pytest.approx(0.4, abs=1e-3)


# --- Conversion dossier → objets canoniques ---

def test_beliefs_persistables_lie_les_claims():
    objets = beliefs_application.beliefs_persistables(dossier(), tenant=TENANT)
    # b1 seul est tenu (CONNU) et ancré à un constat citant un claim ;
    # b2 est INCONNU, b3 n'a pas de claim résoluble.
    assert len(objets) == 1
    b = objets[0]
    assert isinstance(b, modele.Belief)
    assert (b.type, b.famille, b.source, b.statut) == (
        "BELIEF", "connaissance", "RAISONNEMENT", "ACTIF")
    assert b.claim_ids == ["claim-1"]
    assert b.sujet_id == "twin-app-cartes"
    assert b.dossier_id == "dossier-1"
    assert b.enonce.startswith("app-cartes")
    assert b.confiance == pytest.approx(0.8)
    # Identifiant déterministe : rejouer le dossier ne duplique pas.
    autre = beliefs_application.beliefs_persistables(dossier(), tenant=TENANT)
    assert [o.id for o in autre] == [b.id]


def test_beliefs_persistables_dossier_vide_ou_sans_appui():
    assert beliefs_application.beliefs_persistables({}) == []
    assert beliefs_application.beliefs_persistables(None) == []
    sans_claims = {**dossier(), "constats": []}
    assert beliefs_application.beliefs_persistables(sans_claims) == []


# --- Persistance Postgres (objet_entreprise + trigger) ---

@besoin_pg
def test_belief_persiste_et_relu(conn):
    objet = boucle.Belief(
        id="belief-p1", tenant_id=TENANT,
        enonce="app-cartes · SUPPORTE · paiement", sujet_id="twin-app-cartes",
        confiance=0.7, claim_ids=["claim-9"], dossier_id="dossier-9")
    ligne = boucle.enregistrer_boucle(conn, TENANT, objet)
    assert (ligne["type"], ligne["famille"], ligne["mode"]) == (
        "BELIEF", "connaissance", "INFERRED")
    donnees = ligne["donnees"]
    assert donnees["statut"] == "ACTIF"
    assert donnees["claim_ids"] == ["claim-9"]
    assert donnees["enonce"].startswith("app-cartes")
    assert donnees["revalide_le"]

    relu = boucle.lire_boucle(conn, TENANT, "belief-p1")
    assert relu["donnees"]["dossier_id"] == "dossier-9"
    canonique = boucle.lire_boucle(conn, TENANT, "belief-p1", as_dict=False)
    assert isinstance(canonique, boucle.Belief) and canonique.statut == "ACTIF"
    # La ligne stockée alimente directement la confiance effective.
    assert beliefs_application.confiance_effective(relu, MAINTENANT) > 0


@besoin_pg
def test_enregistrer_refuse_belief_invalide(conn):
    brut = {"id": "belief-brut", "tenant_id": TENANT, "type": "BELIEF",
            "famille": "connaissance", "mode": "INFERRED",
            "donnees": {"enonce": "sans appui", "statut": "ACTIF",
                        "source": "RAISONNEMENT"}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, brut)
    assert boucle.lire_boucle(conn, TENANT, "belief-brut") is None

    statut_inconnu = {"id": "belief-statut", "tenant_id": TENANT, "type": "BELIEF",
                      "famille": "connaissance", "mode": "INFERRED",
                      "donnees": {"enonce": "e", "statut": "DORMANT",
                                  "source": "DETECTEUR"}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, statut_inconnu)


@besoin_pg
def test_trigger_belief_exige_appui(conn):
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
            "VALUES ('belief-bad', %s, 'connaissance', 'BELIEF', 'INFERRED', "
            "'{\"enonce\": \"e\", \"statut\": \"ACTIF\", \"source\": \"RAISONNEMENT\"}'::jsonb)",
            (TENANT,))
    # Un belief DETECTEUR sans claim passe le trigger.
    conn.execute(
        "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
        "VALUES ('belief-ok', %s, 'connaissance', 'BELIEF', 'INFERRED', "
        "'{\"enonce\": \"e\", \"statut\": \"ACTIF\", \"source\": \"DETECTEUR\"}'::jsonb)",
        (TENANT,))
    assert boucle.lire_boucle(conn, TENANT, "belief-ok")["type"] == "BELIEF"


@besoin_pg
def test_revalider_et_revoir_persistes(conn):
    boucle.enregistrer_boucle(conn, TENANT, boucle.Belief(
        id="belief-t1", tenant_id=TENANT, enonce="conclusion mesurée",
        confiance=0.9, claim_ids=["claim-1"]))

    ligne = boucle.revoir(conn, TENANT, "belief-t1", "preuve contraire",
                          acteur="relecteur-1")
    assert ligne["donnees"]["statut"] == "REVISE"
    assert ligne["donnees"]["motif_revision"] == "preuve contraire"
    assert beliefs_application.confiance_effective(ligne) == 0.0

    with pytest.raises(boucle.BoucleInvalide):
        boucle.revoir(conn, TENANT, "belief-t1", "   ")

    ligne = boucle.revalider(conn, TENANT, "belief-t1", acteur="rev-1")
    assert ligne["donnees"]["statut"] == "ACTIF"
    assert ligne["donnees"]["revalide_par"] == "rev-1"
    assert ligne["version"] == 3
    assert beliefs_application.confiance_effective(ligne) == pytest.approx(0.9)

    # L'historique conserve les versions précédentes (audit).
    assert len(ligne.get("historique") or ()) == 2

    with pytest.raises(boucle.BoucleInvalide):
        boucle.revalider(conn, TENANT, "belief-inconnu")

    # Un belief CADUC ne revient pas : ni revalidation ni révision.
    ligne = boucle.lire_boucle(conn, TENANT, "belief-t1")
    boucle.enregistrer_boucle(
        conn, TENANT, {**ligne, "donnees": {**ligne["donnees"], "statut": "CADUC"}})
    with pytest.raises(boucle.BoucleInvalide):
        boucle.revalider(conn, TENANT, "belief-t1")
    with pytest.raises(boucle.BoucleInvalide):
        boucle.revoir(conn, TENANT, "belief-t1", "trop tard")


@besoin_pg
def test_ecriture_dossier_persiste_les_conclusions(conn):
    ids = dossiers_raisonnement.enregistrer_beliefs(conn, TENANT, dossier())
    assert len(ids) == 1
    ligne = boucle.lire_boucle(conn, TENANT, ids[0])
    assert ligne["type"] == "BELIEF"
    assert ligne["donnees"]["claim_ids"] == ["claim-1"]
    assert ligne["donnees"]["statut"] == "ACTIF"

    # Le même point d'entrée sert la voie canonique : `enregistrer` du dossier
    # persiste les beliefs dans la même transaction, sans casser l'upsert.
    identifiant = dossiers_raisonnement.enregistrer(conn, TENANT, dossier())
    assert identifiant == "dossier-1"

    # Rejouer le dossier met à jour le même belief (id déterministe).
    ids_bis = dossiers_raisonnement.enregistrer_beliefs(conn, TENANT, dossier())
    assert ids_bis == ids
    relu = boucle.lire_boucle(conn, TENANT, ids[0])
    assert relu["version"] >= 2
