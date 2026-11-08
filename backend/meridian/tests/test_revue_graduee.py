"""D3 : revue graduée par risque — AUTO_VISIBLE révocable, ATTENTION, BLOQUANT.

``niveau_revise`` et ``jumeau_critique`` sont déterministes et testés sans base ;
le routage, la révocation et l'audit sont rejoués sur le schéma réel (fixture
``conn``, marqueur ``besoin_pg`` — ``JUMEAU_PG_DSN`` requis).
"""
from datetime import datetime, timedelta, timezone
import os

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import depot
from meridian.adapters.outbound.postgres import revue_graduee
from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, claim

DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")

MAINTENANT = datetime.now(timezone.utc)


# --- Niveau déterministe, sans base ---


def test_niveau_bloquant_par_contexte():
    element = {"predicat": "REGLE_TVA", "type": "BUSINESS_RULE", "donnees": {}}
    assert revue_graduee.niveau_revise(element, {"jumeau_critique": True}) == "BLOQUANT"
    assert revue_graduee.niveau_revise(element, {"invalide_remplace": True}) == "BLOQUANT"
    assert revue_graduee.niveau_revise(element, {"nb_twins": 3}) == "BLOQUANT"


def test_niveau_bloquant_predicats_sensibles():
    for predicat in ("DECISION_DE_RETIRER", "SUPPRIME_COMPTE", "REGLE_SECURITE"):
        element = {"predicat": predicat, "type": "BUSINESS_RULE", "donnees": {}}
        assert revue_graduee.niveau_revise(element) == "BLOQUANT"
    # Le type de la proposition (donnees.type_claim) est aussi inspecté.
    element = {"predicat": "REGLE", "donnees": {"type_claim": "SUPPRESSION_DONNEE"}}
    assert revue_graduee.niveau_revise(element) == "BLOQUANT"


def test_niveau_attention():
    element = {"predicat": "DEPEND_DE", "type": "DEPENDENCY", "jumeau_id": "tbt",
               "donnees": {}}
    assert revue_graduee.niveau_revise(element, {"contredit_declare": True}) == "ATTENTION"
    assert revue_graduee.niveau_revise(element, {"nb_twins": 2}) == "ATTENTION"
    assert revue_graduee.niveau_revise(
        element, {"source_externe_non_verifiee": True}) == "ATTENTION"


def test_niveau_auto_visible_par_defaut():
    element = {"predicat": "DEPEND_DE", "type": "DEPENDENCY", "jumeau_id": "tbt",
               "donnees": {}}
    assert revue_graduee.niveau_revise(element) == "AUTO_VISIBLE"


def test_nb_twins_depuis_donnees():
    element = {"jumeau_id": "tbt", "donnees": {"twin_ids": ["a", "b"]}}
    assert revue_graduee.niveau_revise(element) == "BLOQUANT"  # tbt + a + b = 3
    element = {"jumeau_id": "tbt", "donnees": {"twin_ids": ["a"]}}
    assert revue_graduee.niveau_revise(element) == "ATTENTION"  # tbt + a = 2


def test_jumeau_critique_domaines_et_applications_des_packs():
    marques = revue_graduee.marques_critiques()
    assert revue_graduee.jumeau_critique({"domaine": "Paiement"}, marques)
    assert revue_graduee.jumeau_critique({"domaine": "Risque"}, marques)
    assert revue_graduee.jumeau_critique({"id": "fraude"}, marques)
    assert revue_graduee.jumeau_critique({"application_id": "comptes"}, marques)
    assert not revue_graduee.jumeau_critique({"domaine": "Support"}, marques)
    assert not revue_graduee.jumeau_critique({"id": "logistique"}, marques)


# --- Routage sur le schéma réel ---


def _jumeau(jid, domaine=None, application_id=None):
    j = dict(JUMEAU)
    j["id"] = jid
    j["nom"] = jid.upper()
    if domaine:
        j["domaine"] = domaine
    if application_id:
        j["application_id"] = application_id
    return j


def _claims(conn, jumeau_id):
    return {c["objet"]: c for c in depot.lister_claims(conn, jumeau_id)}


def _donnees(conn, claim_id):
    return conn.execute(
        "SELECT donnees FROM claim WHERE id = %s", (claim_id,)).fetchone()[0]


def _statut(conn, claim_id):
    return conn.execute(
        "SELECT statut FROM claim WHERE id = %s", (claim_id,)).fetchone()[0]


@besoin_pg
def test_twin_critique_est_bloquant(conn):
    jumeau = _jumeau("pay", domaine="Paiement")
    depot.enregistrer(conn, jumeau, dict(SOURCE, nom="pay-repo"), [claim("lib-x")], ACTIVITE)
    cid = _claims(conn, "pay")["lib-x"]["id"]

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["bloquants"] == 1 and rapport["auto_visibles"] == 0
    assert _statut(conn, cid) == "PROPOSED"
    donnees = _donnees(conn, cid)
    assert donnees["revue_niveau"] == "BLOQUANT"
    assert donnees["bloque"] == "revue_requise"


@besoin_pg
def test_predicat_sensible_est_bloquant(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE),
                      [{**claim("x"), "predicat": "DECISION_DE_RETIRER", "type": "BUSINESS_RULE"}],
                      ACTIVITE)
    cid = _claims(conn, "tbt")["x"]["id"]
    rapport = revue_graduee.appliquer(conn, "banque")
    assert rapport["bloquants"] == 1
    assert _statut(conn, cid) == "PROPOSED"
    assert _donnees(conn, cid)["bloque"] == "revue_requise"


@besoin_pg
def test_reecriture_d_invalide_est_bloquante(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE),
                      [{**claim("v1"), "predicat": "REGLE_TVA"},
                       {**claim("v2"), "predicat": "REGLE_TVA"}], ACTIVITE)
    ids = _claims(conn, "tbt")
    conn.execute("UPDATE claim SET statut = 'INVALIDATED' WHERE id = %s", (ids["v1"]["id"],))

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["bloquants"] == 1
    assert _donnees(conn, ids["v2"]["id"])["revue_niveau"] == "BLOQUANT"


@besoin_pg
def test_proposition_simple_auto_acceptee_et_revocable(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["auto_visibles"] == 1 and rapport["erreurs"] == []
    assert _statut(conn, cid) == "ACCEPTED"
    donnees = _donnees(conn, cid)
    assert donnees["revue_niveau"] == "AUTO_VISIBLE"
    fin = datetime.fromisoformat(donnees["revocable_jusqua"])
    assert fin - datetime.now(timezone.utc) > timedelta(days=29)
    # La revue système est écrite avant le statut, comme toute revue.
    revue = conn.execute(
        "SELECT acteur, decision FROM revue WHERE claim_id = %s", (cid,)).fetchone()
    assert revue == ("revue_graduee", "ACCEPTED")


@besoin_pg
def test_contournement_observed_vs_declared_en_attention(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE),
                      [claim("declares"), claim("observes")], ACTIVITE)
    ids = _claims(conn, "tbt")
    conn.execute("UPDATE claim SET mode = 'OBSERVED' WHERE id = %s", (ids["observes"]["id"],))

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["attentions"] == 1
    assert _statut(conn, ids["observes"]["id"]) == "PROPOSED"
    assert _donnees(conn, ids["observes"]["id"])["revue_niveau"] == "ATTENTION"
    # Le claim DECLARED, sans contradiction, est auto-accepté.
    assert _statut(conn, ids["declares"]["id"]) == "ACCEPTED"


@besoin_pg
def test_source_externe_non_verifiee_en_attention(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE, type="JIRA", nom="jira-1"),
                      [claim("ticket")], ACTIVITE)
    cid = _claims(conn, "tbt")["ticket"]["id"]

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["attentions"] == 1
    assert _statut(conn, cid) == "PROPOSED"


@besoin_pg
def test_auto_accept_trace_dans_outil_audit(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]

    revue_graduee.appliquer(conn, "banque")

    lignes = conn.execute(
        "SELECT outil, capacite, acteur, statut, arguments FROM outil_audit "
        "WHERE tenant_id = 'banque' AND outil = 'revue_graduee'").fetchall()
    assert len(lignes) == 1
    outil, capacite, acteur, statut, arguments = lignes[0]
    assert capacite == "auto_accept_claim" and statut == "ok"
    assert acteur == "revue_graduee"
    assert arguments["claim_id"] == cid


@besoin_pg
def test_revoquer_dans_la_fenetre_rend_contested(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]
    revue_graduee.appliquer(conn, "banque")

    resultat = revue_graduee.revoquer(
        conn, "banque", cid, "alice", "erreur constatée au passage",
        maintenant=MAINTENANT + timedelta(days=10))

    assert resultat["statut"] == "CONTESTED" and resultat["revoque"] is True
    assert _statut(conn, cid) == "CONTESTED"
    donnees = _donnees(conn, cid)
    assert donnees["revoque_par"] == "alice"
    revue = conn.execute(
        "SELECT decision, acteur FROM revue WHERE claim_id = %s ORDER BY id", (cid,)).fetchall()
    assert [r[0] for r in revue] == ["ACCEPTED", "CONTESTED"]
    # La révocation est elle aussi journalisée.
    audit = conn.execute(
        "SELECT capacite FROM outil_audit WHERE tenant_id = 'banque' "
        "AND capacite = 'revocation_claim'").fetchall()
    assert len(audit) == 1


@besoin_pg
def test_revoquer_apres_la_fenetre_est_refuse(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]
    revue_graduee.appliquer(conn, "banque")

    with pytest.raises(revue_graduee.RevocationRefusee):
        revue_graduee.revoquer(conn, "banque", cid, "alice", "trop tard",
                               maintenant=MAINTENANT + timedelta(days=31))
    assert _statut(conn, cid) == "ACCEPTED"


@besoin_pg
def test_revoquer_refuse_un_claim_non_auto_accepte(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]

    with pytest.raises(revue_graduee.RevocationRefusee):
        revue_graduee.revoquer(conn, "banque", cid, "alice", "pas auto")
    with pytest.raises(LookupError):
        revue_graduee.revoquer(conn, "banque", 999999, "alice", "inconnu")
    with pytest.raises(LookupError):
        revue_graduee.revoquer(conn, "autre-tenant", cid, "alice", "mauvais tenant")


@besoin_pg
def test_claim_sans_preuve_support_reste_propose(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]
    conn.execute("DELETE FROM claim_preuve WHERE claim_id = %s", (cid,))

    rapport = revue_graduee.appliquer(conn, "banque")

    # L'invariant « ACCEPTED exige une preuve » n'est jamais contourné.
    assert rapport["sans_preuve"] == 1 and rapport["auto_visibles"] == 0
    assert _statut(conn, cid) == "PROPOSED"


@besoin_pg
def test_appliquer_est_idempotent(conn):
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    revue_graduee.appliquer(conn, "banque")
    second = revue_graduee.appliquer(conn, "banque")
    assert second["traites"] == 0


@besoin_pg
def test_proposition_objet_confirmee_puis_revoquee(conn):
    conn.execute(
        "INSERT INTO objet_entreprise (id, tenant_id, famille, type, mode, titre, donnees) "
        "VALUES ('prop-1', 'banque', 'connaissance', 'CLAIM', 'PROPOSED', 'p1', "
        "'{\"type_claim\": \"BUSINESS_RULE\", \"predicat\": \"REGLE_Y\"}'::jsonb)")

    rapport = revue_graduee.appliquer(conn, "banque")

    assert rapport["propositions"]["auto_visibles"] == 1
    ligne = conn.execute(
        "SELECT mode, donnees FROM objet_entreprise WHERE id = 'prop-1'").fetchone()
    assert ligne[0] == "CONFIRMED"
    assert ligne[1]["revue_niveau"] == "AUTO_VISIBLE"
    assert "revocable_jusqua" in ligne[1]

    resultat = revue_graduee.revoquer(conn, "banque", "prop-1", "alice", "à revoir",
                                    maintenant=MAINTENANT + timedelta(days=5))
    assert resultat["statut"] == "CONTESTED"
    ligne = conn.execute(
        "SELECT mode, donnees FROM objet_entreprise WHERE id = 'prop-1'").fetchone()
    assert ligne[0] == "PROPOSED" and ligne[1]["statut_revue"] == "CONTESTED"


@besoin_pg
def test_niveaux_rend_des_comptes_jamais_de_ratios(conn):
    jumeau = _jumeau("pay", domaine="Paiement")
    depot.enregistrer(conn, jumeau, dict(SOURCE, nom="pay-repo"), [claim("lib-x")], ACTIVITE)
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    cid = _claims(conn, "tbt")["motor"]["id"]
    revue_graduee.appliquer(conn, "banque")
    revue_graduee.revoquer(conn, "banque", cid, "alice", "correction")

    rep = revue_graduee.niveaux(conn, "banque")

    claims = rep["claims"]
    assert claims["BLOQUANT"] == 1
    assert claims["AUTO_VISIBLE"] == 1
    assert claims["revoques"] == 1 and claims["revocables"] == 0
    assert claims["total"] == 2
    assert all(not cle.startswith("taux") for cle in claims)
    assert "n" not in claims or claims["n"] == claims["total"]
    vide = revue_graduee.niveaux(conn, "tenant-inconnu")
    assert vide["claims"]["total"] == 0


# --- Endpoint ---


class _Connexion:
    """Context manager rendant la connexion de test, comme le ferait psycopg."""

    def __init__(self, connexion):
        self.connexion = connexion

    def __enter__(self):
        return self.connexion

    def __exit__(self, *_):
        return False


def _app():
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


@besoin_pg
def test_endpoint_niveaux_repartition_tenant_scopee(conn, monkeypatch):
    jumeau = _jumeau("pay", domaine="Paiement")
    depot.enregistrer(conn, jumeau, dict(SOURCE, nom="pay-repo"), [claim("lib-x")], ACTIVITE)
    depot.enregistrer(conn, dict(JUMEAU), dict(SOURCE), [claim("motor")], ACTIVITE)
    revue_graduee.appliquer(conn, "banque")
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.delenv("JUMEAU_RLS", raising=False)
    monkeypatch.setattr(
        boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion(conn))

    reponse = _app().get("/api/boucle/revue/niveaux", headers={"X-Tenant": "banque"})

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["tenant"] == "banque"
    assert corps["claims"]["BLOQUANT"] == 1
    assert corps["claims"]["AUTO_VISIBLE"] == 1


def test_endpoint_niveaux_sans_dsn_503(monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().get("/api/boucle/revue/niveaux", headers={"X-Tenant": "banque"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]
