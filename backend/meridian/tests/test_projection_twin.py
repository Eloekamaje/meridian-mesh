"""D8 : le Twin comme projection des claims — vue calculée, écarts, endpoint.

La ligne ``jumeau`` porte l'identité ; tout le reste se déduit des claims
confirmés (ACCEPTED ou mode CONFIRMED, encore valides). Tests base réelle,
sautés sans ``JUMEAU_PG_DSN``, comme les autres tests Postgres.
"""
import pytest
from psycopg.types.json import Jsonb

from meridian.adapters.outbound.postgres import depot, projection_twin
from meridian.tests.conftest import besoin_pg

psycopg = pytest.importorskip("psycopg")
pytestmark = besoin_pg

TENANT = "banque"
AUTRE_TENANT = "assurance"


def _jumeau(conn, jid, *, tenant=TENANT, nom=None, equipe="equipe-a",
            type="APPLICATION", domaine="À confirmer", mission=None):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe, type, domaine, mission) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (jid, tenant, nom or jid, equipe, type, domaine, mission))
    return jid


def _source(conn, tenant, jid, nom="src-test"):
    return conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement) "
        "VALUES (%s, %s, 'GIT', %s, %s) ON CONFLICT (jumeau_id, nom) "
        "DO UPDATE SET nom = EXCLUDED.nom RETURNING id",
        (tenant, jid, nom, f"/depots/{nom}")).fetchone()[0]


def _preuve(conn, tenant, source_id, claim_id, locator):
    pid = conn.execute(
        "INSERT INTO preuve (tenant_id, source_id, type, locator, chemin, sha, "
        "ligne_debut, ligne_fin, hash, activite) "
        "VALUES (%s, %s, 'DOC', %s, 'doc.md', 's1', 1, 1, 'h', %s) RETURNING id",
        (tenant, source_id, locator, Jsonb({"extracteur": "test"}))).fetchone()[0]
    conn.execute(
        "INSERT INTO claim_preuve (claim_id, preuve_id, role) VALUES (%s, %s, 'SUPPORT')",
        (claim_id, pid))
    return pid


def _claim(conn, tenant, jumeau_id, predicat, objet, *, sujet=None, statut="PROPOSED",
           mode="DECLARED", prouve=True, source_id=None, locator=None):
    cid = conn.execute(
        "INSERT INTO claim (tenant_id, jumeau_id, sujet, predicat, objet, type, "
        "confiance, mode) VALUES (%s, %s, %s, %s, %s, 'CLAIM', 0.8, %s) RETURNING id",
        (tenant, jumeau_id, sujet if sujet is not None else jumeau_id,
         predicat, objet, mode)).fetchone()[0]
    if prouve:
        sid = source_id if source_id is not None else _source(conn, tenant, jumeau_id)
        _preuve(conn, tenant, sid, cid, locator or f"doc.md#{predicat}-{objet}")
    if statut == "ACCEPTED":
        depot.reviser(conn, cid, "alice", "ACCEPTED", "revue faite")
    elif statut != "PROPOSED":
        conn.execute("UPDATE claim SET statut = %s WHERE id = %s", (statut, cid))
    return cid


# --- projeter : vue calculée ---


def test_projeter_deduit_capacites_dependances_et_dependants(conn):
    _jumeau(conn, "app-a", nom="Application A")
    _jumeau(conn, "app-b", nom="Application B")
    _claim(conn, TENANT, "app-a", "REALISE_CAPACITE", "cap-paiement", statut="ACCEPTED")
    _claim(conn, TENANT, "app-a", "DEPEND_DE", "app-b", statut="ACCEPTED")
    _claim(conn, TENANT, "app-a", "EXPOSE", "GET /v1/cartes")  # PROPOSED : hors capacités
    _claim(conn, TENANT, "app-a", "REALISE_CAPACITE", "cap-fantome", statut="CONTESTED")

    vue = projection_twin.projeter(conn, TENANT, "app-a")

    assert vue["twin_id"] == "app-a"
    assert vue["identite"]["nom"] == "Application A"
    assert vue["identite"]["equipe"] == "equipe-a"
    assert [c["objet"] for c in vue["capacites"]] == ["cap-paiement"]
    assert [d["objet"] for d in vue["dependances"]] == ["app-b"]
    assert vue["dependances"][0]["twin"] == {"id": "app-b", "nom": "Application B"}

    vue_b = projection_twin.projeter(conn, TENANT, "app-b")
    assert [d["twin"]["id"] for d in vue_b["dependants"]] == ["app-a"]
    assert vue_b["dependants"][0]["predicat"] == "DEPEND_DE"
    assert vue_b["capacites"] == [] and vue_b["dependances"] == []


def test_projeter_etat_epistemique_couverture_et_fraicheur(conn):
    _jumeau(conn, "app-e")
    _claim(conn, TENANT, "app-e", "REALISE_CAPACITE", "cap-x", statut="ACCEPTED")
    _claim(conn, TENANT, "app-e", "DETIENT", "les cartes", statut="ACCEPTED")

    vue = projection_twin.projeter(conn, TENANT, "app-e")

    etat = vue["etat_epistemique"]
    assert etat["claims_valides"] == 2
    assert etat["par_statut"] == {"ACCEPTED": 2}
    assert etat["label"] == "CONSOLIDE"
    assert etat["maturite_max"].startswith("M")
    assert vue["fraicheur_derniere_preuve"] is not None
    couverture = vue["couverture"]
    assert couverture["total"] == 7
    assert couverture["answered"] >= 2  # « sert » et « informations » ont des preuves
    assert vue["contradictions_ouvertes"] == 0


def test_projeter_twin_sans_claims_est_inconnu(conn):
    _jumeau(conn, "app-vide")

    vue = projection_twin.projeter(conn, TENANT, "app-vide")

    assert vue["capacites"] == [] and vue["dependances"] == []
    assert vue["etat_epistemique"]["label"] == "INCONNU"
    assert vue["etat_epistemique"]["claims_valides"] == 0
    assert vue["fraicheur_derniere_preuve"] is None


def test_projeter_inconnu_ou_autre_tenant_rend_none(conn):
    _jumeau(conn, "app-b1", tenant=AUTRE_TENANT)

    assert projection_twin.projeter(conn, TENANT, "absent") is None
    assert projection_twin.projeter(conn, TENANT, "app-b1") is None


def test_mode_confirmed_vaut_acceptation(conn):
    _jumeau(conn, "app-c")
    _claim(conn, TENANT, "app-c", "REALISE_CAPACITE", "cap-confirmee", mode="CONFIRMED")

    vue = projection_twin.projeter(conn, TENANT, "app-c")
    assert [c["objet"] for c in vue["capacites"]] == ["cap-confirmee"]


def test_contradiction_ouverte_est_comptee_et_marque_la_couverture(conn):
    _jumeau(conn, "app-k")
    cid = _claim(conn, TENANT, "app-k", "REALISE_CAPACITE", "cap-k", statut="ACCEPTED")
    conn.execute(
        "INSERT INTO contradiction (tenant_id, jumeau_id, claim_id, enonce, "
        "preuve_a, preuve_b, systeme_a, systeme_b, signalee_par) "
        "VALUES (%s, 'app-k', %s, 'deux sources se contredisent', 'a', 'b', "
        "'git', 'jira', 'agent')",
        (TENANT, cid))

    vue = projection_twin.projeter(conn, TENANT, "app-k")

    assert vue["contradictions_ouvertes"] == 1
    assert vue["etat_epistemique"]["label"] == "CONTESTE"
    assert vue["couverture"]["questions"]["sert"] == "contradicted"
    assert vue["couverture"]["contradicted"] == 1

    conn.execute("UPDATE contradiction SET statut = 'TRANCHEE', tranchee_par = 'bob', "
                 "verdict = 'a' WHERE claim_id = %s", (cid,))
    vue = projection_twin.projeter(conn, TENANT, "app-k")
    assert vue["contradictions_ouvertes"] == 0
    assert vue["couverture"]["questions"]["sert"] == "answered"


# --- projection_tous : bornée, tenant-scopée ---


def test_projection_tous_rend_chaque_twin_bornee_au_tenant(conn):
    for jid in ("t1", "t2", "t3"):
        _jumeau(conn, jid)
    _jumeau(conn, "hors", tenant=AUTRE_TENANT)
    _claim(conn, TENANT, "t1", "REALISE_CAPACITE", "cap-t1", statut="ACCEPTED")
    _claim(conn, AUTRE_TENANT, "hors", "REALISE_CAPACITE", "cap-hors", statut="ACCEPTED")

    vues = projection_twin.projection_tous(conn, TENANT)

    assert {vue["twin_id"] for vue in vues} == {"t1", "t2", "t3"}
    assert [c["objet"] for vue in vues if vue["twin_id"] == "t1"
            for c in vue["capacites"]] == ["cap-t1"]
    assert all(vue["capacites"] == [] for vue in vues if vue["twin_id"] != "t1")

    une = projection_twin.projection_tous(conn, TENANT, limite=1)
    assert len(une) == 1


def test_projection_tous_dependants_croises(conn):
    _jumeau(conn, "hub")
    _jumeau(conn, "cli-1")
    _jumeau(conn, "cli-2")
    _claim(conn, TENANT, "cli-1", "DEPEND_DE", "hub", statut="ACCEPTED")
    _claim(conn, TENANT, "cli-2", "APPELLE", "hub", statut="ACCEPTED")

    vues = {vue["twin_id"]: vue for vue in projection_twin.projection_tous(conn, TENANT)}

    assert sorted(d["twin"]["id"] for d in vues["hub"]["dependants"]) == ["cli-1", "cli-2"]


# --- ecarts : la ligne stockée n'est plus la vérité ---


def test_ecarts_divergence_attribut_deduit(conn):
    _jumeau(conn, "app-d", mission="mission stockée")
    _claim(conn, TENANT, "app-d", "A_POUR_MISSION", "mission déduite",
           statut="ACCEPTED")

    rapport = projection_twin.ecarts(conn, TENANT, "app-d")

    assert rapport["stocke"]["mission"] == "mission stockée"
    assert rapport["calcule"]["mission"] == "mission déduite"
    assert rapport["divergence"] == [
        {"champ": "mission", "stocke": "mission stockée",
         "calcule": "mission déduite", "claim_id": rapport["divergence"][0]["claim_id"]}]


def test_ecarts_sujet_denormalise_diverge_apres_renommage(conn):
    _jumeau(conn, "app-r", nom="AncienNom")
    _claim(conn, TENANT, "app-r", "DEPEND_DE", "lib-x", sujet="AncienNom",
           statut="ACCEPTED")
    conn.execute("UPDATE jumeau SET nom = 'NouveauNom' WHERE id = 'app-r'")

    rapport = projection_twin.ecarts(conn, TENANT, "app-r")

    sujet = [d for d in rapport["divergence"] if d["champ"] == "sujet"]
    assert sujet == [{"champ": "sujet", "stocke": "NouveauNom",
                      "calcule": ["AncienNom"], "claim_id": None}]


def test_ecarts_sans_claim_deduit_ne_diverge_pas(conn):
    _jumeau(conn, "app-ok", domaine="À confirmer")
    _claim(conn, TENANT, "app-ok", "REALISE_CAPACITE", "cap-ok", statut="ACCEPTED")

    rapport = projection_twin.ecarts(conn, TENANT, "app-ok")

    assert rapport["divergence"] == []
    assert projection_twin.ecarts(conn, TENANT, "absent") is None


# --- endpoint GET /api/boucle/twins/{id}/projection ---


class _ConnexionPartagee:
    """Rend la connexion du test sans la fermer à la sortie du ``with`` de la route."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *_):
        return False


def _app(conn, monkeypatch):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from meridian.adapters.inbound.http import boucle as boucle_routes

    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.setattr(
        boucle_routes.psycopg, "connect",
        lambda *_, **__: _ConnexionPartagee(conn))
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(boucle_routes.router)
    app.include_router(api)
    return TestClient(app)


def test_endpoint_projection_est_tenant_scopee(conn, monkeypatch):
    _jumeau(conn, "app-h", nom="Application H")
    _claim(conn, TENANT, "app-h", "REALISE_CAPACITE", "cap-h", statut="ACCEPTED")
    client = _app(conn, monkeypatch)

    reponse = client.get("/api/boucle/twins/app-h/projection",
                         headers={"X-Tenant": TENANT})

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["tenant"] == TENANT and corps["twin"] == "app-h"
    assert [c["objet"] for c in corps["projection"]["capacites"]] == ["cap-h"]
    assert corps["projection"]["identite"]["nom"] == "Application H"

    autre = client.get("/api/boucle/twins/app-h/projection",
                       headers={"X-Tenant": AUTRE_TENANT})
    assert autre.status_code == 404

    absent = client.get("/api/boucle/twins/absent/projection",
                        headers={"X-Tenant": TENANT})
    assert absent.status_code == 404


def test_endpoint_ecarts_rend_divergences(conn, monkeypatch):
    _jumeau(conn, "app-g", domaine="À confirmer")
    _claim(conn, TENANT, "app-g", "APPARTIENT_A_DOMAINE", "cartes", statut="ACCEPTED")
    client = _app(conn, monkeypatch)

    reponse = client.get("/api/boucle/twins/app-g/projection/ecarts",
                         headers={"X-Tenant": TENANT})

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["calcule"]["domaine"] == "cartes"
    assert corps["divergence"][0]["champ"] == "domaine"
