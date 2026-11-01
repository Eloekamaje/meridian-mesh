import os

import psycopg

from jumeau.execution import depot
from jumeau.execution.modele import CommandeExecution, EtatRun
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg


def commande(cle="k1", type_="test.echo", payload=None):
    return CommandeExecution(
        tenant_id="banque", type=type_, payload=payload or {"x": 1},
        idempotency_key=cle, acteur="test",
    )


def test_creation_idempotente_et_journal(conn):
    run, cree = depot.creer_run(conn, commande())
    assert cree is True
    assert run["etat"] == EtatRun.QUEUED.value
    assert run["tentative"] == 0

    encore, cree = depot.creer_run(conn, commande())
    assert cree is False
    assert encore["run_id"] == run["run_id"]

    evts = depot.evenements(conn, "banque", run["run_id"])
    assert [e["type"] for e in evts] == ["run.queued"]
    vus = []
    assert depot.publier_outbox(conn, lambda ligne: vus.append(ligne["type"])) == 1
    assert vus == ["run.queued"]


def test_claim_bail_fencing_et_fin(conn):
    run, _ = depot.creer_run(conn, commande())
    pris = depot.reclamer_run(conn, "worker-a", 30)
    assert pris["run_id"] == run["run_id"]
    assert pris["etat"] == EtatRun.RUNNING.value
    assert pris["tentative"] == 1
    assert pris["fencing_token"] == 1
    assert depot.reclamer_run(conn, "worker-b", 30) is None

    assert depot.renouveler_bail(conn, "banque", run["run_id"], "worker-a", 1)
    fini = depot.terminer(conn, "banque", run["run_id"], "worker-a", 1,
                          EtatRun.SUCCEEDED, resultat={"ok": True})
    assert fini["etat"] == EtatRun.SUCCEEDED.value
    assert fini["bail_proprietaire"] is None
    assert depot.reclamer_run(conn, "worker-b", 30) is None


def test_fencing_token_perime(conn):
    run, _ = depot.creer_run(conn, commande())
    depot.reclamer_run(conn, "worker-a", 30)
    try:
        depot.terminer(conn, "banque", run["run_id"], "worker-a", 0,
                       EtatRun.SUCCEEDED, resultat={})
    except depot.TransitionInvalide:
        pass
    else:
        raise AssertionError("un fencing token périmé doit être refusé")


def test_annulation_en_file(conn):
    run, _ = depot.creer_run(conn, commande())
    annule = depot.demander_annulation(conn, "banque", run["run_id"])
    assert annule["etat"] == EtatRun.CANCELLED.value
    assert annule["cancel_requested_at"] is not None
    evts = [e["type"] for e in depot.evenements(conn, "banque", run["run_id"])]
    assert evts == ["run.queued", "run.cancel_requested", "run.cancelled"]
    assert depot.reclamer_run(conn, "worker-a", 30) is None


def test_annulation_pendant_execution(conn):
    run, _ = depot.creer_run(conn, commande())
    depot.reclamer_run(conn, "worker-a", 30)
    annule = depot.demander_annulation(conn, "banque", run["run_id"])
    assert annule["etat"] == EtatRun.RUNNING.value
    assert annule["cancel_requested_at"] is not None


def test_retry_et_timer(conn):
    run, _ = depot.creer_run(conn, commande())
    pris = depot.reclamer_run(conn, "worker-a", 30)
    depot.planifier_retry(conn, "banque", run["run_id"], "worker-a",
                          int(pris["fencing_token"]), "transitoire", due_at=None)
    attendu = depot.obtenir_run(conn, "banque", run["run_id"])
    assert attendu["etat"] == EtatRun.WAITING_RETRY.value
    conn.execute("UPDATE execution_timer SET due_at = now() - interval '1 second'")
    depot.rearmer_timers(conn)
    requis = depot.obtenir_run(conn, "banque", run["run_id"])
    assert requis["etat"] == EtatRun.QUEUED.value
    repris = depot.reclamer_run(conn, "worker-b", 30)
    assert repris["run_id"] == run["run_id"]
    assert repris["fencing_token"] == 2


def test_expiration(conn):
    commande_expiree = CommandeExecution(
        tenant_id="banque", type="test.echo", idempotency_key="expire",
        deadline_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        - __import__("datetime").timedelta(seconds=1),
    )
    run, _ = depot.creer_run(conn, commande_expiree)
    depot.expirer_file(conn)
    expire = depot.obtenir_run(conn, "banque", run["run_id"])
    assert expire["etat"] == EtatRun.EXPIRED.value


def test_idempotence_refuse_un_payload_different(conn):
    depot.creer_run(conn, commande("conflit", payload={"x": 1}))
    try:
        depot.creer_run(conn, commande("conflit", payload={"x": 2}))
    except depot.ConflitIdempotence:
        pass
    else:
        raise AssertionError("un payload différent doit produire un conflit d'idempotence")


def test_tenant_isole(conn):
    run, _ = depot.creer_run(conn, commande())
    assert depot.obtenir_run(conn, "autre", run["run_id"]) is None
    try:
        depot.demander_annulation(conn, "autre", run["run_id"])
    except depot.RunIntrouvable:
        pass
    else:
        raise AssertionError("un autre tenant ne doit pas voir le run")


def test_connect_factory_schema(conn):
    """Le helper de test vérifie que le schéma de test est réutilisable par une connexion fraîche."""
    search_path = conn.execute("SHOW search_path").fetchone()[0]
    with psycopg.connect(os.environ["JUMEAU_PG_DSN"], autocommit=True, options=f"-c search_path={search_path}") as c:
        assert depot.creer_run(c, commande("autre-cle"))[1] is True


def test_outbox_publiee_une_seule_fois(conn):
    depot.creer_run(conn, commande("outbox-1"))
    vus = []
    assert depot.publier_outbox(conn, lambda ligne: vus.append(ligne["id"])) == 1
    assert len(vus) == 1
    assert depot.publier_outbox(conn, lambda ligne: vus.append(ligne["id"])) == 0
    assert depot.publier_outbox(conn, lambda ligne: None) == 0
