"""Twins non applicatifs : création idempotente, lecture, liste et Claims prouvés attachés."""
import pytest

from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import twins_types
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"
PROCESS_ID = "process-cartes"
PROCESS_NOM = "Traiter une demande de carte"


def creer_process(conn, twin_id=PROCESS_ID, nom=PROCESS_NOM, tenant=TENANT, acteur="alice"):
    return twins_types.creer_twin(
        conn, tenant, twin_id, "PROCESS", nom,
        mission="Instruire une demande de carte", domaine="cartes", acteur=acteur)


def test_type_inconnu_et_acteur_vide_refuses_sans_base():
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(None, TENANT, PROCESS_ID, "MAGIQUE", PROCESS_NOM, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(None, TENANT, PROCESS_ID, "PROCESS", PROCESS_NOM, acteur=" ")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(None, " ", PROCESS_ID, "PROCESS", PROCESS_NOM, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(None, TENANT, " ", "PROCESS", PROCESS_NOM, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(None, TENANT, PROCESS_ID, "PROCESS", " ", acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(
            None, TENANT, PROCESS_ID, "PROCESS", PROCESS_NOM,
            mission="https://alice:s3cr3t@example.test", acteur="alice")


def test_lister_refuse_type_et_limite_invalides_sans_base():
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.lister_twins(None, TENANT, type_twin="MAGIQUE")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.lister_twins(None, TENANT, limite=True)


def test_claim_invalide_refuse_sans_base():
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            None, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", mode="MAGIQUE", acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            None, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve=None, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            None, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", confiance=1.5, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            None, TENANT, PROCESS_ID, " ", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", acteur="alice")


@besoin_pg
def test_creation_lecture_liste_et_audit_des_twins_non_applicatifs(conn):
    process = twins_types.creer_twin(
        conn, TENANT, PROCESS_ID, "PROCESS", PROCESS_NOM, mission="Instruire une demande",
        domaine="cartes", equipe="equipe-cartes", acteur="alice",
        preuve={"motif": "création validée en revue"})
    capacite = twins_types.creer_twin(
        conn, TENANT, "cap-cartes", "CAPABILITY", "Délivrer une carte", acteur="alice")
    parcours = twins_types.creer_twin(
        conn, TENANT, "parcours-carte", "JOURNEY", "Demander une carte", acteur="bob")

    assert (process["id"], process["type"], process["nom"], process["mission"]) == (
        PROCESS_ID, "PROCESS", PROCESS_NOM, "Instruire une demande")
    assert process["equipe"] == "equipe-cartes" and process["domaine"] == "cartes"
    assert capacite["domaine"] == "À confirmer" and capacite["equipe"] == "à confirmer"
    assert parcours["type"] == "JOURNEY"
    assert twins_types.lire_twin(conn, TENANT, PROCESS_ID) == process
    assert twins_types.lire_twin(conn, TENANT, "absent") is None

    assert [t["id"] for t in twins_types.lister_twins(conn, TENANT, type_twin="CAPABILITY")] == [
        "cap-cartes"]
    assert {t["id"] for t in twins_types.lister_twins(conn, TENANT)} == {
        PROCESS_ID, "cap-cartes", "parcours-carte"}
    assert len(twins_types.lister_twins(conn, TENANT, limite=1)) == 1

    decisions = conn.execute(
        "SELECT action, acteur, avant, apres, preuve FROM identity_decision ORDER BY id").fetchall()
    assert len(decisions) == 3
    assert {d[0] for d in decisions} == {"creation_twin"}
    assert [d[1] for d in decisions] == ["alice", "alice", "bob"]
    assert all(d[2] == {} for d in decisions)
    assert decisions[0][3]["id"] == PROCESS_ID
    assert decisions[0][4] == {"motif": "création validée en revue"}


@besoin_pg
def test_creation_dupliquee_est_idempotente_et_preserve_identite(conn):
    premier = creer_process(conn)
    second = twins_types.creer_twin(
        conn, TENANT, PROCESS_ID, "process", "Autre nom", mission="Autre mission",
        domaine="autre", acteur="bob")

    assert second == premier
    assert conn.execute("SELECT count(*) FROM jumeau WHERE id = %s", (PROCESS_ID,)).fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 1


@besoin_pg
def test_changement_de_type_refuse_pour_un_twin_existant(conn):
    creer_process(conn)

    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(
            conn, TENANT, PROCESS_ID, "CAPABILITY", "Délivrer une carte", acteur="alice")

    assert twins_types.lire_twin(conn, TENANT, PROCESS_ID)["type"] == "PROCESS"
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 1


@besoin_pg
def test_cross_tenant_refuse_sans_ecriture(conn):
    creer_process(conn)

    with pytest.raises(PermissionError):
        twins_types.creer_twin(
            conn, AUTRE_TENANT, PROCESS_ID, "PROCESS", "Traiter autrement", acteur="bob")

    assert twins_types.lire_twin(conn, AUTRE_TENANT, PROCESS_ID) is None
    assert twins_types.lister_twins(conn, AUTRE_TENANT) == []
    assert twins_types.lire_twin(conn, TENANT, PROCESS_ID)["nom"] == PROCESS_NOM
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 1


@besoin_pg
def test_claim_attache_au_twin_avec_preuve_et_mode(conn):
    creer_process(conn)
    capacite = twins_types.creer_twin(
        conn, TENANT, "cap-cartes", "CAPABILITY", "Délivrer une carte", acteur="alice")
    assert capacite["type"] == "CAPABILITY"

    claim = twins_types.creer_claim(
        conn, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
        source={"type": "DOCUMENTATION", "nom": "referentiel-cartes",
                "emplacement": "docs/cartes.md"},
        preuve={"locator": "docs/cartes.md#L10-L12", "chemin": "docs/cartes.md",
                "sha": "abc123", "ligne_debut": 10, "ligne_fin": 12, "hash": "h"},
        mode="OBSERVED", confiance=0.7, acteur="alice",
        texte="La carte est délivrée par ce processus.")

    assert claim["twin_id"] == PROCESS_ID and claim["sujet"] == PROCESS_NOM
    assert (claim["predicat"], claim["objet"], claim["type"]) == (
        "REALISE_CAPACITE", "cap-cartes", "CLAIM")
    assert claim["mode"] == "OBSERVED" and claim["confiance"] == pytest.approx(0.7)
    assert claim["statut"] == "PROPOSED" and claim["origine"] == "CONVERSATION"
    assert claim["texte"] == "La carte est délivrée par ce processus."
    assert [p["locator"] for p in claim["preuves"]] == ["docs/cartes.md#L10-L12"]
    assert claim["preuves"][0]["role"] == "SUPPORT"

    lus = twins_types.claims_du_twin(conn, TENANT, PROCESS_ID)
    assert [c["id"] for c in lus] == [claim["id"]]
    assert twins_types.claims_du_twin(conn, TENANT, "cap-cartes") == []
    assert conn.execute(
        "SELECT tenant_id, jumeau_id, mode FROM claim WHERE id = %s",
        (claim["id"],)).fetchone() == (TENANT, PROCESS_ID, "OBSERVED")


@besoin_pg
def test_claim_refuse_cible_absente_autre_tenant_ou_sans_preuve(conn):
    creer_process(conn)

    with pytest.raises(twins_types.TwinIntrouvable):
        twins_types.creer_claim(
            conn, TENANT, "absent", "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", acteur="alice")
    with pytest.raises(twins_types.TwinIntrouvable):
        twins_types.creer_claim(
            conn, AUTRE_TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            conn, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve=None, acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            conn, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="referentiel", preuve="docs/cartes.md#L1", mode="MAGIQUE", acteur="alice")

    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM source").fetchone()[0] == 0


@besoin_pg
def test_claim_avec_source_textuelle_cree_une_preuve_immuable(conn):
    creer_process(conn)

    claim = twins_types.creer_claim(
        conn, TENANT, PROCESS_ID, "SERT_ACTEUR", "les conseillers",
        source="note de cadrage", preuve="Les conseillers instruisent la demande.",
        acteur="alice")

    assert claim["statut"] == "PROPOSED" and claim["mode"] == "DECLARED"
    assert claim["preuves"][0]["locator"].startswith("declaration://note de cadrage/")
    assert claim["texte"] == "Les conseillers instruisent la demande."
    assert conn.execute("SELECT type, nom FROM source").fetchone() == ("DOCUMENTATION", "note de cadrage")
    with pytest.raises(Exception):
        conn.execute("UPDATE preuve SET hash = 'autre' WHERE id = %s", (claim["preuves"][0]["id"],))


@besoin_pg
def test_preuve_avec_locator_git_acceptee_et_lignes_invalides_refusees(conn):
    creer_process(conn)

    claim = twins_types.creer_claim(
        conn, TENANT, PROCESS_ID, "DEPEND_DE", "referentiel",
        source={"type": "GIT", "nom": "referentiel", "emplacement": "/depots/referentiel",
                "curseur": "abc123"},
        preuve={"locator": "git://referentiel@abc123:docs/cartes.md#L10-L12",
                "chemin": "docs/cartes.md", "sha": "abc123", "ligne_debut": 10,
                "ligne_fin": 12, "hash": "h"},
        acteur="alice")

    assert claim["preuves"][0]["locator"] == "git://referentiel@abc123:docs/cartes.md#L10-L12"
    assert (claim["preuves"][0]["ligne_debut"], claim["preuves"][0]["ligne_fin"]) == (10, 12)

    textuel = twins_types.creer_claim(
        conn, TENANT, PROCESS_ID, "DEPEND_DE", "autre",
        source="referentiel", preuve="docs/cartes.md#L3-L4", acteur="alice")
    assert textuel["preuves"][0]["locator"] == "docs/cartes.md#L3-L4"
    assert (textuel["preuves"][0]["ligne_debut"], textuel["preuves"][0]["ligne_fin"]) == (3, 4)

    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            conn, TENANT, PROCESS_ID, "DEPEND_DE", "encore",
            source="referentiel", preuve={"locator": "docs/cartes.md#L0", "ligne_debut": 0},
            acteur="alice")
    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 2


@besoin_pg
def test_source_avec_secret_refusee_sans_ecriture(conn):
    creer_process(conn)

    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            conn, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source={"nom": "doc", "emplacement": "https://alice:s3cr3t@example.test/cartes"},
            preuve="docs/cartes.md#L1", acteur="alice")
    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_claim(
            conn, TENANT, PROCESS_ID, "REALISE_CAPACITE", "cap-cartes",
            source="doc", preuve={"locator": "docs/cartes.md#L1", "token": "abc123"},
            acteur="alice")

    assert conn.execute("SELECT count(*) FROM claim").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM source").fetchone()[0] == 0


@besoin_pg
def test_application_existante_n_est_jamais_transformee(conn):
    depot.creer_jumeau(conn, {
        "id": "app-cartes", "tenant_id": TENANT, "nom": "Cartes", "equipe": "equipe-cartes"})

    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(
            conn, TENANT, "app-cartes", "PROCESS", "Cartes", acteur="alice")

    assert twins_types.lire_twin(conn, TENANT, "app-cartes")["type"] == "APPLICATION"
    assert conn.execute("SELECT count(*) FROM identity_decision").fetchone()[0] == 0


@besoin_pg
def test_application_autorisee_seulement_si_absente(conn):
    application = twins_types.creer_twin(
        conn, TENANT, "app-nouvelle", "APPLICATION", "Nouvelle application", acteur="alice")
    assert application["type"] == "APPLICATION"

    with pytest.raises(twins_types.TwinInvalide):
        twins_types.creer_twin(
            conn, TENANT, "app-nouvelle", "PROCESS", "Nouvelle application", acteur="alice")

    assert twins_types.lire_twin(conn, TENANT, "app-nouvelle")["type"] == "APPLICATION"
