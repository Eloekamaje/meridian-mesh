"""Socle d'entreprise P0-A : objets typés, versionnés, tenant-scopés et sans secret."""
import pytest

from jumeau import depot, entreprise_depot
from jumeau.tests.conftest import besoin_pg

TENANT = "banque"
PROCESS = {
    "id": "tbt-process",
    "famille": "identite_structure",
    "type": "PROCESS",
    "mode": "DECLARED",
    "titre": "Traiter une demande de carte",
    "donnees": {"etapes": ["recevoir", "instruire", "décider"], "proprietaire": "équipe-cartes"},
}
SITUATION = {
    "id": "sit-cartes",
    "famille": "emergence",
    "type": "SITUATION",
    "mode": "OBSERVED",
    "titre": "Délai de traitement en hausse",
    "donnees": {"twin_ids": [PROCESS["id"]], "priorite": "HAUTE"},
}


@besoin_pg
def test_creer_et_lire_un_twin_process_et_une_situation(conn):
    process = entreprise_depot.enregistrer_objet(conn, TENANT, PROCESS)
    situation = entreprise_depot.enregistrer_objet(conn, TENANT, SITUATION)

    assert (process["id"], process["famille"], process["type"], process["mode"]) == (
        "tbt-process", "identite_structure", "PROCESS", "DECLARED")
    assert process["version"] == 1 and process["titre"] == PROCESS["titre"]
    assert process["donnees"] == PROCESS["donnees"]
    assert (situation["id"], situation["famille"], situation["type"]) == (
        "sit-cartes", "emergence", "SITUATION")

    lu = entreprise_depot.lire_objet(conn, TENANT, PROCESS["id"])
    assert lu["donnees"] == PROCESS["donnees"]
    assert lu["cree_le"] and lu["maj_le"] and lu["observe_le"] and lu["valide_depuis"]
    assert entreprise_depot.lire_objet(conn, TENANT, "absent") is None


@besoin_pg
def test_objets_du_modele_pur_sont_acceptes(conn):
    from jumeau.modele_entreprise import Situation, Twin

    temps = {"cree_le": "2026-10-30T09:00:00+00:00", "observe_le": "2026-10-30T09:00:00+00:00",
             "valide_depuis": "2026-10-30T09:00:00+00:00"}
    twin = Twin(id="twin-process", tenant_id=TENANT, type="PROCESS", nom="Parcours carte",
                mission="Instruire une demande de carte", **temps)
    situation = Situation(id="sit-modele", tenant_id=TENANT, titre="Délai en hausse",
                          description="Le délai dépasse la cible", **temps)

    process = entreprise_depot.enregistrer_objet(conn, TENANT, twin)
    sit = entreprise_depot.enregistrer_objet(conn, TENANT, situation)

    assert (process["type"], process["mode"]) == ("PROCESS", "DECLARED")
    assert process["donnees"]["nom"] == "Parcours carte"
    assert (sit["type"], sit["mode"], sit["titre"]) == ("SITUATION", "DECLARED", "Délai en hausse")
    assert sit["donnees"]["description"] == "Le délai dépasse la cible"


@besoin_pg
def test_deux_tenants_sont_isoles(conn):
    entreprise_depot.enregistrer_objet(conn, "banque", {**PROCESS, "donnees": {"tenant": "banque"}})
    entreprise_depot.enregistrer_objet(conn, "assurance", {**PROCESS, "donnees": {"tenant": "assurance"}})

    assert entreprise_depot.lire_objet(conn, "banque", PROCESS["id"])["donnees"] == {"tenant": "banque"}
    assert entreprise_depot.lire_objet(conn, "assurance", PROCESS["id"])["donnees"] == {"tenant": "assurance"}
    assert [o["donnees"] for o in entreprise_depot.lister_objets(conn, "banque")] == [{"tenant": "banque"}]
    assert [o["donnees"] for o in entreprise_depot.lister_objets(conn, "assurance")] == [{"tenant": "assurance"}]


@besoin_pg
def test_version_croissante_et_downgrade_refuse(conn):
    cree = entreprise_depot.enregistrer_objet(conn, TENANT, PROCESS)
    assert cree["version"] == 1

    monte = entreprise_depot.enregistrer_objet(
        conn, TENANT, {**PROCESS, "version": 2, "titre": "Traiter une demande de carte (v2)"})
    assert monte["version"] == 2 and monte["titre"].endswith("(v2)")

    with pytest.raises(entreprise_depot.VersionRefusee):
        entreprise_depot.enregistrer_objet(conn, TENANT, {**PROCESS, "version": 1})
    assert entreprise_depot.lire_objet(conn, TENANT, PROCESS["id"])["version"] == 2

    auto = entreprise_depot.enregistrer_objet(conn, TENANT, {**PROCESS, "titre": "Encore"})
    assert auto["version"] == 3 and auto["titre"] == "Encore"


@besoin_pg
@pytest.mark.parametrize("changement", [
    {"famille": "famille_inconnue"},
    {"mode": "MAGIQUE"},
    {"type": "TYPE_INCONNU"},
    {"famille": "identite_structure", "type": "SITUATION"},
])
def test_famille_mode_type_invalides_refuses(conn, changement):
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(conn, TENANT, {**PROCESS, **changement})
    assert entreprise_depot.lister_objets(conn, TENANT) == []


@besoin_pg
def test_donnees_json_strictes_et_sans_secret(conn):
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(conn, TENANT, {**PROCESS, "donnees": {"objet": object()}})
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(conn, TENANT, {**PROCESS, "donnees": {"password": "hunter2"}})
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(
            conn, TENANT, {**PROCESS, "donnees": {"url": "https://alice:s3cr3t@api.example.test"}})
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(
            conn, TENANT, {**PROCESS, "donnees": {"url": "https://api.example.test?token=abc123"}})
    assert entreprise_depot.lister_objets(conn, TENANT) == []

    garde = entreprise_depot.enregistrer_objet(
        conn, TENANT, {**PROCESS, "donnees": {"secret_ref": "vault/banque/cartes", "url": "https://api.example.test"}})
    assert garde["donnees"]["secret_ref"] == "vault/banque/cartes"


@besoin_pg
def test_temporalite_incoherente_refusee(conn):
    with pytest.raises(entreprise_depot.ObjetInvalide):
        entreprise_depot.enregistrer_objet(conn, TENANT, {
            **PROCESS, "valide_depuis": "2026-10-30T10:00:00+00:00",
            "valide_jusqua": "2026-10-30T09:00:00+00:00"})
    assert entreprise_depot.lister_objets(conn, TENANT) == []


@besoin_pg
def test_lister_filtre_et_borne(conn):
    entreprise_depot.enregistrer_objet(conn, TENANT, PROCESS)
    entreprise_depot.enregistrer_objet(conn, TENANT, SITUATION)
    entreprise_depot.enregistrer_objet(conn, TENANT, {
        "id": "cap-cartes", "famille": "identite_structure", "type": "CAPABILITY", "mode": "CONFIRMED"})

    assert [o["id"] for o in entreprise_depot.lister_objets(conn, TENANT, famille="identite_structure")] == [
        "cap-cartes", "tbt-process"]
    assert [o["id"] for o in entreprise_depot.lister_objets(conn, TENANT, type_="PROCESS")] == ["tbt-process"]
    assert [o["id"] for o in entreprise_depot.lister_objets(conn, TENANT, mode="observed")] == ["sit-cartes"]
    assert len(entreprise_depot.lister_objets(conn, TENANT, limite=1)) == 1


@besoin_pg
def test_reapplication_du_schema_est_idempotente(conn):
    depot.appliquer_schema(conn)
    depot.appliquer_schema(conn)

    process = entreprise_depot.enregistrer_objet(conn, TENANT, PROCESS)
    assert process["version"] == 1
    assert entreprise_depot.lire_objet(conn, TENANT, PROCESS["id"])["type"] == "PROCESS"
