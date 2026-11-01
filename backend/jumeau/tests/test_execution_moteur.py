import os
import psycopg

from jumeau.execution import depot
from jumeau.execution.moteur import MoteurExecution
from jumeau.execution.modele import AnnulationExecution, CommandeExecution, ErreurTransitoire, EtatRun
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg


def _factory(conn):
    schema = conn.execute("SHOW search_path").fetchone()[0]
    return lambda: psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True,
                                   options=f"-c search_path={schema}")


def _commande(cle="m1", type_="test.echo", payload=None):
    return CommandeExecution(tenant_id="banque", type=type_, idempotency_key=cle,
                             payload=payload or {"x": 1}, acteur="test")


def test_moteur_succes(conn):
    vus = []
    def executer(run):
        vus.append(run["run_id"])
        return {"valeur": run["payload"]["x"] * 2}

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test")
    run, cree = moteur.creer(_commande())
    assert cree is True
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.SUCCEEDED.value
    assert fini["resultat"] == {"valeur": 2}
    assert vus == [run["run_id"]]
    assert moteur.traiter_prochain() is None


def test_moteur_retry_puis_succes(conn):
    appels = {"n": 0}
    def executer(run):
        appels["n"] += 1
        if appels["n"] == 1:
            raise ErreurTransitoire("temporaire")
        return {"ok": True}

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test")
    moteur.creer(_commande())
    attendu = moteur.traiter_prochain()
    assert attendu["etat"] == EtatRun.WAITING_RETRY.value
    conn.execute("UPDATE execution_timer SET due_at = now() - interval '1 second'")
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.SUCCEEDED.value
    assert appels["n"] == 2


def test_moteur_echec_final(conn):
    moteur = MoteurExecution(_factory(conn), lambda run: (_ for _ in ()).throw(RuntimeError("dur")),
                             worker_id="w-test")
    run, _ = moteur.creer(_commande())
    conn.execute("UPDATE execution_run SET max_tentatives = 1 WHERE run_id = %s", (run["run_id"],))
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.FAILED.value
    assert "RuntimeError" in fini["erreur"]


def test_moteur_annulation_avant_execution(conn):
    appels = {"n": 0}
    def executer(run):
        appels["n"] += 1
        return {}

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test")
    run, _ = moteur.creer(_commande())
    annule = moteur.annuler("banque", run["run_id"])
    assert annule["etat"] == EtatRun.CANCELLED.value
    assert moteur.traiter_prochain() is None
    assert appels["n"] == 0


def test_moteur_annulation_pendant_execution(conn):
    def executer(run):
        with _factory(conn)() as c:
            depot.demander_annulation(c, "banque", run["run_id"])
        return {"trop": "tard"}

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test")
    run, _ = moteur.creer(_commande())
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.CANCELLED.value


def test_heartbeat_run_long(conn):
    def executer(run):
        import time
        time.sleep(1.2)
        return {"long": True}

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test", bail_secondes=1)
    moteur.creer(_commande("long"))
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.SUCCEEDED.value


def test_bail_expire_reprise_et_fencing(conn):
    moteur = MoteurExecution(_factory(conn), lambda run: {"ok": True}, worker_id="w-old", bail_secondes=1)
    run, _ = moteur.creer(_commande("reprise"))
    with _factory(conn)() as c:
        pris = depot.reclamer_run(c, "w-old", 1)
        token_ancien = int(pris["fencing_token"])
        c.execute("UPDATE execution_run SET bail_jusqu_a = now() - interval '1 hour' WHERE run_id = %s",
                  (run["run_id"],))
        depot.reprendre_baux_expires(c)
        assert depot.obtenir_run(c, "banque", run["run_id"])["etat"] == EtatRun.QUEUED.value
        repris = depot.reclamer_run(c, "w-new", 30)
        assert repris["fencing_token"] == token_ancien + 1

    with _factory(conn)() as c:
        try:
            depot.terminer(c, "banque", run["run_id"], "w-old", token_ancien, EtatRun.SUCCEEDED, {})
        except depot.TransitionInvalide:
            pass
        else:
            raise AssertionError("l'ancien worker ne doit plus pouvoir terminer")


def test_terminer_refuse_bail_expire(conn):
    moteur = MoteurExecution(_factory(conn), lambda run: {}, worker_id="w-test")
    run, _ = moteur.creer(_commande("bail"))
    with _factory(conn)() as c:
        pris = depot.reclamer_run(c, "w-test", 30)
        c.execute("UPDATE execution_run SET bail_jusqu_a = now() - interval '1 hour' WHERE run_id = %s",
                  (run["run_id"],))
        try:
            depot.terminer(c, "banque", run["run_id"], "w-test", int(pris["fencing_token"]),
                           EtatRun.SUCCEEDED, {})
        except depot.TransitionInvalide:
            pass
        else:
            raise AssertionError("un bail expiré doit refuser la terminaison")


def test_annulation_puis_echec_transitoire(conn):
    def executer(run):
        with _factory(conn)() as c:
            depot.demander_annulation(c, "banque", run["run_id"])
        raise ErreurTransitoire("temporaire")

    moteur = MoteurExecution(_factory(conn), executer, worker_id="w-test")
    run, _ = moteur.creer(_commande("annule-retry"))
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.CANCELLED.value
    with _factory(conn)() as c:
        assert c.execute("SELECT count(*) FROM execution_timer WHERE run_id = %s", (run["run_id"],)).fetchone()[0] == 0


def test_moteur_annulation_signalee_par_executeur(conn):
    moteur = MoteurExecution(_factory(conn), lambda run: (_ for _ in ()).throw(AnnulationExecution("stop")),
                             worker_id="w-test")
    run, _ = moteur.creer(_commande("stop-ex"))
    fini = moteur.traiter_prochain()
    assert fini["etat"] == EtatRun.CANCELLED.value


def test_moteur_tenant_isole(conn):
    moteur = MoteurExecution(_factory(conn), lambda run: {}, worker_id="w-test")
    run, _ = moteur.creer(_commande())
    assert moteur.lire("autre", run["run_id"]) is None
