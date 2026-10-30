"""Promotion humaine d'un twin provisoire : identité inchangée, audit écrit, refus explicites."""
import pytest

from jumeau import depot, identite, identite_depot
from jumeau.tests.conftest import ACTIVITE, besoin_pg, claim

TENANT = "banque"
JID = "nouveau-jumeau"
PROVISOIRE = {"id": JID, "tenant_id": TENANT, "nom": "Nouveau jumeau", "equipe": "equipe-gsf",
              "mission": "dfggg"}
SOURCE = {"nom": "gsf-mockup", "type": "GIT", "emplacement": "/depots/gsf-mockup", "curseur": "sha1"}
NOM, MISSION = "GSF Mockup", "Sert de banc d'essai aux interfaces de publication"


def preparer(conn):
    depot.enregistrer(conn, PROVISOIRE, SOURCE, [claim("motor")], ACTIVITE)


@besoin_pg
def test_promotion_met_a_jour_identite_et_laisse_une_decision_auditee(conn):
    preparer(conn)
    sources_avant = conn.execute(
        "SELECT id, nom, emplacement, curseur FROM source WHERE jumeau_id = %s ORDER BY id", (JID,)).fetchall()
    claims_avant = conn.execute(
        "SELECT id, predicat, objet, statut, confiance FROM claim WHERE jumeau_id = %s ORDER BY id", (JID,)).fetchall()

    resultat = identite_depot.promouvoir(
        conn, TENANT, JID, NOM, MISSION, "alice", preuve={"motif": "identité validée en revue"})

    assert resultat == {
        "jumeau_id": JID, "nom": NOM, "mission": MISSION, "statut": "actif",
        "avant": {"nom": "Nouveau jumeau", "mission": "dfggg"},
        "apres": {"nom": NOM, "mission": MISSION},
    }
    assert conn.execute("SELECT id, tenant_id, nom, mission FROM jumeau WHERE id = %s",
                        (JID,)).fetchone() == (JID, TENANT, NOM, MISSION)
    assert conn.execute("SELECT id, nom, emplacement, curseur FROM source WHERE jumeau_id = %s ORDER BY id",
                        (JID,)).fetchall() == sources_avant
    assert conn.execute("SELECT id, predicat, objet, statut, confiance FROM claim WHERE jumeau_id = %s "
                        "ORDER BY id", (JID,)).fetchall() == claims_avant

    decision = conn.execute(
        "SELECT tenant_id, jumeau_id, acteur, action, avant, apres, preuve, cree_le FROM identity_decision"
    ).fetchone()
    assert decision[:4] == (TENANT, JID, "alice", "promotion")
    assert decision[4] == {"nom": "Nouveau jumeau", "mission": "dfggg"}
    assert decision[5] == {"nom": NOM, "mission": MISSION}
    assert decision[6] == {"motif": "identité validée en revue"}
    assert decision[7] is not None


@besoin_pg
def test_deuxieme_promotion_refusee_sans_nouvelle_decision(conn):
    preparer(conn)
    identite_depot.promouvoir(conn, TENANT, JID, NOM, MISSION, "alice")

    with pytest.raises(identite_depot.JumeauDejaCanonique):
        identite_depot.promouvoir(conn, TENANT, JID, "Autre nom", "Autre mission", "bob")

    assert conn.execute("SELECT nom, mission FROM jumeau WHERE id = %s", (JID,)).fetchone() == (NOM, MISSION)
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 1


@besoin_pg
def test_tenant_mismatch_refuse_sans_ecriture(conn):
    preparer(conn)

    with pytest.raises(PermissionError):
        identite_depot.promouvoir(conn, "assurance", JID, NOM, MISSION, "alice")

    assert conn.execute("SELECT nom, mission FROM jumeau WHERE id = %s", (JID,)).fetchone() == (
        "Nouveau jumeau", "dfggg")
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 0


@besoin_pg
def test_jumeau_introuvable_refuse(conn):
    with pytest.raises(LookupError):
        identite_depot.promouvoir(conn, TENANT, "absent", NOM, MISSION, "alice")
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 0


@besoin_pg
@pytest.mark.parametrize("nom,mission", [
    ("Nouveau jumeau", MISSION),
    ("nouveau-jumeau", MISSION),
    ("GSF Mockup", "dfggg"),
    ("GSF Mockup", "à confirmer"),
    ("dfggg", MISSION),
    ("", MISSION),
    ("GSF Mockup", "   "),
])
def test_nom_ou_mission_placeholder_refuses(conn, nom, mission):
    preparer(conn)

    with pytest.raises(identite_depot.PromotionRefusee):
        identite_depot.promouvoir(conn, TENANT, JID, nom, mission, "alice")

    assert conn.execute("SELECT nom, mission FROM jumeau WHERE id = %s", (JID,)).fetchone() == (
        "Nouveau jumeau", "dfggg")
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 0


def test_tenant_jumeau_et_acteur_vides_refuses_sans_base():
    with pytest.raises(identite_depot.PromotionRefusee):
        identite_depot.promouvoir(None, " ", JID, NOM, MISSION, "alice")
    with pytest.raises(identite_depot.PromotionRefusee):
        identite_depot.promouvoir(None, TENANT, " ", NOM, MISSION, "alice")
    with pytest.raises(identite_depot.PromotionRefusee):
        identite_depot.promouvoir(None, TENANT, JID, NOM, MISSION, " ")


def test_est_provisoire_distingue_provisoire_et_canonique():
    provisoire, raisons = identite.est_provisoire(
        {"id": JID, "nom": "Nouveau jumeau", "mission": "dfggg", "statut": "actif"})
    assert provisoire is True and raisons
    assert identite.est_provisoire({"nom": "Nouveau jumeau", "mission": MISSION, "statut": "actif"})[0] is True
    assert identite.est_provisoire({"nom": NOM, "mission": "dfggg", "statut": "actif"})[0] is True

    canonique, raisons = identite.est_provisoire(
        {"id": "conduit", "nom": "Conduit", "mission": "Publie et organise les articles", "statut": "actif"})
    assert canonique is False and raisons == []
