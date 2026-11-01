"""Journal d'étapes, checkpoints et reprise après crash."""
import os

import psycopg
import pytest

from jumeau.execution import depot
from jumeau.execution.modele import AnnulationExecution, CommandeExecution, EtatRun
from jumeau.execution.processus import ProcessManager
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def _commande(cle="etape-1"):
    return CommandeExecution(tenant_id="banque", type="test.multi", idempotency_key=cle,
                             payload={"x": 1}, acteur="test")


def _run_reclame(conn, cle="etape-1", worker="w-test"):
    run, _ = depot.creer_run(conn, _commande(cle))
    pris = depot.reclamer_run(conn, worker, 30)
    assert pris["run_id"] == run["run_id"]
    return pris


def test_process_manager_checkpoint_et_reprise(conn):
    run = _run_reclame(conn, "checkpoint")
    appels = {"a": 0, "b": 0}

    def a(_contexte):
        appels["a"] += 1
        return {"valeur": "a"}

    def b(_contexte):
        appels["b"] += 1
        raise RuntimeError("crash simulé")

    manager = ProcessManager(_factory(conn), run)
    with pytest.raises(RuntimeError):
        manager.executer([("a", a), ("b", b)])

    etapes = {e["nom"]: e for e in depot.etapes_run(conn, "banque", run["run_id"])}
    assert etapes["a"]["etat"] == "TERMINE"
    assert etapes["a"]["sortie"] == {"valeur": "a"}
    assert etapes["b"]["etat"] == "ECHEC"
    assert "crash simulé" in etapes["b"]["erreur"]

    def b_reprise(_contexte):
        appels["b"] += 1
        return {"valeur": "b"}

    repris = ProcessManager(_factory(conn), run).executer(
        [("a", a), ("b", b_reprise)])
    assert appels == {"a": 1, "b": 2}
    assert repris["reprises"] == ["a"]
    assert repris["resultats"] == {"a": {"valeur": "a"}, "b": {"valeur": "b"}}

    etapes = {e["nom"]: e for e in depot.etapes_run(conn, "banque", run["run_id"])}
    assert etapes["b"]["etat"] == "TERMINE"
    assert etapes["b"]["sortie"] == {"valeur": "b"}

    # Un second passage ne rejoue plus aucune étape terminée.
    encore = ProcessManager(_factory(conn), run).executer([("a", a), ("b", b_reprise)])
    assert appels == {"a": 1, "b": 2}
    assert encore["reprises"] == ["a", "b"]


def test_annulation_cooperative_entre_etapes(conn):
    run = _run_reclame(conn, "annulation-etapes")
    appels = {"n": 0}

    def verifier():
        appels["n"] += 1
        return appels["n"] >= 2

    manager = ProcessManager(_factory(conn), run, verifier_annulation=verifier)
    with pytest.raises(AnnulationExecution):
        manager.executer([("a", lambda: {"ok": True}), ("b", lambda: {"ok": True})])

    etapes = {e["nom"]: e for e in depot.etapes_run(conn, "banque", run["run_id"])}
    assert etapes["a"]["etat"] == "TERMINE"
    assert "b" not in etapes


def test_reprise_apres_bail_expire_rejoue_etape_en_cours(conn):
    run = _run_reclame(conn, "bail-etape", worker="w-old")
    manager = ProcessManager(_factory(conn), run)
    manager.demarrer("specialistes", seq=1, entree={"run_id": run["run_id"]})
    assert depot.obtenir_etape(
        conn, "banque", run["run_id"], "specialistes")["etat"] == "EN_COURS"

    conn.execute(
        "UPDATE execution_run SET bail_jusqu_a = now() - interval '1 hour' WHERE run_id = %s",
        (run["run_id"],),
    )
    depot.reprendre_baux_expires(conn)
    assert depot.obtenir_run(conn, "banque", run["run_id"])["etat"] == EtatRun.QUEUED.value

    repris = depot.reclamer_run(conn, "w-new", 30)
    resultat = ProcessManager(_factory(conn), repris).executer(
        [("specialistes", lambda: {"dossier": "repris"})])
    assert resultat["reprises"] == []
    etape = depot.obtenir_etape(conn, "banque", run["run_id"], "specialistes")
    assert etape["etat"] == "TERMINE"
    assert etape["sortie"] == {"dossier": "repris"}


def test_contrat_journaliser_etape_et_connexion_directe(conn):
    run = _run_reclame(conn, "contrat-etape")
    depot.journaliser_etape(conn, "banque", run["run_id"], "contexte",
                            etat="EN_COURS", seq=0, entree={"q": "x"})
    depot.journaliser_etape(conn, "banque", run["run_id"], "contexte",
                            etat="TERMINE", sortie={"ok": True})
    etape = depot.obtenir_etape(conn, "banque", run["run_id"], "contexte")
    assert etape["etat"] == "TERMINE"
    assert etape["sortie"] == {"ok": True}

    # Une connexion directe est acceptée ; le manager ne la ferme pas.
    manager = ProcessManager(conn, run)
    resultat = manager.executer([("contexte", lambda: {"relance": True})])
    assert resultat["reprises"] == ["contexte"]
    assert resultat["resultats"]["contexte"] == {"ok": True}
    assert conn.execute("SELECT 1").fetchone()[0] == 1
