import os

import psycopg
import pytest

from jumeau.execution import depot
from jumeau.execution.modele import (
    ApprobationRequise,
    CommandeExecution,
    ErreurTransitoire,
    OutilRefuse,
)
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


def _commande(cle, tenant="banque"):
    return CommandeExecution(tenant_id=tenant, type="test.effet", idempotency_key=cle,
                             payload={"x": 1}, acteur="test")


def _run_reclame(conn, cle="g1", tenant="banque"):
    run, _ = depot.creer_run(conn, _commande(cle, tenant))
    with _factory(conn)() as c:
        pris = depot.reclamer_run(c, "w-test", 30)
    assert pris["run_id"] == run["run_id"]
    return pris


def _gateway(conn, transport, allowlist=None, outils=None):
    return ToolGateway(
        _factory(conn),
        allowlist=allowlist or ALLOWLIST,
        outils=outils or {"facturation": OUTIL},
        transport=transport,
        timeout_s=1.0,
    )


def test_lecture_directe_sans_approbation_et_rejeu(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport)
    run = _run_reclame(conn, "lecture")

    effet = gateway.proposer(run, etape="e1", outil="facturation", operation="lire",
                             cible="42", payload={"q": "x"})

    assert effet["statut"] == "EXECUTE"
    assert transport.appels[0]["method"] == "GET"
    assert transport.appels[0]["url"].endswith("/objets/42")
    assert transport.appels[0]["params"] == {"q": "x"}
    assert depot.obtenir_approbation(
        conn, "banque", run["run_id"], "e1", "42", "lire") is None

    encore = gateway.proposer(run, etape="e1", outil="facturation", operation="lire",
                              cible="42", payload={"q": "x"})
    assert encore["resultat"] == effet["resultat"]
    assert len(transport.appels) == 1


def test_ecriture_idempotente_apres_approbation(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport)
    run = _run_reclame(conn, "ecriture")

    with pytest.raises(ApprobationRequise):
        gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                         cible="42", payload={"montant": 10})

    effet = depot.obtenir_effet(conn, "banque", run["run_id"], "e1", "42", "ecrire")
    assert effet["statut"] == "PROPOSE"
    assert transport.appels == []

    depot.decider_approbation(conn, "banque", run["run_id"], approuve=True, acteur="chef")

    premier = gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                               cible="42", payload={"montant": 10})
    second = gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                              cible="42", payload={"montant": 10})

    assert premier["statut"] == "EXECUTE"
    assert second["statut"] == "EXECUTE"
    assert premier["resultat"] == second["resultat"]
    assert len(transport.appels) == 1
    assert transport.appels[0]["json"] == {"montant": 10}


def test_allowlist_refuse_tenant_acteur_outil_et_operation(conn):
    transport = TransportFactice()
    gateway = _gateway(conn, transport, allowlist={
        "banque": {
            "test": {
                "facturation": {
                    "lecture": ("lire", "inconnue"),
                    "ecriture": ("ecrire",),
                },
            },
        },
    })
    run = _run_reclame(conn, "allowlist")

    for champ, valeur in (("tenant_id", "autre"), ("acteur", "intrus")):
        intrus = dict(run)
        intrus[champ] = valeur
        with pytest.raises(OutilRefuse):
            gateway.proposer(intrus, etape="e1", outil="facturation", operation="lire",
                             cible="42")

    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e1", outil="inconnu", operation="lire", cible="42")
    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e1", outil="facturation", operation="supprimer",
                         cible="42")
    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e1", outil="facturation", operation="inconnue",
                         cible="42")

    assert transport.appels == []


def test_timeout_leve_une_erreur_transitoire(conn):
    gateway = _gateway(conn, TransportFactice(erreur=TimeoutError("lent")))
    run = _run_reclame(conn, "timeout")

    with pytest.raises(ErreurTransitoire):
        gateway.proposer(run, etape="e1", outil="facturation", operation="lire", cible="42")

    assert depot.obtenir_effet(conn, "banque", run["run_id"], "e1", "42", "lire") is None


def test_echec_apres_approbation_reste_rejouable(conn):
    transport = TransportFactice(erreur=TimeoutError("lent"))
    gateway = _gateway(conn, transport)
    run = _run_reclame(conn, "echec")

    with pytest.raises(ApprobationRequise):
        gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                         cible="42", payload={"montant": 10})
    depot.decider_approbation(conn, "banque", run["run_id"], approuve=True, acteur="chef")

    with pytest.raises(ErreurTransitoire):
        gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                         cible="42", payload={"montant": 10})

    effet = depot.obtenir_effet(conn, "banque", run["run_id"], "e1", "42", "ecrire")
    assert effet["statut"] == "APPROUVE"
    assert "timeout" in effet["erreur"]

    transport.erreur = None
    effet = gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                             cible="42", payload={"montant": 10})
    assert effet["statut"] == "EXECUTE"
    assert len(transport.appels) == 2


def test_allowlist_env_et_refus_par_defaut(conn, monkeypatch):
    import json

    monkeypatch.delenv("EXECUTION_ALLOWLIST", raising=False)
    transport = TransportFactice()
    run = _run_reclame(conn, "env-vide")
    gateway = ToolGateway(_factory(conn), outils={"facturation": OUTIL}, transport=transport)
    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e1", outil="facturation", operation="lire", cible="42")
    assert transport.appels == []

    monkeypatch.setenv("EXECUTION_ALLOWLIST", json.dumps({
        "banque": {"test": {"facturation": {
            "lecture": ["lire"], "ecriture": [],
        }}},
    }))
    gateway = ToolGateway(_factory(conn), outils={"facturation": OUTIL}, transport=transport)
    lecture = gateway.proposer(run, etape="e1", outil="facturation", operation="lire",
                               cible="42")
    assert lecture["statut"] == "EXECUTE"
    assert len(transport.appels) == 1

    # Une écriture absente de la liste `ecriture` reste refusée, même si l'outil
    # est autorisé en lecture.
    with pytest.raises(OutilRefuse):
        gateway.proposer(run, etape="e1", outil="facturation", operation="ecrire",
                         cible="42", payload={"montant": 10})
    assert len(transport.appels) == 1

    monkeypatch.setenv("EXECUTION_ALLOWLIST", "{pas du json")
    with pytest.raises(ValueError):
        ToolGateway(_factory(conn), outils={"facturation": OUTIL})
