"""Worker de mesure automatique : flag, checkpoint, idempotence et isolation tenant.

Le worker ne touche jamais Postgres : il lit une collection d'observations Mongo, construit des
Outcomes avec le module pur, et les enfile dans l'outbox C1 (``pont_canonique``).
"""
from __future__ import annotations

import asyncio
import copy

import pytest

from meridian.tests.aides_mesure_auto import CollectionMesure

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
            env=None, depuis=None):
    return mesure_auto_worker.WorkerMesureAuto(
        observations=observations,
        checkpoints=checkpoints,
        enfiler=outbox.enfiler,
        tenants=tenants,
        lot=lot,
        env=env if env is not None else {mesure_auto_worker.FLAG_ENV: "1"},
        depuis=depuis,
        maintenant=lambda: "2026-11-07T12:00:00+00:00",
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
    assert bilan["doublons"] == 0 and bilan["ignores"] == 0 and bilan["echecs"] == 0
    assert outbox.operations() == [pont.OPERATION_OUTCOME, pont.OPERATION_OUTCOME]
    assert {e["tenant_id"] for e in outbox.evenements.values()} == {TENANT}
    checkpoint = asyncio.run(checkpoints.lire(TENANT))
    assert checkpoint["dernier_id"] == "obs-2"
    assert checkpoint["dernier_maj_le"] == "2026-11-05T09:02:00+00:00"


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
    assert asyncio.run(checkpoints.lire(TENANT))["dernier_id"] == "obs-2"


def test_observation_incomplete_est_ignoree_mais_le_checkpoint_avance():
    incomplete = _observation("obs-1")
    incomplete.pop("observe")
    observations, checkpoints, _col_obs, _col_cp = _depots([
        incomplete,
        _observation("obs-2", maj_le="2026-11-05T09:02:00+00:00"),
    ])
    outbox = Outbox()
    worker = _worker(observations, checkpoints, outbox)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["lues"] == 2
    assert bilan["ignores"] == 1 and bilan["outcomes"] == 1
    assert len(outbox.evenements) == 1
    assert asyncio.run(checkpoints.lire(TENANT))["dernier_id"] == "obs-2"


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

    col_obs.documents[0]["observe"] = 8
    col_obs.documents[0]["maj_le"] = "2026-11-06T09:00:00+00:00"
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
    assert cp_banque["dernier_id"] == "obs-banque"
    assert cp_assurance["dernier_id"] == "obs-assurance"


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

    premier = asyncio.run(depot.lister_apres(TENANT, None, None, 10))
    second = asyncio.run(depot.lister_apres(
        TENANT, "2026-11-05T09:00:00+00:00", "obs-1", 10))

    assert [document["id"] for document in premier] == ["obs-1", "obs-2"]
    assert [document["id"] for document in second] == ["obs-2"]
    assert collection.appels[0][1]["tenant_id"] == TENANT


def test_depot_checkpoints_lit_et_ecrit_un_document_par_tenant():
    collection = CollectionMesure()
    depot = mongo_mesure.DepotCheckpointsMesure(collection)

    assert asyncio.run(depot.lire(TENANT)) is None
    asyncio.run(depot.ecrire(TENANT, "2026-11-05T09:01:00+00:00", "obs-2"))
    asyncio.run(depot.ecrire(AUTRE, "2026-11-06T09:00:00+00:00", "obs-9"))

    assert asyncio.run(depot.lire(TENANT))["dernier_id"] == "obs-2"
    assert asyncio.run(depot.lire(AUTRE))["dernier_id"] == "obs-9"
    assert len(collection.documents) == 2


def test_depot_checkpoints_refuse_un_curseur_incomplet():
    depot = mongo_mesure.DepotCheckpointsMesure(CollectionMesure())

    with pytest.raises(ValueError):
        asyncio.run(depot.ecrire(TENANT, "", "obs-1"))
    with pytest.raises(ValueError):
        asyncio.run(depot.ecrire(TENANT, "2026-11-05T09:00:00+00:00", ""))


def test_depot_observations_borne_et_indexe():
    collection = CollectionMesure([
        _observation("obs-1", maj_le="2026-11-05T09:00:00+00:00"),
        _observation("obs-2", maj_le="2026-11-05T09:01:00+00:00"),
    ])
    depot = mongo_mesure.DepotObservationsMesure(collection)

    lot = asyncio.run(depot.lister_apres(TENANT, None, None, 1))
    index = asyncio.run(depot.assurer_index())

    assert [document["id"] for document in lot] == ["obs-1"]
    assert len(index) == 2 and collection.index[0][0][0] == ("tenant_id", 1)


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
        "mesure_auto_doublons": 0, "mesure_auto_ignores": 0,
        "mesure_auto_echecs": 0,
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

    assert asyncio.run(worker._avancer(TENANT, {"id": "obs-1"})) is False
    assert asyncio.run(worker._avancer(TENANT, {"maj_le": "2026-11-05T09:00:00+00:00"})) is False

    class CheckpointsEnPanne:
        async def lire(self, tenant):
            return None

        async def ecrire(self, *args, **kwargs):
            raise RuntimeError("mongo indisponible")

    worker = mesure_auto_worker.WorkerMesureAuto(
        observations, CheckpointsEnPanne(), Outbox().enfiler,
        tenants=(TENANT,), env={mesure_auto_worker.FLAG_ENV: "1"})
    assert asyncio.run(worker._avancer(
        TENANT, {"id": "obs-1", "maj_le": "2026-11-05T09:00:00+00:00"})) is False


def test_une_panne_sur_un_tenant_ne_bloque_pas_les_autres():
    class ObservationsParTenant:
        def __init__(self, depot_autre):
            self.depot_autre = depot_autre

        async def lister_apres(self, tenant, maj_le=None, identifiant=None, limite=100):
            if tenant == TENANT:
                raise RuntimeError("lecture impossible pour ce tenant")
            return await self.depot_autre.lister_apres(
                tenant, maj_le, identifiant, limite)

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
    assert asyncio.run(checkpoints.lire(TENANT))["dernier_id"] == "obs-2"


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
