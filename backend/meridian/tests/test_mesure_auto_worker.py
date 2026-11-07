"""Worker de mesure automatique : flag, checkpoint, idempotence et isolation tenant.

Le worker ne touche jamais Postgres : il lit une collection d'observations Mongo, construit des
Outcomes avec le module pur, et les enfile dans l'outbox C1 (``pont_canonique``).
"""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone

import pytest

from meridian.tests.aides_mesure_auto import CollectionMesure, url_test_autorisee

from meridian.adapters.inbound.worker import mesure_auto_worker
from meridian.adapters.outbound.mongo import mesure_auto as mongo_mesure
from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.application import pont_canonique as pont

TENANT = "banque"
AUTRE = "assurance"
CLE = "cle-de-test-mesure-auto-32"


@pytest.fixture(autouse=True)
def _cle_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)


def _observation(identifiant="obs-1", tenant=TENANT, **champs):
    base = {
        "id": identifiant,
        "tenant_id": tenant,
        "initiative_id": "ini-dec-case-c1-1",
        "metrique": "delai_moyen_jours",
        "attendu": 5,
        "observe": 7,
        "effets_secondaires": [],
        "periode": "2026-11",
        "quand": "2026-11-05T09:00:00+00:00",
        "maj_le": "2026-11-05T09:01:00+00:00",
        "source": {"type": "twin", "nom": "tbt"},
    }
    base.update(champs)
    return base


class Outbox:
    """Outbox C1 en mémoire : ``$setOnInsert`` simulé par un dictionnaire d'événements."""

    def __init__(self, panne=False):
        self.evenements = {}
        self.panne = panne
        self.appels = []

    async def enfiler(self, evenement):
        self.appels.append(copy.deepcopy(evenement))
        if self.panne:
            return None
        existant = self.evenements.get(evenement["_id"])
        if existant is not None:
            assert existant["payload"] == evenement["payload"]
            assert existant["signature"] == evenement["signature"]
            return {"id": evenement["_id"], "cree": False}
        self.evenements[evenement["_id"]] = copy.deepcopy(evenement)
        return {"id": evenement["_id"], "cree": True}

    def operations(self):
        return [evenement["operation"] for evenement in self.evenements.values()]


def _worker(observations, checkpoints, outbox, *, tenants=(TENANT,), lot=100,
            env=None, depuis=None, rejets=None, maintenant=None):
    return mesure_auto_worker.WorkerMesureAuto(
        observations=observations,
        checkpoints=checkpoints,
        enfiler=outbox.enfiler,
        rejets=rejets,
        tenants=tenants,
        lot=lot,
        env=env if env is not None else {mesure_auto_worker.FLAG_ENV: "1"},
        depuis=depuis,
        maintenant=maintenant or (lambda: "2026-11-07T12:00:00+00:00"),
    )


def _depots(documents=None):
    collection_observations = CollectionMesure(documents or [])
    collection_checkpoints = CollectionMesure()
    return (
        mongo_mesure.DepotObservationsMesure(collection_observations),
        mongo_mesure.DepotCheckpointsMesure(collection_checkpoints),
        collection_observations,
        collection_checkpoints,
    )


# ---------------------------------------------------------------------------
# Flag et CLI
# ---------------------------------------------------------------------------


def test_flag_off_par_defaut_le_worker_ne_lit_rien(monkeypatch):
    monkeypatch.delenv(mesure_auto_worker.FLAG_ENV, raising=False)

    class Interdite:
        async def lister_apres(self, *args, **kwargs):
            raise AssertionError("le flag off ne doit rien lire")

        async def lire(self, *args, **kwargs):
            raise AssertionError("le flag off ne doit rien lire")

        async def ecrire(self, *args, **kwargs):
            raise AssertionError("le flag off ne doit rien écrire")

    outbox = Outbox()
    worker = mesure_auto_worker.WorkerMesureAuto(
        Interdite(), Interdite(), outbox.enfiler, tenants=(TENANT,), env={})

    bilan = asyncio.run(worker.une_passe())

    assert bilan["actif"] is False
    assert outbox.appels == []
    assert mesure_auto_worker.actif({mesure_auto_worker.FLAG_ENV: "0"}) is False
    assert mesure_auto_worker.actif({mesure_auto_worker.FLAG_ENV: "1"}) is True


def test_cli_flag_off_sort_sans_connexion(monkeypatch, capsys):
    monkeypatch.delenv(mesure_auto_worker.FLAG_ENV, raising=False)

    code = mesure_auto_worker.principal(["--once"])

    capture = capsys.readouterr()
    assert code == 0
    assert "désactivé" in capture.out.lower()


def test_cli_flag_on_sans_mongo_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.delenv("MONGO_URL", raising=False)

    code = mesure_auto_worker.principal(["--once"])

    capture = capsys.readouterr()
    assert code == 2
    assert "MONGO_URL" in capture.err


def test_cli_flag_on_sans_cle_pont_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.delenv(pont.PONT_KEY_ENV, raising=False)

    code = mesure_auto_worker.principal(["--once"])

    capture = capsys.readouterr()
    assert code == 2
    assert "PONT_KEY" in capture.err


def test_le_worker_n_importe_pas_postgres():
    import inspect

    source = inspect.getsource(mesure_auto_worker)
    assert "import psycopg" not in source
    assert "from psycopg" not in source
    assert "JUMEAU_PG_DSN" not in source


# ---------------------------------------------------------------------------
# Enfilement, checkpoint, idempotence
# ---------------------------------------------------------------------------


def test_flag_on_enfile_les_outcomes_et_avance_le_checkpoint():
    observations, checkpoints, _col_obs, col_cp = _depots([
        _observation("obs-1"),
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["actif"] is True
    assert bilan["lues"] == 2
    assert bilan["outcomes"] == 2
    assert bilan["doublons"] == 0 and bilan["echecs"] == 0
    assert outbox.operations() == [pont.OPERATION_OUTCOME, pont.OPERATION_OUTCOME]
    assert {e["tenant_id"] for e in outbox.evenements.values()} == {TENANT}
    checkpoint = asyncio.run(checkpoints.lire(TENANT))
    assert checkpoint.id == "obs-2"
    assert checkpoint.maj_le == "2026-11-05T09:02:00.000000+00:00"


def test_rejeu_ne_cree_pas_de_doublon():
    documents = [_observation("obs-1"), _observation("obs-2")]
    observations, checkpoints, _col_obs, col_cp = _depots(copy.deepcopy(documents))
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)
    asyncio.run(worker.une_passe())

    # On rejoue en remettant le checkpoint au début : l'outbox doit dédupliquer.
    col_cp.documents.clear()
    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 2
    assert bilan["outcomes"] == 0
    assert bilan["doublons"] == 2
    assert len(outbox.evenements) == 2


def test_checkpoint_non_avance_si_l_enfilage_echoue():
    observations, checkpoints, _col_obs, col_cp = _depots([
        _observation("obs-1"),
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox(panne=True)
    worker = _worker(observations, checkpoints, outbox)

    premier = asyncio.run(worker.une_passe())

    assert premier["echecs"] == 1
    assert premier["outcomes"] == 0
    assert asyncio.run(checkpoints.lire(TENANT)) is None

    outbox.panne = False
    second = asyncio.run(worker.une_passe())

    assert second["outcomes"] == 2
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"


def test_observation_incomplete_est_ignoree_mais_le_checkpoint_avance():
    incomplete = _observation("obs-1")
    incomplete.pop("observe")
    observations, checkpoints, _col_obs, _col_cp = _depots([
        incomplete,
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    rejets, _col_rejets = _rejets()
    worker = _worker(observations, checkpoints, outbox, rejets=rejets)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 2
    assert bilan["rejets"] == 1 and bilan["outcomes"] == 1
    assert len(outbox.evenements) == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"


def test_lot_borne_et_reprise_au_tour_suivant():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1"),
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
        _observation("obs-3", maj_le="2026-11-05T09:03:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox, lot=2)

    premier = asyncio.run(worker.une_passe())
    second = asyncio.run(worker.une_passe())

    assert premier["lues"] == 2 and premier["outcomes"] == 2
    assert second["lues"] == 1 and second["outcomes"] == 1
    assert len(outbox.evenements) == 3


def test_un_document_avec_une_autre_maj_le_est_relu_et_mis_a_jour():
    observations, checkpoints, col_obs, _col_cp = _depots([
        _observation("obs-1"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)
    asyncio.run(worker.une_passe())

    col_obs.documents[0] = mongo_mesure.document_ingestion({
        **col_obs.documents[0],
        "observe": 8,
        "maj_le": "2026-11-06T09:00:00+00:00",
    })
    bilan = asyncio.run(worker.une_passe())

    assert bilan["outcomes"] == 1
    assert len(outbox.evenements) == 2  # deux versions de la mesure, même Outcome canonique
    assert len({e["canonical_id"] for e in outbox.evenements.values()}) == 1


# ---------------------------------------------------------------------------
# Isolation tenant
# ---------------------------------------------------------------------------


def test_isolation_tenant_un_seul_tenant_lu():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-banque", TENANT),
        _observation("obs-assurance", AUTRE, maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox, tenants=(TENANT,))

    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 1
    assert len(outbox.evenements) == 1
    assert next(iter(outbox.evenements.values()))["tenant_id"] == TENANT
    assert asyncio.run(checkpoints.lire(AUTRE)) is None


def test_deux_tenants_ne_partagent_ni_evenement_ni_checkpoint():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-banque", TENANT),
        _observation("obs-assurance", AUTRE,
                     initiative_id="ini-dec-case-c9-1",
                     maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox, tenants=(TENANT, AUTRE))

    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 2 and bilan["outcomes"] == 2
    assert {e["tenant_id"] for e in outbox.evenements.values()} == {TENANT, AUTRE}
    cp_banque = asyncio.run(checkpoints.lire(TENANT))
    cp_assurance = asyncio.run(checkpoints.lire(AUTRE))
    assert cp_banque.id == "obs-banque"
    assert cp_assurance.id == "obs-assurance"


def test_un_document_du_mauvais_tenant_est_refuse_meme_s_il_est_lu():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1", AUTRE),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox, tenants=(TENANT,))

    bilan = asyncio.run(worker.une_passe())

    # Le filtre tenant de l'adaptateur l'écarte avant même la normalisation.
    assert bilan["lues"] == 0
    assert outbox.evenements == {}


def test_aucun_learning_n_est_enfile():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1"),
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    asyncio.run(worker.une_passe())

    assert set(outbox.operations()) == {pont.OPERATION_OUTCOME}
    assert pont.OPERATION_LEARNING not in outbox.operations()


# ---------------------------------------------------------------------------
# Adaptateurs Mongo
# ---------------------------------------------------------------------------


def test_depot_observations_filtre_tenant_et_curseur():
    collection = CollectionMesure([
        _observation("obs-1", maj_le="2026-11-05T09:00:00+00:00"),
        _observation("obs-2", maj_le="2026-11-05T09:01:00+00:00"),
        _observation("obs-3", AUTRE, maj_le="2026-11-05T09:00:30+00:00"),
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    premier = asyncio.run(depot.lister_apres(TENANT, None, 10))
    second = asyncio.run(depot.lister_apres(
        TENANT, mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00.000000+00:00", id="obs-1"), 10))

    assert [document["id"] for document in premier] == ["obs-1", "obs-2"]
    assert [document["id"] for document in second] == ["obs-2"]
    assert collection.appels[0][1]["tenant_id"] == TENANT


def test_depot_checkpoints_lit_et_ecrit_un_document_par_tenant():
    collection = CollectionMesure()
    depot = mongo_mesure.DepotCheckpointsMesure(collection)

    assert asyncio.run(depot.lire(TENANT)) is None
    asyncio.run(depot.ecrire(TENANT, mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:01:00+00:00", id="obs-2")))
    asyncio.run(depot.ecrire(AUTRE, mongo_mesure.CurseurObservation(
        maj_le="2026-11-06T09:00:00+00:00", id="obs-9")))

    assert asyncio.run(depot.lire(TENANT)).id == "obs-2"
    assert asyncio.run(depot.lire(AUTRE)).id == "obs-9"
    assert len(collection.documents) == 2


def test_depot_checkpoints_refuse_un_curseur_incomplet():
    depot = mongo_mesure.DepotCheckpointsMesure(CollectionMesure())

    with pytest.raises(ValueError):
        asyncio.run(depot.ecrire(TENANT, mongo_mesure.CurseurObservation(
            maj_le="", id="obs-1")))
    with pytest.raises(ValueError):
        asyncio.run(depot.ecrire(TENANT, mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00+00:00", id="")))


def test_depot_observations_borne_et_indexe():
    collection = CollectionMesure([
        _observation("obs-1", maj_le="2026-11-05T09:00:00+00:00"),
        _observation("obs-2", maj_le="2026-11-05T09:01:00+00:00"),
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    lot = asyncio.run(depot.lister_apres(TENANT, None, 1))
    index = asyncio.run(depot.assurer_index())

    assert [document["id"] for document in lot] == ["obs-1"]
    assert len(index) == 2 and collection.index[0][0][0] == ("tenant_id", 1)
    assert ("sequence_canonique", 1) in collection.index[0][0]


# ---------------------------------------------------------------------------
# Configuration, boucle et CLI de bout en bout (Mongo simulé)
# ---------------------------------------------------------------------------


def test_tenants_cli_environnement_et_refus():
    assert mesure_auto_worker._tenants(
        None, {"JUMEAU_WORKER_TENANTS": "Banque, assurance,banque"}) == ("banque", "assurance")
    assert mesure_auto_worker._tenants(
        None, {"JUMEAU_WORKER_TENANT": "Banque"}) == ("banque",)
    assert mesure_auto_worker._tenants(["Autre"], {"JUMEAU_WORKER_TENANTS": "banque"}) \
        == ("autre",)
    assert mesure_auto_worker._tenants("Banque", {}) == ("banque",)
    assert mesure_auto_worker._tenants(None, {}) == ("local",)
    with pytest.raises(ValueError):
        mesure_auto_worker._tenants(None, {"JUMEAU_WORKER_TENANT": "banque client"})


def test_worker_normalise_et_deduplique_les_tenants():
    observations, checkpoints, _col_obs, _col_cp = _depots()
    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, checkpoints, Outbox().enfiler,
        tenants=["Banque", "banque", "assurance"], env={},
        maintenant=lambda: "2026-11-07T12:00:00+00:00")

    assert worker.tenants == ("banque", "assurance")
    assert worker.metriques.instantane() == {
        "mesure_auto_lues": 0, "mesure_auto_outcomes": 0,
        "mesure_auto_doublons": 0,
        "mesure_auto_echecs": 0, "mesure_auto_rejets": 0,
        "mesure_auto_non_conformes": 0, "mesure_auto_dead_letter_echecs": 0,
    }


def test_instant_normalise_datetime_naif_et_vide():
    from datetime import datetime

    assert mesure_auto_worker._instant(datetime(2026, 11, 5, 9, 0)) \
        == "2026-11-05T09:00:00+00:00"
    assert mesure_auto_worker._instant("") != ""
    assert mesure_auto_worker._instant(None) != ""


def test_avancer_refuse_un_curseur_incomplet_ou_une_panne_de_checkpoint():
    observations, checkpoints, _col_obs, _col_cp = _depots()
    worker = _worker(observations, checkpoints, Outbox())

    assert asyncio.run(worker._avancer(
        TENANT, mongo_mesure.CurseurObservation(maj_le="", id="obs-1"))) is False
    assert asyncio.run(worker._avancer(
        TENANT, mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00+00:00", id=""))) is False

    class CheckpointsEnPanne:
        async def lire(self, tenant):
            return None

        async def ecrire(self, *args, **kwargs):
            raise RuntimeError("mongo indisponible")

    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, CheckpointsEnPanne(), Outbox().enfiler,
        tenants=(TENANT,), env={mesure_auto_worker.FLAG_ENV: "1"})
    assert asyncio.run(worker._avancer(
        TENANT, mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:00:00+00:00", id="obs-1"))) is False


def test_une_panne_sur_un_tenant_ne_bloque_pas_les_autres():
    class ObservationsParTenant:
        def __init__(self, depot_autre):
            self.depot_autre = depot_autre

        async def lister_apres(self, tenant, curseur=None, limite=100):
            if tenant == TENANT:
                raise RuntimeError("lecture impossible pour ce tenant")
            return await self.depot_autre.lister_apres(tenant, curseur, limite)

    autre = mongo_mesure.DepotObservationsMesure(CollectionMesure([
        _observation("obs-assurance", AUTRE, initiative_id="ini-dec-case-c9-1"),
    ]))
    worker = _worker(
        ObservationsParTenant(autre),
        mongo_mesure.DepotCheckpointsMesure(CollectionMesure()),
        Outbox(), tenants=(TENANT, AUTRE))

    bilan = asyncio.run(worker.une_passe())

    assert bilan["echecs"] == 1
    assert bilan["outcomes"] == 1
    assert bilan["tenants"][TENANT]["echecs"] == 1
    assert bilan["tenants"][AUTRE]["outcomes"] == 1


def test_depuis_est_utilise_si_le_checkpoint_est_absent():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1", maj_le="2026-11-05T09:00:00+00:00"),
        _observation("obs-2", maj_le="2026-11-05T09:01:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox,
                     depuis="2026-11-05T09:00:30+00:00")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 1 and bilan["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"


def test_tourner_s_arrete_proprement():
    class ObservationsVides:
        def __init__(self):
            self.passes = 0

        async def lister_apres(self, *args, **kwargs):
            self.passes += 1
            return []

    observations = ObservationsVides()
    worker = mesure_auto_worker.WorkerMesureAuto(
        observations,
        mongo_mesure.DepotCheckpointsMesure(CollectionMesure()),
        Outbox().enfiler, tenants=(TENANT,),
        env={mesure_auto_worker.FLAG_ENV: "1"}, intervalle=0.01)

    async def scenario():
        tache = asyncio.create_task(worker.tourner())
        await asyncio.sleep(0.03)
        worker.arreter()
        await tache

    asyncio.run(scenario())

    assert observations.passes >= 1


class _BaseFaux:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, nom):
        return self.collections.setdefault(nom, CollectionMesure())


class _ClientFaux:
    instances = []

    def __init__(self, url):
        self.url = url
        self.ferme = False
        self.base = _BaseFaux(_ClientFaux.collections)
        _ClientFaux.instances.append(self)

    def __getitem__(self, nom):
        return self.base

    def close(self):
        self.ferme = True


def _client_mongo(monkeypatch, collections):
    _ClientFaux.collections = collections
    _ClientFaux.instances = []
    monkeypatch.setattr("motor.motor_asyncio.AsyncIOMotorClient", _ClientFaux)


def test_cli_once_enfile_avec_un_client_mongo_simule(monkeypatch):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")
    monkeypatch.delenv("JUMEAU_WORKER_TENANTS", raising=False)
    monkeypatch.delenv("JUMEAU_WORKER_TENANT", raising=False)
    collections = {
        mongo_mesure.OBSERVATIONS: CollectionMesure([
            _observation("obs-1"),
            _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
        ]),
    }
    _client_mongo(monkeypatch, collections)

    code = mesure_auto_worker.principal(["--once", "--tenant", TENANT, "--lot", "10"])

    assert code == 0
    assert len(collections[pont_mongo.COLLECTION].documents) == 2
    assert len(collections[mongo_mesure.CHECKPOINTS].documents) == 1
    assert _ClientFaux.instances[0].ferme is True


def test_cli_once_retourne_1_si_l_enfilage_echoue(monkeypatch):
    class CollectionEnPanne(CollectionMesure):
        async def update_one(self, *args, **kwargs):
            raise RuntimeError("outbox indisponible")

    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")
    collections = {
        mongo_mesure.OBSERVATIONS: CollectionMesure([_observation("obs-1")]),
        pont_mongo.COLLECTION: CollectionEnPanne(),
    }
    _client_mongo(monkeypatch, collections)

    code = mesure_auto_worker.principal(["--once", "--tenant", TENANT])

    assert code == 1


def test_cli_tenant_invalide_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")

    code = mesure_auto_worker.principal(["--once", "--tenant", "banque client"])

    capture = capsys.readouterr()
    assert code == 2
    assert "tenant" in capture.err.lower()


def test_cli_sans_once_tourne_puis_sort(monkeypatch):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")
    _client_mongo(monkeypatch, {})

    async def tourner_puis_arreter(self):
        self.arreter()

    monkeypatch.setattr(
        mesure_auto_worker.WorkerMesureAuto, "tourner", tourner_puis_arreter)

    code = mesure_auto_worker.principal(["--tenant", TENANT])

    assert code == 0


def test_cli_interruption_retourne_0(monkeypatch):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")
    _client_mongo(monkeypatch, {})

    def interrompre(coroutine):
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(mesure_auto_worker.asyncio, "run", interrompre)

    assert mesure_auto_worker.principal(["--once", "--tenant", TENANT]) == 0


# ---------------------------------------------------------------------------
# Revue lot D : dead-letter, transitoire, audit, type bracketing, CAS
# ---------------------------------------------------------------------------


class OutboxCollision(Outbox):
    """Outbox qui refuse un événement comme le ferait C1 sur collision d'idempotence."""

    def __init__(self, observation_id="obs-1"):
        super().__init__()
        self.observation_id = observation_id

    async def enfiler(self, evenement):
        if evenement["payload"]["mesure"].get("observation_id") == self.observation_id:
            raise pont.PontInvalide("collision d'idempotence sur _id")
        return await super().enfiler(evenement)


class OutboxTransitoire(Outbox):
    def __init__(self, pannes=2):
        super().__init__()
        self.pannes = pannes

    async def enfiler(self, evenement):
        if self.pannes > 0:
            self.pannes -= 1
            raise RuntimeError("PyMongoError: timeout")
        return await super().enfiler(evenement)


class OutboxStrict(Outbox):
    """Reproduit C1 : même `_id` avec un payload différent = collision permanente."""

    async def enfiler(self, evenement):
        existant = self.evenements.get(evenement["_id"])
        if existant is not None and existant["payload"] != evenement["payload"]:
            raise pont.PontInvalide(
                f"collision d'idempotence sur _id {evenement['_id']!r}")
        return await super().enfiler(evenement)


def test_correction_d_interpretation_produit_un_nouvel_evenement_et_continue():
    observations, checkpoints, col_obs, _col_cp = _depots([
        _observation("obs-1", interpretation="version 1"),
    ])
    outbox = OutboxStrict()
    worker = _worker(observations, checkpoints, outbox)
    asyncio.run(worker.une_passe())

    # Correction de l'interprétation seule, puis une observation suivante.
    col_obs.documents[0] = mongo_mesure.document_ingestion({
        **col_obs.documents[0],
        "interpretation": "version 2",
        "maj_le": "2026-11-05T09:02:00+00:00",
    })
    col_obs.documents.append(mongo_mesure.document_ingestion(_observation(
        "obs-2", maj_le="2026-11-05T09:03:00+00:00")))

    bilan = asyncio.run(worker.une_passe())

    assert bilan["rejets"] == 0
    assert bilan["outcomes"] == 2
    assert len(outbox.evenements) == 3  # v1, v2, obs-2
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"


def _rejets():
    collection = CollectionMesure()
    return mongo_mesure.DepotRejetsMesure(collection), collection


def test_dead_letter_est_durable_avant_l_avancement_du_checkpoint():
    incomplete = _observation("obs-1")
    incomplete.pop("observe")
    observations, checkpoints, _col_obs, _col_cp = _depots([
        incomplete,
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    rejets, col_rejets = _rejets()

    class CheckpointsVerifiant:
        async def lire(self, tenant):
            return await checkpoints.lire(tenant)

        async def ecrire(self, tenant, curseur):
            assert any(document.get("etat") == "dead" for document in col_rejets.documents), \
                "le dead-letter doit être écrit avant le checkpoint"
            return await checkpoints.ecrire(tenant, curseur)

    worker = _worker(observations, CheckpointsVerifiant(), Outbox(), rejets=rejets)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["rejets"] == 1 and bilan["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"


def test_collision_permanente_est_dead_letter_et_obs_suivante_traitee():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1"),
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    rejets, col_rejets = _rejets()
    outbox = OutboxCollision("obs-1")
    worker = _worker(observations, checkpoints, outbox, rejets=rejets)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["rejets"] == 1
    assert bilan["outcomes"] == 1
    assert set(outbox.evenements)  # obs-2 est bien enfilée
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-2"
    rejet = next(document for document in col_rejets.documents
                 if document["observation_id"] == "obs-1")
    assert rejet["etat"] == "dead" and rejet["permanent"] is True


def test_erreur_transitoire_ne_avance_pas_puis_dead_letter_apres_borne():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-1"),
    ])
    rejets, col_rejets = _rejets()
    outbox = OutboxTransitoire(pannes=2)
    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, checkpoints, outbox.enfiler, rejets=rejets,
        tenants=(TENANT,), lot=10, tentatives_max=2,
        env={mesure_auto_worker.FLAG_ENV: "1"},
        maintenant=lambda: "2026-11-07T12:00:00+00:00")

    premier = asyncio.run(worker.une_passe())
    assert premier["echecs"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)) is None

    second = asyncio.run(worker.une_passe())
    assert second["rejets"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-1"
    assert col_rejets.documents[0]["etat"] == "dead"


def test_signature_indisponible_est_transitoire_et_ne_perd_pas_la_mesure():
    observations, checkpoints, _col_obs, _col_cp = _depots([_observation("obs-1")])
    rejets, _col_rejets = _rejets()
    appels = {"n": 0}

    async def enfiler(evenement):
        appels["n"] += 1
        if appels["n"] == 1:
            raise pont.SignatureInvalide("PONT_KEY indisponible")
        return {"id": evenement["_id"], "cree": True}

    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, checkpoints, enfiler, rejets=rejets,
        tenants=(TENANT,), env={mesure_auto_worker.FLAG_ENV: "1"},
        maintenant=lambda: "2026-11-07T12:00:00+00:00")

    premier = asyncio.run(worker.une_passe())
    assert premier["echecs"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)) is None

    second = asyncio.run(worker.une_passe())
    assert second["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-1"


def test_quand_futur_ne_consomme_pas_les_tentatives_et_attend_l_horloge():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation(
            "obs-1",
            maj_le="2026-11-07T11:59:00+00:00",
            quand="2026-11-07T12:06:00+00:00",
        ),
    ])
    rejets, col_rejets = _rejets()
    outbox = Outbox()
    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, checkpoints, outbox.enfiler, rejets=rejets,
        tenants=(TENANT,), tentatives_max=1,
        env={mesure_auto_worker.FLAG_ENV: "1"},
        maintenant=lambda: "2026-11-07T12:00:00+00:00")

    # Six passes (30 s à intervalle 5 s, bien moins que +6 min) : jamais de dead-letter.
    for _ in range(6):
        bilan = asyncio.run(worker.une_passe())
        assert bilan["echecs"] == 1
        assert asyncio.run(checkpoints.lire(TENANT)) is None
        assert outbox.evenements == {}
    assert all(document.get("etat") == "retry" for document in col_rejets.documents)

    worker.maintenant = lambda: "2026-11-07T12:10:00+00:00"
    second = asyncio.run(worker.une_passe())

    assert second["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-1"


def test_dead_letter_indisponible_ne_fait_pas_avancer_le_checkpoint():
    incomplete = _observation("obs-1")
    incomplete.pop("observe")
    observations, checkpoints, _col_obs, _col_cp = _depots([incomplete])
    outbox = Outbox()

    class RejetsEnPanne:
        async def enregistrer(self, *args, **kwargs):
            raise RuntimeError("mongo indisponible")

    worker = _worker(observations, checkpoints, outbox, rejets=RejetsEnPanne())

    bilan = asyncio.run(worker.une_passe())

    assert bilan["echecs"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)) is None
    assert outbox.evenements == {}
    assert worker.metriques.mesure_auto_dead_letter_echecs == 1


def test_avancer_echoue_si_le_checkpoint_retourne_un_curseur_plus_ancien():
    observations, checkpoints, _col_obs, _col_cp = _depots()
    worker = _worker(observations, checkpoints, Outbox())

    class CheckpointsAnciens:
        async def ecrire(self, tenant, curseur):
            return mongo_mesure.CurseurObservation(
                maj_le="2026-11-05T09:00:00.000000+00:00", id="obs-old")

    worker.checkpoints = CheckpointsAnciens()
    assert asyncio.run(worker._avancer(
        TENANT, mongo_mesure.CurseurObservation(
            maj_le="2026-11-05T09:01:00.000000+00:00", id="obs-new"))) is False


def test_checkpoint_legacy_en_secondes_ou_offset_est_matche_et_migre():
    collection = CollectionMesure([
        {"_id": TENANT, "tenant_id": TENANT,
         "dernier_maj_le": "2026-11-05T11:00:00+02:00", "dernier_id": "obs-1"},
    ])
    depot = mongo_mesure.DepotCheckpointsMesure(collection)

    assert asyncio.run(depot.lire(TENANT)).maj_le \
        == "2026-11-05T09:00:00.000000+00:00"
    retour = asyncio.run(depot.ecrire(TENANT, mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:01:00+00:00", id="obs-2")))

    assert retour.id == "obs-2"
    assert collection.documents[0]["dernier_maj_le"] \
        == "2026-11-05T09:01:00.000000+00:00"
    assert collection.documents[0]["dernier_sequence"] == ""


def test_checkpoint_legacy_en_secondes_est_migre():
    collection = CollectionMesure([
        {"_id": TENANT, "tenant_id": TENANT,
         "dernier_maj_le": "2026-11-05T09:00:00+00:00", "dernier_id": "obs-1"},
    ])
    depot = mongo_mesure.DepotCheckpointsMesure(collection)

    retour = asyncio.run(depot.ecrire(TENANT, mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:01:00+00:00", id="obs-2")))

    assert retour.id == "obs-2"
    assert collection.documents[0]["dernier_maj_le"] \
        == "2026-11-05T09:01:00.000000+00:00"


def test_correction_meme_ms_sequence_bumpee_est_relue():
    premier = mongo_mesure.document_ingestion(_observation(
        "obs-1", maj_le="2026-11-05T09:01:00.123456+00:00"))
    premier["sequence"] = "00000000000000000001"
    premier["sequence_canonique"] = "00000000000000000001"
    second = mongo_mesure.document_ingestion(_observation(
        "obs-2", maj_le="2026-11-05T09:01:00.123789+00:00"))
    second["sequence"] = "00000000000000000002"
    second["sequence_canonique"] = "00000000000000000002"
    collection = CollectionMesure([premier, second])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    curseur = mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:01:00.123000+00:00",
        sequence="00000000000000000001", id="obs-1")
    documents = asyncio.run(depot.lister_apres(TENANT, curseur, 10))

    assert [document["id"] for document in documents] == ["obs-2"]


def test_correction_legacy_apres_backfill_est_relue_en_faux_mongo():
    document = mongo_mesure.document_ingestion(_observation(
        "obs-legacy", maj_le="2026-11-05T09:00:00+00:00"))
    collection = CollectionMesure([document])
    depot = mongo_mesure.DepotObservationsMesure(collection)
    asyncio.run(depot.remplir_maj_le_utc(TENANT))
    collection.documents[0]["maj_le"] = "2026-11-05T10:00:00+00:00"
    curseur = mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:00:00.000000+00:00", id="curseur")

    documents = asyncio.run(depot.lister_apres(TENANT, curseur, 10))

    assert [element["id"] for element in documents] == ["obs-legacy"]


def test_backfill_ne_regresse_pas_une_correction_concurrente():
    class CollectionConcurrente(CollectionMesure):
        def __init__(self, documents=None):
            super().__init__(documents)
            self.concurrent = False

        async def update_one(self, filtre, modification, upsert=False):
            if not self.concurrent:
                self.concurrent = True
                for document in self.documents:
                    document["maj_le"] = "2026-11-05T10:30:00+00:00"
            return await super().update_one(filtre, modification, upsert)

    collection = CollectionConcurrente([
        _observation("obs-1", maj_le="2026-11-05T10:00:00+00:00"),
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    remplis = asyncio.run(depot.remplir_maj_le_utc(TENANT))

    assert remplis == 0
    assert collection.documents[0]["maj_le"] == "2026-11-05T10:30:00+00:00"


def test_garde_url_mongo_refuse_la_production():
    assert url_test_autorisee("mongodb://127.0.0.1:27017/db") is True
    assert url_test_autorisee("mongodb://localhost:27017/meridian_test") is True
    assert url_test_autorisee("mongodb://prod.example.com/meridian") is False


def test_document_ingestion_tronque_maj_le_utc_a_la_milliseconde():
    propre = mongo_mesure.document_ingestion(_observation(
        "obs-ms", maj_le="2026-11-05T09:01:00.123456+00:00"))

    assert propre["maj_le"] == "2026-11-05T09:01:00.123456+00:00"
    assert propre["maj_le_utc"].microsecond == 123000
    assert mongo_mesure.curseur_document(propre).maj_le \
        == "2026-11-05T09:01:00.123000+00:00"


def test_tie_breaker_numerique_est_zero_padde():
    collection = CollectionMesure([
        {**_observation("obs-9", maj_le="2026-11-05T10:00:00+00:00"), "sequence": 9},
        {**_observation("obs-10", maj_le="2026-11-05T10:00:00+00:00"), "sequence": 10},
        {**_observation("obs-11", maj_le="2026-11-05T10:00:00+00:00"), "sequence": 11},
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    documents = asyncio.run(depot.lister_apres(TENANT, None, 10))

    assert [document["id"] for document in documents] == ["obs-9", "obs-10", "obs-11"]
    assert mongo_mesure.sequence_canonique(9) < mongo_mesure.sequence_canonique(10)
    curseur = mongo_mesure.CurseurObservation(
        maj_le=documents[1]["maj_le"],
        sequence=mongo_mesure.sequence_canonique(10), id="obs-10")
    assert [document["id"] for document in
            asyncio.run(depot.lister_apres(TENANT, curseur, 10))] == ["obs-11"]


def test_seek_index_ne_starve_pas_500_documents_avant_le_curseur():
    avant = [
        mongo_mesure.document_ingestion(_observation(
            f"old-{rang}", maj_le=f"2026-11-05T08:{rang // 60:02d}:{rang % 60:02d}+00:00"))
        for rang in range(500)
    ]
    apres = [
        mongo_mesure.document_ingestion(_observation(
            f"new-{rang}", maj_le=f"2026-11-05T09:0{rang + 1}:00+00:00"))
        for rang in range(5)
    ]
    collection = CollectionMesure(avant + apres)
    depot = mongo_mesure.DepotObservationsMesure(collection)
    curseur = mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:00:00.000000+00:00", id="curseur")

    documents = asyncio.run(depot.lister_apres(TENANT, curseur, 10))

    assert [document["id"] for document in documents] == [
        "new-0", "new-1", "new-2", "new-3", "new-4"]


def test_audit_compte_tenant_non_normalise_et_maj_le_illisible():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-ok"),
        _observation("obs-tenant", tenant="Banque"),
        _observation("obs-maj", maj_le="hier"),
    ])
    worker = _worker(observations, checkpoints, Outbox())

    total = asyncio.run(worker.auditer())

    assert total == 2
    assert worker.metriques.mesure_auto_non_conformes == 2


def test_audit_est_refait_a_chaque_passe():
    observations, checkpoints, col_obs, _col_cp = _depots([_observation("obs-1")])
    worker = _worker(observations, checkpoints, Outbox())
    asyncio.run(worker.une_passe())

    col_obs.documents.append({
        "tenant_id": TENANT, "id": "",
        "maj_le": "2026-11-05T09:00:00+00:00",
    })
    asyncio.run(worker.une_passe())

    assert worker.metriques.mesure_auto_non_conformes == 1


def test_depuis_est_canonise_et_invalide_refuse():
    observations, checkpoints, _col_obs, _col_cp = _depots()
    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, checkpoints, Outbox().enfiler, tenants=(TENANT,),
        env={mesure_auto_worker.FLAG_ENV: "1"},
        depuis="2026-11-05T11:00:00+02:00")
    assert worker.depuis == "2026-11-05T09:00:00.000000+00:00"

    with pytest.raises(ValueError):
        mesure_auto_worker.WorkerMesureAuto(
            observations, checkpoints, Outbox().enfiler, tenants=(TENANT,),
            env={mesure_auto_worker.FLAG_ENV: "1"}, depuis="hier")


def test_cli_depuis_invalide_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(mesure_auto_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE)
    monkeypatch.setenv("MONGO_URL", "mongodb://faux")

    code = mesure_auto_worker.principal(["--once", "--depuis", "hier"])

    capture = capsys.readouterr()
    assert code == 2
    assert "depuis" in capture.err.lower()


def test_audit_compte_les_documents_non_conformes_sans_bloquer_le_flux():
    malforme = {"tenant_id": TENANT, "maj_le": "2026-11-05T09:00:00+00:00"}
    observations, checkpoints, _col_obs, _col_cp = _depots([
        malforme,
        _observation("obs-1", maj_le="2026-11-05T09:02:00+00:00"),
        _observation("obs-assurance", tenant=AUTRE, maj_le="hier"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["outcomes"] == 1
    assert worker.metriques.mesure_auto_non_conformes == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-1"


def test_audit_ignore_les_documents_d_un_autre_tenant():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        _observation("obs-ok"),
        _observation("obs-tenant", tenant="Banque"),
        _observation("obs-maj", maj_le="hier"),
        _observation("obs-assurance", tenant=AUTRE, maj_le="hier"),
    ])
    worker = _worker(observations, checkpoints, Outbox())

    assert asyncio.run(worker.auditer()) == 2


def test_audit_tourne_par_lot_de_1000():
    valides = [
        {**_observation(f"ok-{rang}"), "_id": f"{rang:04d}"}
        for rang in range(1000)
    ]
    mauvais = {**_observation("ko", maj_le="hier"), "_id": "1000"}
    observations, checkpoints, _col_obs, _col_cp = _depots(valides + [mauvais])
    worker = _worker(observations, checkpoints, Outbox(), env={})

    premier = asyncio.run(worker.auditer())
    second = asyncio.run(worker.auditer())

    assert premier == 0
    assert second == 1


def test_maj_le_utc_chaine_est_backfille_et_ne_bloque_pas():
    document = mongo_mesure.document_ingestion(_observation(
        "obs-chaine", maj_le="2026-11-05T09:00:00+00:00"))
    document["maj_le_utc"] = "2026-11-05T09:00:00.000000+00:00"  # chaîne legacy
    collection = CollectionMesure([document])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    assert asyncio.run(depot.compter_a_migrer(TENANT)) == 1
    assert asyncio.run(depot.auditer_lot(TENANT))[0] == 1
    assert asyncio.run(depot.lister_apres(TENANT, None, 10))[0]["id"] == "obs-chaine"
    assert asyncio.run(depot.remplir_maj_le_utc(TENANT)) == 1
    assert isinstance(collection.documents[0]["maj_le_utc"], datetime)
    assert asyncio.run(depot.compter_a_migrer(TENANT)) == 0


def test_worker_maj_le_utc_chaine_est_backfille_et_traite():
    document = mongo_mesure.document_ingestion(_observation(
        "obs-chaine", maj_le="2026-11-05T09:02:00+00:00"))
    document["maj_le_utc"] = "2026-11-05T09:02:00.000000+00:00"
    observations, checkpoints, _col_obs, _col_cp = _depots([document])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    premier = asyncio.run(worker.une_passe())

    assert premier["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-chaine"


def test_maj_le_illisible_est_audite_et_ne_bloque_pas_la_migration():
    observations, checkpoints, _col_obs, _col_cp = _depots([
        {"tenant_id": TENANT, "id": "obs-bad", "maj_le": "hier"},
        _observation("obs-1", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["outcomes"] == 1
    assert asyncio.run(checkpoints.lire(TENANT)).id == "obs-1"
    assert worker.metriques.mesure_auto_non_conformes == 1


def test_backfill_garde_ne_starve_pas_500_legacy_plus_5_nouveaux():
    legacy = [
        _observation(f"old-{rang}", maj_le=f"2026-11-05T08:{rang // 60:02d}:{rang % 60:02d}+00:00")
        for rang in range(500)
    ]
    nouveaux = [
        _observation(f"new-{rang}", maj_le=f"2026-11-05T09:0{rang + 1}:00+00:00")
        for rang in range(5)
    ]
    observations, checkpoints, _col_obs, _col_cp = _depots(legacy + nouveaux)
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox, lot=10)
    asyncio.run(checkpoints.ecrire(TENANT, mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T09:00:00+00:00", id="curseur")))

    premier = asyncio.run(worker.une_passe())
    second = asyncio.run(worker.une_passe())

    assert premier["outcomes"] == 0  # garde de migration : 5 docs restent à backfiller
    assert second["outcomes"] == 5
    assert {evenement["payload"]["mesure"]["observation_id"]
            for evenement in outbox.evenements.values()} == {
                f"new-{rang}" for rang in range(5)}


def test_type_bracketing_date_et_offset_non_utc_sont_lus_et_ordonnes():
    collection = CollectionMesure([
        _observation("obs-offset", maj_le="2026-11-05T12:00:00+02:00"),
        _observation("obs-date", maj_le=datetime(2026, 11, 5, 10, 0, 1, tzinfo=timezone.utc)),
        _observation("obs-late", maj_le="2026-11-05T10:00:02+00:00"),
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    documents = asyncio.run(depot.lister_apres(TENANT, None, 10))

    assert [document["id"] for document in documents] == [
        "obs-offset", "obs-date", "obs-late"]
    assert documents[0]["maj_le"] == "2026-11-05T10:00:00.000000+00:00"


def test_tie_breaker_mongo_ordonne_deux_documents_de_la_meme_seconde():
    collection = CollectionMesure([
        # Insertion volontairement inversée : `_id` est le tie-breaker monotone.
        {**_observation("obs-b", maj_le="2026-11-05T10:00:00+00:00"), "_id": "002"},
        {**_observation("obs-a", maj_le="2026-11-05T10:00:00+00:00"), "_id": "001"},
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    documents = asyncio.run(depot.lister_apres(TENANT, None, 10))

    assert [document["id"] for document in documents] == ["obs-a", "obs-b"]
    premier = mongo_mesure.CurseurObservation(
        maj_le=documents[0]["maj_le"], sequence="001", id="obs-a")
    suite = asyncio.run(depot.lister_apres(TENANT, premier, 10))
    assert [document["id"] for document in suite] == ["obs-b"]


def test_checkpoint_ne_regresse_jamais():
    collection = CollectionMesure()
    depot = mongo_mesure.DepotCheckpointsMesure(collection)
    recent = mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T10:00:02+00:00", id="obs-2")
    ancien = mongo_mesure.CurseurObservation(
        maj_le="2026-11-05T10:00:01+00:00", id="obs-1")

    asyncio.run(depot.ecrire(TENANT, recent))
    asyncio.run(depot.ecrire(TENANT, ancien))

    assert asyncio.run(depot.lire(TENANT)).id == "obs-2"


def test_rejets_permanent_transitoire_et_compteur():
    collection = CollectionMesure()
    depot = mongo_mesure.DepotRejetsMesure(collection)
    permanent = _observation("obs-permanent")
    transitoire = _observation("obs-transitoire")

    assert asyncio.run(depot.enregistrer(
        TENANT, permanent, "schéma invalide", permanent=True)) is True
    assert asyncio.run(depot.enregistrer(
        TENANT, transitoire, "timeout", permanent=False, tentatives_max=2)) is False
    assert asyncio.run(depot.enregistrer(
        TENANT, transitoire, "timeout", permanent=False, tentatives_max=2)) is True
    assert asyncio.run(depot.compter(TENANT, "dead")) == 2


def test_rediger_message_expurge_les_jetons_et_urls():
    message = mesure_auto_worker.rediger_message(
        "Bearer abcdefghijklmnop sk-1234567890 mongodb://user:secret@host/db")

    assert "abcdefghijklmnop" not in message
    assert "sk-1234567890" not in message
    assert "secret" not in message
    assert "[redacted]" in message


def test_validateur_json_schema_est_pose_si_la_base_expose_command():
    class Base:
        def __init__(self):
            self.commandes = []

        async def command(self, commande):
            self.commandes.append(commande)
            return {"ok": 1}

    class Collection:
        database = Base()
        name = mongo_mesure.OBSERVATIONS

    depot = mongo_mesure.DepotObservationsMesure(Collection())

    assert asyncio.run(depot.assurer_validateur()) is True
    assert depot.collection.database.commandes[0]["collMod"] == mongo_mesure.OBSERVATIONS
    assert "validator" in depot.collection.database.commandes[0]
