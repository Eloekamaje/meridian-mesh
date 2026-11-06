"""Partage de connaissance : `claim_share`, projection et frontières.

Le Claim reste privé par défaut. Un partage n'élargit jamais la confidentialité ; `SECRET` ne
sort jamais ; `CONFIDENTIAL` n'est partagé qu'en `SUMMARY` et avec revue.
"""
from datetime import datetime, timedelta, timezone

import pytest

from meridian.adapters.outbound.postgres import depot, partage
from meridian.domain import partage as domaine
from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, besoin_pg, claim


# --- domaine pur ---------------------------------------------------------------------------------

def test_consommateur_exige_un_tenant():
    with pytest.raises(domaine.PartageInvalide):
        domaine.Consommateur("")


def test_partage_refuse_un_scope_inconnu():
    with pytest.raises(domaine.PartageInvalide):
        domaine.Partage(1, "APPLICATION", "x", granted_by="alice")


def test_external_desactive_par_defaut(monkeypatch):
    monkeypatch.delenv("JUMEAU_EXTERNAL_PUBLICATION", raising=False)
    assert "EXTERNAL" in domaine.SCOPES
    assert domaine.external_autorise() is False


@pytest.mark.parametrize("valeur", ["1", "true", "oui", "yes", "TRUE", " Oui "])
def test_external_active_par_variable(monkeypatch, valeur):
    monkeypatch.setenv("JUMEAU_EXTERNAL_PUBLICATION", valeur)
    assert domaine.external_autorise() is True


@pytest.mark.parametrize("valeur", ["", "0", "false", "non", "no"])
def test_external_desactive_par_valeur_fausse(monkeypatch, valeur):
    monkeypatch.setenv("JUMEAU_EXTERNAL_PUBLICATION", valeur)
    assert domaine.external_autorise() is False


def test_confidentialite_effective_prend_la_plus_forte():
    claim_ = {"confidentialite": "PUBLIC"}
    preuves = [{"confidentialite": "INTERNAL"}, {"confidentialite": "CONFIDENTIAL"}]
    assert domaine.confidentialite_effective(claim_, preuves) == "CONFIDENTIAL"


def test_autoriser_refuse_un_autre_tenant():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "INTERNAL"}
    partages = [domaine.Partage(1, "TENANT", "banque", granted_by="alice")]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("autre")
    ) is None


def test_autoriser_confidential_sans_revue_refuse():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "CONFIDENTIAL"}
    partages = [domaine.Partage(1, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) is None


def test_autoriser_confidential_avec_revue_autorise_summary():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "CONFIDENTIAL"}
    partages = [domaine.Partage(1, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice",
                                reviewed_by="bob")]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) == "SUMMARY"


def test_autoriser_secret_refuse_tout():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "SECRET"}
    partages = [domaine.Partage(1, "TENANT", "banque", "EVIDENCE", granted_by="alice")]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", twin_id="autre")
    ) is None


def test_autoriser_partage_revoque_refuse():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "INTERNAL"}
    partages = [domaine.Partage(1, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice",
                                revoked_at=datetime.now(timezone.utc))]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) is None


def test_autoriser_partage_expire_refuse():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "INTERNAL"}
    partages = [domaine.Partage(1, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice",
                                valid_to=datetime.now(timezone.utc) - timedelta(seconds=1))]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) is None


def test_consommateur_normalise_external_id():
    assert domaine.Consommateur("banque", external_id="  partenaire  ").external_id == "partenaire"


def test_autoriser_external_matche_le_bon_external_id():
    claim_ = {"tenant_id": "banque", "jumeau_id": "tbt", "confidentialite": "INTERNAL"}
    partages = [domaine.Partage(1, "EXTERNAL", "partenaire", granted_by="alice")]
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", external_id="partenaire")
    ) == "SUMMARY"
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque", external_id="autre")
    ) is None
    assert domaine.autoriser(
        claim_, (), partages, domaine.Consommateur("banque")
    ) is None


def test_projeter_summary_cache_les_preuves():
    claim_ = {"id": 1, "tenant_id": "banque", "jumeau_id": "tbt", "objet": "motor",
              "confidentialite": "INTERNAL"}
    vue = domaine.projeter(claim_, [{"locator": "git://tbt@sha1:a.py#L1-L2"}], "SUMMARY")
    assert vue["projection"] == "SUMMARY"
    assert "preuves" not in vue


def test_projeter_evidence_ajoute_les_localisateurs():
    claim_ = {"id": 1, "tenant_id": "banque", "jumeau_id": "tbt", "objet": "motor",
              "confidentialite": "INTERNAL"}
    vue = domaine.projeter(claim_, [{"locator": "git://tbt@sha1:a.py#L1-L2"}], "EVIDENCE")
    assert vue["preuves"][0]["locator"] == "git://tbt@sha1:a.py#L1-L2"


# --- Postgres ------------------------------------------------------------------------------------

def _claim_id(conn, objet="motor", confidentialite_preuve=None):
    c = claim(objet)
    if confidentialite_preuve:
        c["preuves"][0]["confidentialite"] = confidentialite_preuve
    depot.enregistrer(conn, JUMEAU, SOURCE, [c], ACTIVITE)
    return conn.execute(
        "SELECT id FROM claim WHERE jumeau_id = 'tbt' AND objet = %s", (objet,)
    ).fetchone()[0]


@besoin_pg
def test_owner_voit_toujours_son_claim(conn):
    cid = _claim_id(conn)
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", twin_id="tbt")
    ) == "EVIDENCE"


@besoin_pg
def test_team_share_autorise_uniquement_l_equipe(conn):
    cid = _claim_id(conn)
    partage.accorder(conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) == "SUMMARY"
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="autre")
    ) is None


@besoin_pg
def test_tenant_share_autorise_un_autre_twin(conn):
    cid = _claim_id(conn)
    partage.accorder(conn, "banque", cid, "TENANT", "banque", "EVIDENCE", granted_by="alice")
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", twin_id="autre")
    ) == "EVIDENCE"


@besoin_pg
def test_revocation_ferme_le_partage(conn):
    cid = _claim_id(conn)
    share = partage.accorder(
        conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")
    assert partage.revoquer(conn, "banque", share["id"], "alice")
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) is None


@besoin_pg
def test_secret_ne_peut_pas_etre_partage(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'SECRET' WHERE id = %s", (cid,))
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")


@besoin_pg
def test_confidential_exige_summary_et_revue(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "TEAM", "equipe-tbt", "EVIDENCE", granted_by="alice",
            reviewed_by="bob")
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")
    partage.accorder(
        conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice",
        reviewed_by="bob")
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) == "SUMMARY"


@besoin_pg
def test_preuve_confidentielle_limite_a_summary(conn):
    cid = _claim_id(conn, confidentialite_preuve="CONFIDENTIAL")
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "TEAM", "equipe-tbt", "EVIDENCE", granted_by="alice",
            reviewed_by="bob")
    partage.accorder(
        conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice",
        reviewed_by="bob")
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="equipe-tbt")
    ) == "SUMMARY"


@besoin_pg
def test_partage_tenant_ne_peut_pas_viser_un_autre_tenant(conn):
    cid = _claim_id(conn)
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "TENANT", "autre", "SUMMARY", granted_by="alice")


@besoin_pg
def test_scope_external_refuse_par_defaut(conn, monkeypatch):
    monkeypatch.delenv("JUMEAU_EXTERNAL_PUBLICATION", raising=False)
    cid = _claim_id(conn)
    with pytest.raises(domaine.PartageInvalide):
        partage.accorder(
            conn, "banque", cid, "EXTERNAL", "partenaire", "SUMMARY", granted_by="alice")


@besoin_pg
def test_scope_external_accepte_si_active(conn, monkeypatch):
    monkeypatch.setenv("JUMEAU_EXTERNAL_PUBLICATION", "1")
    cid = _claim_id(conn)
    share = partage.accorder(
        conn, "banque", cid, "EXTERNAL", "partenaire", "SUMMARY", granted_by="alice")
    assert share["scope_type"] == "EXTERNAL"


@besoin_pg
def test_external_visible_seulement_pour_le_bon_external_id(conn, monkeypatch):
    monkeypatch.setenv("JUMEAU_EXTERNAL_PUBLICATION", "1")
    cid = _claim_id(conn)
    partage.accorder(
        conn, "banque", cid, "EXTERNAL", "partenaire", "SUMMARY", granted_by="alice")
    vus = partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", external_id="partenaire"))
    assert len(vus) == 1
    assert vus[0]["projection"] == "SUMMARY"
    assert partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", external_id="autre")) == []
    assert partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque")) == []


@besoin_pg
def test_publier_carte_refuse_external_par_defaut(conn, monkeypatch):
    monkeypatch.delenv("JUMEAU_EXTERNAL_PUBLICATION", raising=False)
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
    ], ACTIVITE)
    with pytest.raises(domaine.PartageInvalide):
        partage.publier_carte(
            conn, "banque", "tbt", scope_type="EXTERNAL", scope_id="partenaire",
            granted_by="alice")


@besoin_pg
def test_publier_carte_accepte_external_si_active(conn, monkeypatch):
    monkeypatch.setenv("JUMEAU_EXTERNAL_PUBLICATION", "1")
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
    ], ACTIVITE)
    bilan = partage.publier_carte(
        conn, "banque", "tbt", scope_type="EXTERNAL", scope_id="partenaire",
        granted_by="alice")
    assert bilan["publies"] == 1


@besoin_pg
def test_claims_visibles_projette_et_cache_les_preuves(conn):
    cid = _claim_id(conn)
    partage.accorder(
        conn, "banque", cid, "TEAM", "equipe-tbt", "SUMMARY", granted_by="alice")
    visibles = partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", team_id="equipe-tbt"))
    assert len(visibles) == 1
    assert visibles[0]["projection"] == "SUMMARY"
    assert "preuves" not in visibles[0]
    assert partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", team_id="autre")) == []


@besoin_pg
def test_projection_evidence_ajoute_les_localisateurs(conn):
    cid = _claim_id(conn)
    partage.accorder(
        conn, "banque", cid, "TENANT", "banque", "EVIDENCE", granted_by="alice")
    vue = partage.projeter_claim(
        conn, "banque", cid, domaine.Consommateur("banque", twin_id="autre"))
    assert vue["projection"] == "EVIDENCE"
    assert vue["preuves"][0]["locator"].startswith("git://tbt@sha1")


def _claim_carte(objet, predicat):
    c = claim(objet)
    c["predicat"] = predicat
    c["type"] = "CAPABILITY"
    return c


@besoin_pg
def test_publier_carte_publie_les_claims_metier_en_summary(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
        _claim_carte("GET /dossiers", "EXPOSE"),
        _claim_carte("Fraude", "ECHANGE_AVEC"),
        _claim_carte("fastapi", "DEPEND_DE"),
    ], ACTIVITE)
    bilan = partage.publier_carte(conn, "banque", "tbt", granted_by="alice")
    assert bilan["publies"] == 3
    visibles = partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", portfolio_id="paiement"))
    assert {v["objet"] for v in visibles} == {"Gérer les dossiers", "GET /dossiers", "Fraude"}
    assert all(v["projection"] == "SUMMARY" for v in visibles)
    assert all("preuves" not in v for v in visibles)
    assert partage.publier_carte(conn, "banque", "tbt", granted_by="alice")["deja"] == 3


@besoin_pg
def test_depublier_carte_retire_les_partages(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
    ], ACTIVITE)
    partage.publier_carte(conn, "banque", "tbt", granted_by="alice")
    assert partage.depublier_carte(conn, "banque", "tbt", revoked_by="alice")["revoques"] == 1
    assert partage.claims_visibles(
        conn, "banque", domaine.Consommateur("banque", portfolio_id="paiement")) == []


@besoin_pg
def test_publier_carte_ignore_secret_et_confidentiel_sans_revue(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
        _claim_carte("Secret", "EXPOSE"),
        _claim_carte("Confidentiel", "ECHANGE_AVEC"),
    ], ACTIVITE)
    conn.execute("UPDATE claim SET confidentialite = 'SECRET' WHERE objet = 'Secret'")
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE objet = 'Confidentiel'")
    bilan = partage.publier_carte(conn, "banque", "tbt", granted_by="alice")
    assert bilan["publies"] == 1
    assert len(bilan["ignores"]) == 2
    assert partage.publier_carte(
        conn, "banque", "tbt", granted_by="alice", reviewed_by="bob")["publies"] == 1


@besoin_pg
def test_publication_confidential_avec_revue_ecrit_une_trace(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Confidentiel", "ECHANGE_AVEC"),
    ], ACTIVITE)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE objet = 'Confidentiel'")
    bilan = partage.publier_carte(
        conn, "banque", "tbt", granted_by="alice", reviewed_by="bob")
    assert bilan["publies"] == 1
    lignes = conn.execute(
        """SELECT r.tenant_id, r.share_id, s.claim_id, r.reviewer, r.decision, r.reason
           FROM publication_review r JOIN claim_share s ON s.id = r.share_id"""
    ).fetchall()
    assert len(lignes) == 1
    assert lignes[0][0] == "banque"
    assert lignes[0][3] == "bob"
    assert lignes[0][4] == "APPROVED"
    assert lignes[0][5]


@besoin_pg
def test_publication_non_confidential_ne_cree_pas_de_trace(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
    ], ACTIVITE)
    partage.publier_carte(conn, "banque", "tbt", granted_by="alice", reviewed_by="bob")
    assert conn.execute("SELECT count(*) FROM publication_review").fetchone()[0] == 0


@besoin_pg
def test_publier_carte_refuse_auto_revue(conn):
    depot.enregistrer(conn, JUMEAU, SOURCE, [
        _claim_carte("Gérer les dossiers", "REALISE_CAPACITE"),
    ], ACTIVITE)
    with pytest.raises(domaine.PartageInvalide):
        partage.publier_carte(
            conn, "banque", "tbt", granted_by="alice", reviewed_by="alice")


# --- revue des publications ----------------------------------------------------------------------

def _partage_en_attente(conn, cid, *, granted_by="alice", scope_type="TEAM",
                        scope_id="equipe-tbt", reason="carte de catalogue"):
    return conn.execute(
        """INSERT INTO claim_share
             (tenant_id, claim_id, scope_type, scope_id, projection, granted_by, reason)
           VALUES ('banque', %s, %s, %s, 'SUMMARY', %s, %s)
           RETURNING id""",
        (cid, scope_type, scope_id, granted_by, reason),
    ).fetchone()[0]


@besoin_pg
def test_lister_a_reviser_remonte_confidential_non_revu(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    sid = _partage_en_attente(conn, cid)
    cid_interne = _claim_id(conn, objet="uvicorn")
    partage.accorder(
        conn, "banque", cid_interne, "TEAM", "equipe-tbt", "SUMMARY",
        granted_by="alice", reason="carte de catalogue")
    a_reviser = partage.lister_a_reviser(conn, "banque")
    assert [(ligne["id"], ligne["claim_id"], ligne["objet"]) for ligne in a_reviser] == [
        (sid, cid, "motor")]
    assert a_reviser[0]["confidentialite"] == "CONFIDENTIAL"
    assert a_reviser[0]["scope_type"] == "TEAM"
    assert a_reviser[0]["scope_id"] == "equipe-tbt"
    assert a_reviser[0]["granted_by"] == "alice"
    partage.decider_revue(conn, "banque", sid, reviewer="bob", decision="APPROVED")
    assert partage.lister_a_reviser(conn, "banque") == []


@besoin_pg
def test_lister_a_reviser_prend_la_confidentialite_des_preuves(conn):
    cid = _claim_id(conn, confidentialite_preuve="CONFIDENTIAL")
    sid = _partage_en_attente(conn, cid)
    assert [ligne["id"] for ligne in partage.lister_a_reviser(conn, "banque")] == [sid]


@besoin_pg
def test_decider_revue_approuvee_ecrit_la_trace_et_ouvre_le_partage(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    sid = _partage_en_attente(conn, cid)
    consommateur = domaine.Consommateur("banque", team_id="equipe-tbt")
    assert partage.autoriser_claim(conn, "banque", cid, consommateur) is None
    bilan = partage.decider_revue(
        conn, "banque", sid, reviewer="bob", decision="APPROVED", reason="revue conforme")
    assert bilan["decision"] == "APPROVED"
    assert bilan["revoked"] is False
    assert partage.autoriser_claim(conn, "banque", cid, consommateur) == "SUMMARY"
    assert conn.execute(
        "SELECT reviewed_by FROM claim_share WHERE id = %s", (sid,)
    ).fetchone()[0] == "bob"
    assert conn.execute(
        """SELECT tenant_id, share_id, reviewer, decision, reason
           FROM publication_review WHERE share_id = %s""", (sid,)
    ).fetchone() == ("banque", sid, "bob", "APPROVED", "revue conforme")


@besoin_pg
def test_decider_revue_rejetee_revoque_le_partage(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    sid = _partage_en_attente(conn, cid)
    bilan = partage.decider_revue(
        conn, "banque", sid, reviewer="bob", decision="REJECTED", reason="trop sensible")
    assert bilan["revoked"] is True
    ligne = conn.execute(
        """SELECT reviewed_by, revoked_at, revoked_by, reason
           FROM claim_share WHERE id = %s""", (sid,)
    ).fetchone()
    assert ligne[0] is None
    assert ligne[1] is not None
    assert ligne[2] == "bob"
    assert ligne[3] == "trop sensible"
    assert partage.autoriser_claim(
        conn, "banque", cid, domaine.Consommateur("banque", team_id="equipe-tbt")) is None
    assert conn.execute(
        "SELECT decision, reviewer, reason FROM publication_review WHERE share_id = %s", (sid,)
    ).fetchone() == ("REJECTED", "bob", "trop sensible")


@besoin_pg
def test_decider_revue_refuse_auto_revue(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    sid = _partage_en_attente(conn, cid, granted_by="alice")
    with pytest.raises(domaine.PartageInvalide):
        partage.decider_revue(conn, "banque", sid, reviewer="alice", decision="APPROVED")
    assert conn.execute("SELECT count(*) FROM publication_review").fetchone()[0] == 0


@besoin_pg
def test_decider_revue_refuse_un_autre_tenant(conn):
    cid = _claim_id(conn)
    conn.execute("UPDATE claim SET confidentialite = 'CONFIDENTIAL' WHERE id = %s", (cid,))
    sid = _partage_en_attente(conn, cid)
    with pytest.raises(domaine.PartageInvalide):
        partage.decider_revue(conn, "autre", sid, reviewer="bob", decision="APPROVED")
