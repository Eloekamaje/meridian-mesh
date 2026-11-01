"""Alimentation pull-first : planification idempotente, bail/fencing, backoff, pause, isolation tenant."""
import asyncio
import json
from datetime import datetime, timezone

import pytest
from psycopg.rows import dict_row

from jumeau import ingestion_runtime as runtime
from jumeau.tests.conftest import besoin_pg

pytestmark = besoin_pg

TENANT = "banque"
AUTRE = "autre"


def _jumeau(conn, identifiant="tbt", tenant=TENANT):
    conn.execute(
        "INSERT INTO jumeau (id, tenant_id, nom, equipe) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        (identifiant, tenant, identifiant.upper(), "equipe-" + identifiant))
    return identifiant


def _source(conn, *, nom="tbt-repo", tenant=TENANT, jumeau="tbt",
            emplacement="/depots/tbt", curseur="sha1"):
    _jumeau(conn, jumeau, tenant)
    return conn.execute(
        "INSERT INTO source (tenant_id, jumeau_id, type, nom, emplacement, curseur) "
        "VALUES (%s, %s, 'GIT', %s, %s, %s) RETURNING id",
        (tenant, jumeau, nom, emplacement, curseur)).fetchone()[0]


def _schedule(conn, source_id, tenant=TENANT):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT * FROM source_schedule WHERE tenant_id = %s AND source_id = %s",
            (tenant, source_id)).fetchone()


def _run(conn, run_id):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM ingestion_run WHERE id = %s", (run_id,)).fetchone()


def test_planifier_source_est_idempotent_et_ne_remet_pas_l_echeance_a_zero(conn):
    source_id = _source(conn)

    premier = runtime.planifier_source(conn, source_id, 120, TENANT)
    echeance = _schedule(conn, source_id)["next_run_at"]
    second = runtime.planifier_source(conn, source_id, 120, TENANT)

    assert premier["source_id"] == second["source_id"] == source_id
    assert second["intervalle_s"] == 120
    assert len(conn.execute(
        "SELECT 1 FROM source_schedule WHERE tenant_id = %s AND source_id = %s",
        (TENANT, source_id)).fetchall()) == 1
    assert _schedule(conn, source_id)["next_run_at"] == echeance
    assert runtime.planifier_source(conn, source_id, 30, TENANT)["intervalle_s"] == 30


def test_une_seule_ingestion_par_source_due(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)

    premiers = runtime.enfiler_du(conn, 10)
    assert len(premiers) == 1
    assert premiers[0]["tenant_id"] == TENANT and premiers[0]["etat"] == "QUEUED"
    assert runtime.enfiler_du(conn, 10) == []

    conn.execute("UPDATE source_schedule SET next_run_at = now() WHERE source_id = %s", (source_id,))
    assert runtime.enfiler_du(conn, 10) == []  # le run vivant interdit le doublon

    manuel = runtime.enfiler_source(conn, source_id, TENANT, force=True)
    assert manuel["cree"] is False and manuel["run"]["id"] == premiers[0]["id"]


def test_claim_et_fencing_interdisent_deux_workers(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)
    runtime.enfiler_du(conn, 10)

    run = runtime.reclamer_run(conn, "worker-1", 30)
    assert run["etat"] == "FETCHING" and run["tentative"] == 1
    assert runtime.reclamer_run(conn, "worker-2", 30) is None

    for etape in ("INDEXING", "EXTRACTING", "PROJECTING"):
        run = runtime.marquer_etape(conn, run["id"], "worker-1", run["fencing_token"], etape)
    run = runtime.terminer(conn, run["id"], "worker-1", run["fencing_token"],
                           resultat={"ok": True}, observed_sha="sha2")

    assert run["etat"] == "SUCCEEDED" and run["observed_sha"] == "sha2"
    assert run["metriques"]["ok"] is True
    schedule = _schedule(conn, source_id)
    assert schedule["last_success_at"] is not None and schedule["last_error"] is None
    assert schedule["tentative"] == 0


def test_reprise_d_un_bail_expire_et_ancien_token_refuse(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)
    runtime.enfiler_du(conn, 10)

    premier = runtime.reclamer_run(conn, "worker-1", 30)
    conn.execute(
        "UPDATE ingestion_run SET bail_jusqu_a = now() - interval '1 second' WHERE id = %s",
        (premier["id"],))
    repris = runtime.reprendre_baux_expires(conn, 10)

    assert [run["etat"] for run in repris] == ["QUEUED"]
    second = runtime.reclamer_run(conn, "worker-2", 30)
    assert second["id"] == premier["id"]
    assert second["fencing_token"] > premier["fencing_token"]

    with pytest.raises(runtime.TransitionInvalide):
        runtime.terminer(conn, premier["id"], "worker-1", premier["fencing_token"])
    assert _run(conn, premier["id"])["etat"] == "FETCHING"


class _SansJitter:
    def uniform(self, debut, fin):
        return debut


def test_backoff_exponentiel_avec_plafond():
    assert runtime.backoff_secondes(1, base=10, plafond=100, rng=_SansJitter()) == 10
    assert runtime.backoff_secondes(2, base=10, plafond=100, rng=_SansJitter()) == 20
    assert runtime.backoff_secondes(3, base=10, plafond=100, rng=_SansJitter()) == 40
    assert runtime.backoff_secondes(10, base=10, plafond=100, rng=_SansJitter()) == 100
    assert runtime.backoff_secondes(1, base=0) == 0


def test_echec_repousse_la_source_puis_échoue_apres_max_tentatives(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)
    runtime.enfiler_du(conn, 10)

    run = runtime.reclamer_run(conn, "worker-1", 30)
    run = runtime.echouer(conn, run["id"], "worker-1", run["fencing_token"], "source injoignable")
    assert run["etat"] == "RETRY_WAIT" and run["next_attempt_at"] is not None
    schedule = _schedule(conn, source_id)
    assert schedule["last_error"] == "source injoignable" and schedule["tentative"] == 1

    conn.execute("UPDATE ingestion_run SET max_tentatives = 2, next_attempt_at = now() WHERE id = %s",
                 (run["id"],))
    run = runtime.reclamer_run(conn, "worker-2", 30)
    assert run["tentative"] == 2
    run = runtime.echouer(conn, run["id"], "worker-2", run["fencing_token"], "toujours injoignable")
    assert run["etat"] == "FAILED" and run["fini_le"] is not None
    assert _schedule(conn, source_id)["tentative"] == 2


def test_pause_stoppe_les_enfilements_et_resume_les_relance(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)

    assert runtime.pause_source(conn, source_id, TENANT)["etat"] == "paused"
    conn.execute("UPDATE source_schedule SET next_run_at = now() WHERE source_id = %s", (source_id,))
    assert runtime.enfiler_du(conn, 10) == []

    assert runtime.resume_source(conn, source_id, TENANT)["etat"] == "active"
    assert len(runtime.enfiler_du(conn, 10)) == 1


def test_isolation_tenant_sur_planification_runs_et_sante(conn):
    source_id = _source(conn)

    with pytest.raises(runtime.SourceIntrouvable):
        runtime.planifier_source(conn, source_id, 60, AUTRE)
    with pytest.raises(runtime.SourceIntrouvable):
        runtime.runs_source(conn, source_id, AUTRE)
    with pytest.raises(runtime.SourceIntrouvable):
        runtime.pause_source(conn, source_id, AUTRE)

    runtime.planifier_source(conn, source_id, 60, TENANT)
    assert runtime.sante_sources(conn, AUTRE)["sources"] == []
    assert len(runtime.sante_sources(conn, TENANT)["sources"]) == 1


def test_sante_ne_laisse_fuir_ni_url_ni_secret(conn):
    source_id = _source(
        conn, nom="depot-secret",
        emplacement="https://user:secret-token@git.exemple.fr/depot?token=secret-token")
    conn.execute(
        "UPDATE source SET url = %s, secret_ref = %s WHERE id = %s",
        ("https://user:secret-token@git.exemple.fr/depot", "env:JETON_DEPOT", source_id))
    runtime.planifier_source(conn, source_id, 60, TENANT)
    conn.execute(
        "UPDATE source_schedule SET last_error = %s, last_success_at = now() - interval '2 hours' "
        "WHERE source_id = %s",
        ("échec https://user:secret-token@git.exemple.fr/depot token=secret-token", source_id))

    sante = runtime.sante_sources(conn, TENANT)
    texte = json.dumps(sante, ensure_ascii=False)

    assert sante["tenant"] == TENANT
    assert sante["sources"][0]["sante"] == "en_erreur"
    assert sante["sources"][0]["lag_s"] > 0
    for interdit in ("secret-token", "https://", "env:JETON_DEPOT", "/depots/"):
        assert interdit not in texte


def test_ingerer_run_suit_les_etapes_et_consigne_le_sha(conn, monkeypatch):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)
    runtime.enfiler_du(conn, 10)
    run = runtime.reclamer_run(conn, "worker-1", 30)

    vus = []
    vrai_marquer = runtime.marquer_etape

    def espion(conn_, run_id, worker_id, fencing, etape, **kwargs):
        vus.append(etape)
        return vrai_marquer(conn_, run_id, worker_id, fencing, etape, **kwargs)

    monkeypatch.setattr(runtime, "marquer_etape", espion)

    async def faux_veiller(conn_, db, jumeau_id, chemins=None, **kwargs):
        assert jumeau_id == "tbt"
        assert chemins == ["/depots/tbt"]
        conn_.execute("UPDATE source SET curseur = 'sha2' WHERE id = %s", (source_id,))

    final = asyncio.run(runtime.ingerer_run(conn, None, run, "worker-1", run["fencing_token"],
                                            veiller=faux_veiller))

    assert vus[:4] == ["FETCHING", "INDEXING", "EXTRACTING", "PROJECTING"]
    assert final["etat"] == "SUCCEEDED"
    assert final["previous_sha"] == "sha1" and final["observed_sha"] == "sha2"
    assert final["metriques"]["changement"] is True
    assert _schedule(conn, source_id)["last_success_at"] is not None


def test_ingerer_run_echoue_sans_divulguer_url_ni_secret(conn):
    source_id = _source(conn)
    runtime.planifier_source(conn, source_id, 60, TENANT)
    runtime.enfiler_du(conn, 10)
    run = runtime.reclamer_run(conn, "worker-1", 30)

    async def panne(conn_, db, jumeau_id, chemins=None, **kwargs):
        raise RuntimeError("https://user:secret-token@git.exemple.fr/depot token=secret-token")

    final = asyncio.run(runtime.ingerer_run(conn, None, run, "worker-1", run["fencing_token"],
                                            veiller=panne))

    assert final["etat"] == "RETRY_WAIT"
    assert "secret-token" not in final["erreur"] and "https://" not in final["erreur"]
    assert _schedule(conn, source_id)["last_error"] is not None
