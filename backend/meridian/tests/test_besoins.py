"""Objets B6 : NEED, UNKNOWN, HYPOTHESIS — invariants, transitions et persistance."""
import psycopg
import pytest

from meridian.adapters.outbound.postgres import boucle
from meridian.domain import modele_entreprise as modele
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
DATES = {
    "cree_le": "2026-10-01T08:00:00+00:00",
    "observe_le": "2026-10-02T09:00:00+00:00",
    "valide_depuis": "2026-10-02T09:00:00+00:00",
}


def besoin(identifiant="need-1", tenant=TENANT, **champs):
    valeurs = {
        **DATES,
        "id": identifiant,
        "tenant_id": tenant,
        "porteur": "equipe-cartes",
        "exigence": "délai de traitement < 5 jours",
        "ecart": "12 jours observés",
        "signature": "contournement",
        "refutable_par": "un délai mesuré sous 5 jours sur 30 jours glissants",
        "claim_ids": ["claim-delai"],
    }
    valeurs.update(champs)
    return boucle.Need(**valeurs)


def unknown(identifiant="unk-1", tenant=TENANT, **champs):
    valeurs = {
        **DATES,
        "id": identifiant,
        "tenant_id": tenant,
        "question": "Qui consomme l'interface TBT en dehors des horaires ?",
        "bloque": "impossible de trancher la décommission",
        "origine": "flore",
        "tentatives": ["consultation des logs OTLP"],
    }
    valeurs.update(champs)
    return boucle.Unknown(**valeurs)


def hypothese(identifiant="hyp-1", tenant=TENANT, **champs):
    valeurs = {**DATES, "id": identifiant, "tenant_id": tenant,
               "enonce": "Le délai vient de la revue manuelle"}
    valeurs.update(champs)
    return boucle.Hypothesis(**valeurs)


# --- NEED : refutable_par obligatoire ---

def test_need_sans_refutable_par_rejete():
    with pytest.raises(modele.ModeleInvalide):
        boucle.Need(id="need-vide", tenant_id=TENANT, porteur="equipe", **DATES)


def test_need_statut_avance_sans_porteur_rejete():
    with pytest.raises(modele.ModeleInvalide):
        besoin(statut="QUALIFIE", porteur="")
    with pytest.raises(modele.ModeleInvalide):
        besoin(statut="CORROBORE", porteur="")


def test_need_statut_inconnu_rejete():
    with pytest.raises(modele.ModeleInvalide):
        besoin(statut="BANCO")


# --- HYPOTHESIS : rivale exigée ---

def test_hypothesis_testee_ou_retenue_sans_rivale_rejetee():
    for statut in ("TESTEE", "RETENUE"):
        with pytest.raises(modele.ModeleInvalide):
            hypothese(statut=statut)
        with pytest.raises(modele.ModeleInvalide):
            hypothese(statut=statut, rival_ids=[])
    emise = hypothese(statut="EMISE")
    assert emise.statut == "EMISE" and emise.rival_ids == []
    testee = hypothese(statut="TESTEE", rival_ids=["hyp-2"],
                       preuve_discriminante="mesurer le délai avec revue sautée")
    assert testee.rival_ids == ["hyp-2"]


def test_hypothesis_sans_enonce_rejetee():
    with pytest.raises(modele.ModeleInvalide):
        boucle.Hypothesis(id="hyp-vide", tenant_id=TENANT, **DATES)


# --- UNKNOWN ---

def test_unknown_statuts_et_question_obligatoire():
    with pytest.raises(modele.ModeleInvalide):
        boucle.Unknown(id="unk-vide", tenant_id=TENANT, **DATES)
    with pytest.raises(modele.ModeleInvalide):
        unknown(statut="PRESQUE")
    inconnu = unknown(statut="en_cours")
    assert (inconnu.statut, inconnu.famille, inconnu.type) == (
        "EN_COURS", "connaissance", "UNKNOWN")
    assert inconnu.tentatives == ["consultation des logs OTLP"]


# --- TRANSITIONS_NEED ---

def test_transitions_need_chemin_heureux():
    n = besoin()
    assert n.statut == "OUVERT"
    qualifie = boucle.transiter_need(n, "QUALIFIE")
    assert qualifie.statut == "QUALIFIE" and n.statut == "OUVERT"  # source non muté
    corrobore = boucle.transiter_need(qualifie, "CORROBORE")
    assert corrobore.statut == "CORROBORE"
    adresse = boucle.transiter_need(corrobore, "ADRESSE")
    assert adresse.statut == "ADRESSE"


def test_transitions_need_invalides():
    n = besoin()
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(n, "ADRESSE")       # raccourci interdit
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(n, "CORROBORE")     # saute QUALIFIE
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(n, "TRUC")          # statut inconnu


def test_transition_qualifie_exige_porteur_exigence_ecart_claim():
    nu = besoin(porteur="")
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(nu, "QUALIFIE")
    sans_claim = besoin(claim_ids=[])
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(sans_claim, "QUALIFIE")
    # le porteur peut être fourni au moment de la transition
    complete = boucle.transiter_need(nu, "QUALIFIE", porteur="equipe-cartes")
    assert (complete.statut, complete.porteur) == ("QUALIFIE", "equipe-cartes")


def test_reouverture_exige_un_motif_et_versionne():
    refute = boucle.transiter_need(besoin(), "REFUTE")
    assert refute.statut == "REFUTE"
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(refute, "OUVERT")
    rouvert = boucle.transiter_need(refute, "OUVERT", motif="signal contradictoire")
    assert (rouvert.statut, rouvert.version) == ("OUVERT", refute.version + 1)
    assert rouvert.motif_reouverture == "signal contradictoire"

    perime = boucle.transiter_need(besoin(), "PERIME")
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(perime, "OUVERT", motif="   ")


def test_transiter_need_tenant_mismatch():
    with pytest.raises(boucle.BoucleInvalide):
        boucle.transiter_need(besoin(), "QUALIFIE", tenant_id="assurance")


# --- Persistance Postgres (dépôt + trigger) ---

@besoin_pg
def test_persistance_need_unknown_hypothesis(conn):
    n, u, h = besoin(), unknown(), hypothese(rival_ids=["hyp-2"])
    stocke = boucle.enregistrer_boucle(conn, TENANT, [n, u, h])
    assert {o["type"] for o in stocke} == {"NEED", "UNKNOWN", "HYPOTHESIS"}

    relu = boucle.lire_boucle(conn, TENANT, n.id)
    assert relu["type"] == "NEED"
    assert relu["donnees"]["refutable_par"] == n.refutable_par
    canonique = boucle.lire_boucle(conn, TENANT, n.id, as_dict=False)
    assert isinstance(canonique, boucle.Need) and canonique.statut == "OUVERT"

    transition = boucle.transiter_need(canonique, "QUALIFIE")
    boucle.enregistrer_boucle(conn, TENANT, transition)
    assert boucle.lire_boucle(conn, TENANT, n.id)["donnees"]["statut"] == "QUALIFIE"


@besoin_pg
def test_enregistrer_refuse_need_et_hypothesis_invalides(conn):
    brut = {"id": "need-brut", "tenant_id": TENANT, "type": "NEED",
            "famille": "emergence", "mode": "PROPOSED", "donnees": {"statut": "OUVERT"}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, brut)

    brut_qualifie = {**brut, "id": "need-qualifie",
                     "donnees": {"statut": "QUALIFIE", "refutable_par": "obs"}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, brut_qualifie)

    hyp = {"id": "hyp-brute", "tenant_id": TENANT, "type": "HYPOTHESIS",
           "famille": "investigation", "mode": "PROPOSED",
           "donnees": {"enonce": "e", "statut": "RETENUE"}}
    with pytest.raises(boucle.BoucleInvalide):
        boucle.enregistrer_boucle(conn, TENANT, hyp)
    assert boucle.lire_boucle(conn, TENANT, "need-brut") is None


@besoin_pg
def test_trigger_need_exige_refutation(conn):
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
            "VALUES ('need-bad', %s, 'emergence', 'NEED', 'PROPOSED', "
            "'{\"statut\": \"OUVERT\"}'::jsonb)", (TENANT,))
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
            "VALUES ('need-bad2', %s, 'emergence', 'NEED', 'CONFIRMED', "
            "'{\"statut\": \"OUVERT\", \"refutable_par\": \"   \"}'::jsonb)", (TENANT,))


@besoin_pg
def test_trigger_need_statut_avance_exige_porteur(conn):
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
            "VALUES ('need-qual', %s, 'emergence', 'NEED', 'DECLARED', "
            "'{\"statut\": \"QUALIFIE\", \"refutable_par\": \"obs\"}'::jsonb)", (TENANT,))
    # un NEED DECLARED sans statut avancé passe le trigger
    conn.execute(
        "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, donnees) "
        "VALUES ('need-ok', %s, 'emergence', 'NEED', 'DECLARED', "
        "'{\"statut\": \"OUVERT\"}'::jsonb)", (TENANT,))
    assert boucle.lire_boucle(conn, TENANT, "need-ok")["type"] == "NEED"
