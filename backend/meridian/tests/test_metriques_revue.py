"""C3 : métriques de la revue humaine — taux, IC de Wilson, délai médian, repli.

Les tests unitaires tournent sur sqlite (le module est agnostique, comme
``calibration``) ; un test marqué ``besoin_pg`` rejoue le vrai chemin
``depot.reviser`` sur le schéma réel. L'endpoint est testé via un TestClient
dont ``psycopg.connect`` rend la connexion sqlite — même patron que
``test_boucle_routes``.
"""
from datetime import datetime, timedelta, timezone
import os
import sqlite3

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import boucle as boucle_routes
from meridian.adapters.outbound.postgres import metriques_revue
from meridian.adapters.outbound.postgres import signatures_besoins

DSN = os.environ.get("JUMEAU_PG_DSN")
besoin_pg = pytest.mark.skipif(not DSN, reason="JUMEAU_PG_DSN non défini")

MAINTENANT = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
CREE = MAINTENANT - timedelta(days=2)
REVU = MAINTENANT - timedelta(days=1)


@pytest.fixture
def conn_lite():
    connexion = sqlite3.connect(":memory:", check_same_thread=False)
    connexion.execute(
        "CREATE TABLE claim ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " tenant_id TEXT NOT NULL,"
        " statut TEXT NOT NULL DEFAULT 'PROPOSED',"
        " enregistre_le TEXT NOT NULL)"
    )
    connexion.execute(
        "CREATE TABLE revue ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " tenant_id TEXT NOT NULL,"
        " claim_id INTEGER NOT NULL,"
        " acteur TEXT NOT NULL,"
        " decision TEXT NOT NULL,"
        " motif TEXT,"
        " le TEXT NOT NULL)"
    )
    yield connexion
    connexion.close()


def _claim(conn_lite, tenant="banque", statut="PROPOSED", cree=CREE):
    return conn_lite.execute(
        "INSERT INTO claim (tenant_id, statut, enregistre_le) VALUES (?, ?, ?)",
        (tenant, statut, cree)).lastrowid


def _revue(conn_lite, claim_id, decision, le=REVU, tenant="banque", acteur="alice"):
    conn_lite.execute(
        "INSERT INTO revue (tenant_id, claim_id, acteur, decision, le) "
        "VALUES (?, ?, ?, ?, ?)",
        (tenant, claim_id, acteur, decision, le))


def _metriques(conn_lite, tenant="banque", **kwargs):
    return metriques_revue.metriques(
        conn_lite, tenant, maintenant=MAINTENANT, **kwargs)


# --- Comptes, taux et IC ---


def test_taux_et_ic_exactement_calcules(conn_lite):
    for _ in range(6):
        cid = _claim(conn_lite, statut="ACCEPTED")
        _revue(conn_lite, cid, "ACCEPTED")
    for _ in range(2):
        cid = _claim(conn_lite, statut="SUPERSEDED")
        _revue(conn_lite, cid, "CONTESTED")
    for _ in range(2):
        cid = _claim(conn_lite, statut="CONTESTED")
        _revue(conn_lite, cid, "CONTESTED")

    m = _metriques(conn_lite)

    assert m["n"] == 10 and m["total"] == 10
    assert (m["acceptes"], m["corriges"], m["refuses"]) == (6, 2, 2)
    assert m["taux_accepte"] == pytest.approx(0.6)
    assert m["taux_corrige"] == pytest.approx(0.2)
    assert m["taux_refuse"] == pytest.approx(0.2)
    assert m["ic95"]["accepte"] == signatures_besoins.intervalle_wilson(6, 10)
    assert m["ic95"]["corrige"] == signatures_besoins.intervalle_wilson(2, 10)
    assert m["ic95"]["refuse"] == signatures_besoins.intervalle_wilson(2, 10)


def test_jamais_un_taux_sous_le_minimum(conn_lite):
    for _ in range(3):
        cid = _claim(conn_lite, statut="ACCEPTED")
        _revue(conn_lite, cid, "ACCEPTED")

    m = _metriques(conn_lite)

    assert m["n"] == 3 and m["acceptes"] == 3
    assert m["taux_accepte"] is None and m["taux_corrige"] is None
    assert m["taux_refuse"] is None
    assert m["ic95"] == {"accepte": None, "corrige": None, "refuse": None}


def test_un_minimum_explicite_s_applique(conn_lite):
    for _ in range(3):
        cid = _claim(conn_lite, statut="ACCEPTED")
        _revue(conn_lite, cid, "ACCEPTED")

    m = _metriques(conn_lite, minimum=3)
    assert m["taux_accepte"] == pytest.approx(1.0)


def test_revue_vide_rend_des_zeros_jamais_une_erreur(conn_lite):
    m = _metriques(conn_lite)
    assert m["n"] == 0 and m["total"] == 0
    assert (m["acceptes"], m["corriges"], m["refuses"]) == (0, 0, 0)
    assert m["taux_accepte"] is None and m["delai_revu_median_heures"] is None
    assert len(m["par_jour"]) == 31
    assert all(jour["total"] == 0 for jour in m["par_jour"])


def test_le_verdict_debout_est_la_derniere_revue(conn_lite):
    cid = _claim(conn_lite, statut="ACCEPTED")
    _revue(conn_lite, cid, "CONTESTED", le=REVU - timedelta(hours=6))
    _revue(conn_lite, cid, "ACCEPTED", le=REVU)

    m = _metriques(conn_lite)

    assert m["total"] == 2 and m["n"] == 1
    assert m["acceptes"] == 1 and m["refuses"] == 0


# --- Délai médian ---


def test_delai_median_en_heures(conn_lite):
    delais = (2.0, 10.0, 24.0)
    for heures in delais:
        cid = _claim(conn_lite, statut="ACCEPTED", cree=REVU - timedelta(hours=heures))
        _revue(conn_lite, cid, "ACCEPTED", le=REVU)

    m = _metriques(conn_lite, minimum=3)
    assert m["delai_revu_median_heures"] == pytest.approx(10.0)


def test_delai_median_pair_moyenne_les_deux_centres(conn_lite):
    for heures in (4.0, 12.0):
        cid = _claim(conn_lite, statut="ACCEPTED", cree=REVU - timedelta(hours=heures))
        _revue(conn_lite, cid, "ACCEPTED", le=REVU)

    m = _metriques(conn_lite, minimum=2)
    assert m["delai_revu_median_heures"] == pytest.approx(8.0)


# --- Repli : claims décidés sans revue ---


def test_claim_sans_revue_est_mesure_par_son_statut(conn_lite):
    _claim(conn_lite, statut="CONTESTED")
    _claim(conn_lite, statut="SUPERSEDED")
    _claim(conn_lite, statut="INVALIDATED")
    for _ in range(3):
        cid = _claim(conn_lite, statut="ACCEPTED")
        _revue(conn_lite, cid, "ACCEPTED")

    m = _metriques(conn_lite, minimum=3)

    assert m["sans_revue"] == 3
    assert m["n"] == 6
    assert (m["acceptes"], m["corriges"], m["refuses"]) == (3, 1, 2)
    # Le repli n'a pas de date de revue : hors du délai médian.
    assert m["delai_revu_median_heures"] == pytest.approx(24.0)


def test_claims_proposes_comptent_dans_en_attente_pas_dans_n(conn_lite):
    _claim(conn_lite, statut="PROPOSED")
    _claim(conn_lite, statut="PROPOSED")

    m = _metriques(conn_lite)
    assert m["en_attente"] == 2 and m["n"] == 0


# --- Fenêtre et tenant ---


def test_hors_fenetre_n_est_pas_mesure(conn_lite):
    cid = _claim(conn_lite, statut="ACCEPTED", cree=MAINTENANT - timedelta(days=40))
    _revue(conn_lite, cid, "ACCEPTED", le=MAINTENANT - timedelta(days=31))

    m = _metriques(conn_lite, jours=30)
    assert m["n"] == 0 and m["total"] == 0


def test_le_tenant_borne_la_mesure(conn_lite):
    cid = _claim(conn_lite, tenant="autre", statut="ACCEPTED")
    _revue(conn_lite, cid, "ACCEPTED", tenant="autre")
    cid = _claim(conn_lite, tenant="banque", statut="CONTESTED")
    _revue(conn_lite, cid, "CONTESTED", tenant="banque")

    m = _metriques(conn_lite, tenant="banque")
    assert m["n"] == 1 and m["refuses"] == 1 and m["acceptes"] == 0


def test_par_jour_couvre_toute_la_fenetre(conn_lite):
    cid = _claim(conn_lite, statut="ACCEPTED")
    _revue(conn_lite, cid, "ACCEPTED", le=REVU)
    cid = _claim(conn_lite, statut="CONTESTED")
    _revue(conn_lite, cid, "CONTESTED", le=MAINTENANT)

    m = _metriques(conn_lite, jours=7)

    assert len(m["par_jour"]) == 8
    par_jour = {jour["jour"]: jour for jour in m["par_jour"]}
    assert par_jour[REVU.date().isoformat()]["acceptes"] == 1
    jour_fin = par_jour[MAINTENANT.date().isoformat()]
    assert jour_fin["refuses"] == 1 and jour_fin["total"] == 1
    assert sum(jour["total"] for jour in m["par_jour"]) == m["n"]


def test_tenant_obligatoire_et_jours_bornes(conn_lite):
    with pytest.raises(metriques_revue.MetriquesRevueInvalide):
        _metriques(conn_lite, tenant="  ")
    m = _metriques(conn_lite, jours=0)
    assert m["jours"] == 1


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


def _client(monkeypatch, connexion):
    monkeypatch.setenv("JUMEAU_PG_DSN", "postgresql://test/test")
    monkeypatch.delenv("JUMEAU_RLS", raising=False)
    monkeypatch.setattr(
        boucle_routes.psycopg, "connect", lambda *_, **__: _Connexion(connexion))
    return _app()


def test_endpoint_metriques_tenant_scope_et_json(monkeypatch, conn_lite):
    # L'endpoint mesure sur le temps réel : les fixtures datent d'aujourd'hui.
    maintenant = datetime.now(timezone.utc)
    for _ in range(6):
        cid = _claim(conn_lite, tenant="banque", statut="ACCEPTED",
                     cree=maintenant - timedelta(days=2))
        _revue(conn_lite, cid, "ACCEPTED", tenant="banque",
               le=maintenant - timedelta(hours=6))
    for _ in range(4):
        cid = _claim(conn_lite, tenant="autre", statut="CONTESTED",
                     cree=maintenant - timedelta(days=2))
        _revue(conn_lite, cid, "CONTESTED", tenant="autre",
               le=maintenant - timedelta(hours=6))
    client = _client(monkeypatch, conn_lite)

    reponse = client.get("/api/boucle/revue/metriques",
                         headers={"X-Tenant": "banque"})

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["tenant"] == "banque"
    assert corps["n"] == 6 and corps["acceptes"] == 6
    assert corps["taux_accepte"] == pytest.approx(1.0)
    assert corps["ic95"]["accepte"]["bas"] > 0
    # Rien du tenant « autre » ne fuit.
    assert corps["refuses"] == 0


def test_endpoint_sans_dsn_repond_503(monkeypatch):
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)
    reponse = _app().get("/api/boucle/revue/metriques",
                         headers={"X-Tenant": "banque"})
    assert reponse.status_code == 503
    assert "JUMEAU_PG_DSN" in reponse.json()["detail"]


def test_endpoint_revue_vide_repond_200_jamais_500(monkeypatch, conn_lite):
    client = _client(monkeypatch, conn_lite)
    reponse = client.get("/api/boucle/revue/metriques",
                         headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["n"] == 0 and corps["taux_accepte"] is None
    assert corps["delai_revu_median_heures"] is None


def test_endpoint_jours_borne_par_la_validation(monkeypatch, conn_lite):
    client = _client(monkeypatch, conn_lite)
    assert client.get("/api/boucle/revue/metriques",
                      params={"jours": 0}).status_code == 422
    assert client.get("/api/boucle/revue/metriques",
                      params={"jours": 500}).status_code == 422
    reponse = client.get("/api/boucle/revue/metriques", params={"jours": 7},
                         headers={"X-Tenant": "banque"})
    assert reponse.status_code == 200
    assert len(reponse.json()["par_jour"]) == 8


# --- Chemin réel sur le schéma Postgres ---


@besoin_pg
def test_sur_schema_reel_reviser_alimente_la_mesure(conn):
    from meridian.adapters.outbound.postgres import depot
    from meridian.tests.conftest import ACTIVITE, JUMEAU, SOURCE, claim

    # Une seule passe d'enregistrement : une passe suivante fermerait
    # (valide_jusqua) les claims qu'elle n'a pas revus.
    depot.enregistrer(
        conn, JUMEAU, SOURCE,
        [claim("motor", ligne=3), claim("fastapi", ligne=4),
         claim("uvicorn", ligne=5), claim("pydantic", ligne=6)],
        ACTIVITE)
    claims = depot.lister_claims(conn, "tbt")
    depot.reviser(conn, claims[0]["id"], "alice", "ACCEPTED", "vu dans le code")
    depot.reviser(conn, claims[1]["id"], "alice", "CONTESTED", "à corriger")

    m = metriques_revue.metriques(conn, "banque", minimum=2)

    assert m["n"] == 2
    assert m["acceptes"] == 1 and m["refuses"] == 1
    assert m["taux_accepte"] == pytest.approx(0.5)
    assert m["delai_revu_median_heures"] is not None
    # Les autres claims restent PROPOSED, comptés en attente.
    assert m["en_attente"] == len(claims) - 2
    # Un autre tenant ne voit rien.
    vide = metriques_revue.metriques(conn, "tenant-inconnu")
    assert vide["n"] == 0 and vide["en_attente"] == 0
