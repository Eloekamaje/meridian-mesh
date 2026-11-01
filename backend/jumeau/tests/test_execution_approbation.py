import os

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jumeau.execution import depot
from jumeau.execution.modele import (
    CommandeExecution,
    ConflitApprobation,
    EtatRun,
    OutilRefuse,
    RunIntrouvable,
)
from jumeau.execution.moteur import MoteurExecution
from jumeau.execution.routes import construire_router
from jumeau.execution.tool_gateway import OutilHTTP, ToolGateway
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg

OUTIL = OutilHTTP(
    base_url="https://outils.test",
    operations={
        "lire": ("GET", "/objets/{cible}"),
        "ecrire": ("POST", "/objets/{cible}"),
    },
)

ALLOWLIST = {
    "banque": {
        "test": {
            "facturation": {
                "lecture": ("lire",),
                "ecriture": ("ecrire",),
            },
        },
    },
}


class TransportFactice:
    def __init__(self, reponse=None, erreur=None):
        self.appels = []
        self.erreur = erreur
        self.reponse = reponse if reponse is not None else {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "content": {"ok": True},
        }

    def __call__(self, method, url, **kwargs):
        self.appels.append({"method": method, "url": url, **kwargs})
        if self.erreur is not None:
            raise self.erreur
        return self.reponse


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def _commande(cle, type_="test.effet"):
    return CommandeExecution(tenant_id="banque", type=type_, idempotency_key=cle,
                             payload={"x": 1}, acteur="test")


def _gateway(conn, transport):
    return ToolGateway(
        _factory(conn),
        allowlist=ALLOWLIST,
        outils={"facturation": OUTIL},
        transport=transport,
        timeout_s=1.0,
    )


def _client(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]

    def connecter():
        return psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                               options=f"-c search_path={schema}")

    app = FastAPI()
    app.include_router(construire_router(
        connect=connecter,
        resoudre_tenant=lambda request, x_tenant: x_tenant or "banque",
    ), prefix="/api")
    return TestClient(app)


def _executeur(gateway):
    def executer(run):
        return gateway.proposer(run, etape="paiement", outil="facturation",
                                operation="ecrire", cible="facture-1",
                                payload={"montant": 10})
    return executer


def _mettre_en_attente(conn, client, cle):
    run = client.post("/api/runs", json={"type": "test.effet", "idempotency_key": cle},
                      headers={"X-Tenant": "banque"}).json()
    pris = depot.reclamer_run(conn, "w-test", 30)
    assert pris["run_id"] == run["run_id"]
    depot.proposer_effet(
        conn, "banque", run["run_id"], etape="paiement", cible="facture-1",
        operation="ecrire", outil="facturation", acteur="test", payload={"montant": 10},
        worker_id="w-test", fencing_token=int(pris["fencing_token"]),
    )
    return run


def test_approbation_reprend_le_run_et_execute_une_fois(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport)
    moteur = MoteurExecution(_factory(conn), _executeur(gateway), worker_id="w-test")
    run, _ = moteur.creer(_commande("appro"))

    attente = moteur.traiter_prochain()
    assert attente["etat"] == EtatRun.WAITING_APPROVAL.value
    assert transport.appels == []
    evts = [e["type"] for e in depot.evenements(conn, "banque", run["run_id"])]
    assert "run.waiting_approval" in evts
    assert "execution.effet.propose" in evts

    decision = depot.decider_approbation(
        conn, "banque", run["run_id"], approuve=True, acteur="chef", motif="ok")
    assert decision["run"]["etat"] == EtatRun.QUEUED.value
    assert decision["effet"]["statut"] == "APPROUVE"
    assert decision["approbation"]["acteur"] == "chef"
    assert decision["approbation"]["demandeur"] == "test"

    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.SUCCEEDED.value
    assert len(transport.appels) == 1
    effet = depot.obtenir_effet(
        conn, "banque", run["run_id"], "paiement", "facture-1", "ecrire")
    assert effet["statut"] == "EXECUTE"
    evts = [e["type"] for e in depot.evenements(conn, "banque", run["run_id"])]
    assert "execution.effet.approuve" in evts
    assert "run.queued" in evts
    assert "execution.effet.execute" in evts
    publies = []
    depot.publier_outbox(conn, lambda ligne: publies.append(ligne["type"]))
    assert {"run.waiting_approval", "execution.effet.approuve",
            "run.queued", "execution.effet.execute"} <= set(publies)


def test_rejet_annule_le_run_sans_appel_http(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport)
    moteur = MoteurExecution(_factory(conn), _executeur(gateway), worker_id="w-test")
    run, _ = moteur.creer(_commande("rejet"))

    attente = moteur.traiter_prochain()
    assert attente["etat"] == EtatRun.WAITING_APPROVAL.value

    decision = depot.decider_approbation(
        conn, "banque", run["run_id"], approuve=False, acteur="chef", motif="non")
    assert decision["run"]["etat"] == EtatRun.CANCELLED.value
    assert decision["run"]["erreur"] == "non"
    assert decision["effet"]["statut"] == "REJETE"
    assert moteur.traiter_prochain() is None
    assert transport.appels == []
    evts = [e["type"] for e in depot.evenements(conn, "banque", run["run_id"])]
    assert "execution.effet.rejete" in evts
    assert "run.cancelled" in evts


def test_approbation_idempotente_et_conflit(conn):
    client = _client(conn)
    run = _mettre_en_attente(conn, client, "appro-idem")
    premier = depot.decider_approbation(
        conn, "banque", run["run_id"], approuve=True, acteur="chef")
    encore = depot.decider_approbation(
        conn, "banque", run["run_id"], approuve=True, acteur="chef")
    assert premier["run"]["etat"] == encore["run"]["etat"] == EtatRun.QUEUED.value
    with pytest.raises(ConflitApprobation):
        depot.decider_approbation(
            conn, "banque", run["run_id"], approuve=False, acteur="autre")


def test_route_approbation_approuve_et_rejette(conn):
    client = _client(conn)
    run = _mettre_en_attente(conn, client, "route-appro")

    approuve = client.post(f"/api/runs/{run['run_id']}/approval",
                           json={"approuve": True}, headers={"X-Tenant": "banque"})
    assert approuve.status_code == 200, approuve.text
    corps = approuve.json()
    assert corps["run"]["etat"] == EtatRun.QUEUED.value
    assert corps["effet"]["statut"] == "APPROUVE"
    assert corps["approbation"]["acteur"] == "demo"
    assert corps["approbation"]["demandeur"] == "test"

    encore = client.post(f"/api/runs/{run['run_id']}/approval",
                         json={"approuve": True}, headers={"X-Tenant": "banque"})
    assert encore.status_code == 200
    conflit = client.post(f"/api/runs/{run['run_id']}/approval",
                          json={"approuve": False}, headers={"X-Tenant": "banque"})
    assert conflit.status_code == 409

    moteur = MoteurExecution(_factory(conn), lambda _run: {}, worker_id="w-test")
    assert moteur.traiter_prochain()["etat"] == EtatRun.SUCCEEDED.value

    rejet_run = _mettre_en_attente(conn, client, "route-rejet")
    rejet = client.post(f"/api/runs/{rejet_run['run_id']}/approval",
                        json={"decision": "rejeter", "motif": "non"},
                        headers={"X-Tenant": "banque"})
    assert rejet.status_code == 200, rejet.text
    assert rejet.json()["run"]["etat"] == EtatRun.CANCELLED.value
    assert rejet.json()["effet"]["statut"] == "REJETE"


def test_route_approbation_tenant_isole_et_introuvable(conn):
    client = _client(conn)
    run = _mettre_en_attente(conn, client, "route-isole")

    autre = client.post(f"/api/runs/{run['run_id']}/approval",
                        json={"approuve": True}, headers={"X-Tenant": "autre"})
    assert autre.status_code == 404
    with pytest.raises(RunIntrouvable):
        depot.decider_approbation(
            conn, "autre", run["run_id"], approuve=True, acteur="chef")
    assert depot.obtenir_effet(
        conn, "autre", run["run_id"], "paiement", "facture-1", "ecrire") is None

    absent = client.post("/api/runs/inconnu/approval",
                         json={"approuve": True}, headers={"X-Tenant": "banque"})
    assert absent.status_code == 404


def test_gateway_refuse_un_autre_tenant_avant_toute_ecriture(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport)
    run = {"tenant_id": "autre", "acteur": "test", "run_id": "r"}
    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e", outil="facturation", operation="ecrire",
                         cible="c", payload={"m": 1})
    assert transport.appels == []


def test_route_liste_approbations_filtre_et_sans_payload(conn):
    client = _client(conn)
    attente = _mettre_en_attente(conn, client, "liste-attente")
    decide = _mettre_en_attente(conn, client, "liste-decide")
    depot.decider_approbation(conn, "banque", decide["run_id"], approuve=True, acteur="chef")

    liste = client.get("/api/runs/approvals", headers={"X-Tenant": "banque"})
    assert liste.status_code == 200, liste.text
    corps = liste.json()
    assert corps["limite"] == 50
    assert [item["run_id"] for item in corps["approbations"]] == [attente["run_id"]]
    assert all("payload" not in item for item in corps["approbations"])
    assert all(item["statut"] == "PROPOSE" for item in corps["approbations"])

    filtre_run = client.get(f"/api/runs/approvals?run_id={attente['run_id']}",
                            headers={"X-Tenant": "banque"})
    assert [item["run_id"] for item in filtre_run.json()["approbations"]] == [attente["run_id"]]

    filtres = client.get("/api/runs/approvals?statut=APPROUVE&limite=10",
                         headers={"X-Tenant": "banque"})
    assert [item["run_id"] for item in filtres.json()["approbations"]] == [decide["run_id"]]

    detail = client.get(
        f"/api/runs/approvals/{corps['approbations'][0]['id']}",
        headers={"X-Tenant": "banque"})
    assert detail.status_code == 200
    assert detail.json()["approbation"]["run_id"] == attente["run_id"]
    assert "payload" not in detail.json()["approbation"]

    autre = client.get("/api/runs/approvals", headers={"X-Tenant": "autre"})
    assert autre.status_code == 200
    assert autre.json()["approbations"] == []

    invalide = client.get("/api/runs/approvals?limite=0", headers={"X-Tenant": "banque"})
    assert invalide.status_code == 422
