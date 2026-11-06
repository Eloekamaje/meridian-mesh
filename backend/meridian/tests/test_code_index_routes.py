"""Routes de lecture de l'index legacy : résumé, couverture, observations et liens."""
import os

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meridian.adapters.inbound.http import code_index as routes
from meridian.adapters.outbound.postgres import code_index_store
from meridian.application.code_links import Link
from meridian.domain.code_index import CouvertureFichier, Observation
from meridian.tests.conftest import besoin_pg

TENANT = "banque"
JUMEAU = "tbt"
ENTETES = {"X-Tenant": TENANT}
URL = f"/api/jumeaux/{JUMEAU}/code-index"


class FausseConnexion:
    def __init__(self):
        self.fermee = False

    def close(self):
        self.fermee = True


def _client(connect=None):
    app = FastAPI()
    app.include_router(routes.construire_router(
        connect=connect or FausseConnexion,
        resoudre_tenant=lambda request, x_tenant: x_tenant or TENANT,
    ), prefix="/api")
    return TestClient(app)


def test_limite_invalide_rend_400_sans_lire_la_base(monkeypatch):
    appels = []
    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id",
                        lambda *args: appels.append(args))
    client = _client()

    for valeur in ("0", "-1", "abc", "1001"):
        for ressource in ("coverage", "observations", "links"):
            reponse = client.get(f"{URL}/{ressource}?limite={valeur}", headers=ENTETES)
            assert reponse.status_code == 400, reponse.text
    assert appels == []


def test_jumeau_inconnu_ou_d_un_autre_tenant_rend_404(monkeypatch):
    client = _client()

    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id", lambda conn, jid: None)
    assert client.get(f"{URL}/resume", headers=ENTETES).status_code == 404

    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id",
                        lambda conn, jid: {"tenant_id": "assurance"})
    for ressource in ("resume", "coverage", "observations", "links"):
        assert client.get(f"{URL}/{ressource}", headers=ENTETES).status_code == 404


def test_aucune_route_d_ecriture(monkeypatch):
    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id",
                        lambda conn, jid: {"tenant_id": TENANT})
    client = _client()

    for methode in ("post", "put", "patch", "delete"):
        assert getattr(client, methode)(f"{URL}/resume", headers=ENTETES).status_code == 405


def test_resume_rend_les_compteurs_du_magasin(monkeypatch):
    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id",
                        lambda conn, jid: {"tenant_id": TENANT})
    appels = {}

    def resume(conn, tenant, jumeau):
        appels.update({"tenant": tenant, "jumeau": jumeau})
        return {"observations": {"total": 3},
                "couverture": {"total": 2, "fichiers_couverts": 2},
                "liens": {"total": 1}}

    monkeypatch.setattr(routes.code_index_store, "resume", resume)
    reponse = _client().get(f"{URL}/resume", headers=ENTETES)

    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["tenant"] == TENANT and corps["jumeau_id"] == JUMEAU
    assert corps["observations"] == {"total": 3}
    assert corps["couverture"]["fichiers_couverts"] == 2
    assert corps["liens"] == {"total": 1}
    assert appels == {"tenant": TENANT, "jumeau": JUMEAU}


def test_les_lectures_transmettent_les_filtres_et_la_limite(monkeypatch):
    monkeypatch.setattr(routes.jumeau_depot, "jumeau_par_id",
                        lambda conn, jid: {"tenant_id": TENANT})
    appels = {}

    def couverture(conn, tenant, jumeau, statut=None, limite=100):
        appels["couverture"] = (tenant, jumeau, statut, limite)
        return [{"file": "src/A.java", "status": "indexe"}]

    def observations(conn, tenant, jumeau, kind=None, fichier=None, limite=100):
        appels["observations"] = (tenant, jumeau, kind, fichier, limite)
        return [{"file": "src/A.java", "kind": "java_type"}]

    def liens(conn, tenant, jumeau, kind=None, limite=100):
        appels["liens"] = (tenant, jumeau, kind, limite)
        return [{"kind": "java_to_jpa_entity"}]

    monkeypatch.setattr(routes.code_index_store, "lire_couverture", couverture)
    monkeypatch.setattr(routes.code_index_store, "lire_observations", observations)
    monkeypatch.setattr(routes.code_index_store, "lire_liens", liens)
    client = _client()

    reponse = client.get(f"{URL}/coverage?statut=indexe&limite=7", headers=ENTETES)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["couverture"] == [{"file": "src/A.java", "status": "indexe"}]
    assert reponse.json()["limite"] == 7

    reponse = client.get(f"{URL}/observations?kind=java_type&fichier=src/A.java&limite=9",
                         headers=ENTETES)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["observations"] == [{"file": "src/A.java", "kind": "java_type"}]

    reponse = client.get(f"{URL}/links?kind=java_to_jpa_entity&limite=4", headers=ENTETES)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["liens"] == [{"kind": "java_to_jpa_entity"}]

    assert appels == {
        "couverture": (TENANT, JUMEAU, "indexe", 7),
        "observations": (TENANT, JUMEAU, "java_type", "src/A.java", 9),
        "liens": (TENANT, JUMEAU, "java_to_jpa_entity", 4),
    }


def _client_postgres(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                               options=f"-c search_path={schema}")

    return _client(connecter)


@besoin_pg
def test_les_routes_lisent_les_donnees_persistees(conn):
    conn.execute("INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s)",
                 (JUMEAU, TENANT, "TBT", "equipe-tbt"))
    code_index_store.remplacer(
        conn, TENANT, JUMEAU,
        [Observation(provider="java", parser="javaparser", parser_version="1",
                     file="src/A.java", language="java", kind="java_type",
                     symbol="A", start=1, end=5, commit="abc",
                     attributes={"lignes": 5}, confidence=0.8)],
        [CouvertureFichier(file="src/A.java", language="java", parser="javaparser",
                           statut="indexe")],
        [Link(kind="java_to_jpa_entity", source_file="src/A.java", source_symbol="A",
              target_file="src/A.java", target_symbol="A.entity",
              attributes={}, confidence=0.7, status="inferred", evidence={})])
    client = _client_postgres(conn)

    resume = client.get(f"{URL}/resume", headers=ENTETES)
    assert resume.status_code == 200, resume.text
    assert resume.json()["observations"]["total"] == 1
    assert resume.json()["couverture"]["fichiers_indexes"] == 1
    assert resume.json()["liens"]["par_kind"] == {"java_to_jpa_entity": 1}

    couverture = client.get(f"{URL}/coverage?statut=indexe", headers=ENTETES)
    assert couverture.status_code == 200, couverture.text
    assert couverture.json()["couverture"][0]["file"] == "src/A.java"

    observations = client.get(f"{URL}/observations?kind=java_type&fichier=src/A.java",
                              headers=ENTETES)
    assert observations.status_code == 200, observations.text
    assert observations.json()["observations"][0]["symbol"] == "A"

    liens = client.get(f"{URL}/links?kind=java_to_jpa_entity", headers=ENTETES)
    assert liens.status_code == 200, liens.text
    assert liens.json()["liens"][0]["source_symbol"] == "A"

    assert client.get(f"{URL}/resume", headers={"X-Tenant": "assurance"}).status_code == 404
    assert client.get("/api/jumeaux/inconnu/code-index/resume",
                      headers=ENTETES).status_code == 404
