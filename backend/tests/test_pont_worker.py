"""Worker du pont canonique : flag, claim, bail, métriques, reprise et robustesse."""
from __future__ import annotations

import asyncio
import copy
import logging

import pytest

from aides_pont import CollectionPont, ConnexionPont, instant

from meridian.adapters.inbound.worker import pont_worker
from meridian.adapters.outbound.mongo import pont_canonique as pont_mongo
from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import pont_canonique as pont_pg
from meridian.application import pont_canonique as pont

CLE_PONT = "cle-de-test-pont-canonique-32"
CLE_INTERNE = "cle-de-test-pont-interne-32"


@pytest.fixture(autouse=True)
def _cle_pont(monkeypatch):
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE_PONT)
    monkeypatch.setenv(pont.PONT_KEY_INTERNE_ENV, CLE_INTERNE)


TENANT = "banque"


def _situation(**champs):
    base = {
        "id": "sit-1",
        "tenant_id": TENANT,
        "titre": "Délai en hausse",
        "resume": "Le délai dépasse la cible.",
        "statut": "décidée",
        "priorite": "haute",
        "decision": "Automatiser",
        "decidee_le": "2026-11-06T10:00:00+00:00",
        "detectee": "2026-11-05T09:00:00+00:00",
        "cree_le": "2026-11-05T09:00:00+00:00",
        "jumeaux": ["paiements"],
    }
    base.update(champs)
    return base


def _evenement(**champs):
    champs.setdefault("maintenant", instant())
    champs.setdefault("source_event_id", "maj-1")
    return pont.evenement_depuis_situation(_situation(), **champs)


class DepotEspion:
    """Dépôt qui refuse toute sollicitation : prouve qu'un flag off ne touche à rien."""

    def __init__(self):
        self.appels = []

    async def reprendre_expires(self, *args, **kwargs):
        self.appels.append("reprendre_expires")
        raise AssertionError("le worker ne doit rien faire quand le flag est off")

    async def reclamer(self, *args, **kwargs):
        self.appels.append("reclamer")
        raise AssertionError("le worker ne doit rien faire quand le flag est off")

    async def statistiques(self, *args, **kwargs):
        self.appels.append("statistiques")
        raise AssertionError("le worker ne doit rien faire quand le flag est off")


def test_flag_off_par_defaut_le_worker_ne_traite_rien(monkeypatch):
    monkeypatch.delenv(pont_worker.FLAG_ENV, raising=False)
    depot = DepotEspion()
    worker = pont_worker.WorkerPont(depot, lambda evenement: pytest.fail("ne doit pas être appelé"))

    bilan = asyncio.run(worker.une_passe())

    assert bilan["actif"] is False
    assert bilan["traites"] == 0
    assert depot.appels == []
    assert pont_worker.actif({pont_worker.FLAG_ENV: "0"}) is False
    assert pont_worker.actif({pont_worker.FLAG_ENV: "1"}) is True
    assert pont_worker.actif({pont_worker.FLAG_ENV: "oui"}) is True


def test_flag_on_traite_l_evenement_et_le_marque_done(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        evenement = _evenement()
        await depot.enfiler(evenement)
        conn = ConnexionPont()
        worker = pont_worker.WorkerPont(
            depot, lambda ev: pont_pg.appliquer_evenement(conn, ev),
            worker_id="worker-a", maintenant=lambda: instant())
        bilan = await worker.une_passe()
        return collection, conn, evenement, bilan

    collection, conn, evenement, bilan = asyncio.run(scenario())

    assert bilan["actif"] is True
    assert bilan["reussis"] == 1 and bilan["echecs"] == 0
    assert collection.documents[0]["etat"] == "done"
    assert collection.documents[0]["canonical_ids"] == evenement["canonical_ids"]
    assert collection.documents[0]["locked_until"] is None
    assert set(conn.stock) == {(TENANT, identifiant) for identifiant in evenement["canonical_ids"]}


def test_une_erreur_marque_failed_et_ne_remonte_pas(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement())
        worker = pont_worker.WorkerPont(
            depot, lambda ev: (_ for _ in ()).throw(RuntimeError("panne applicative")),
            worker_id="worker-a", maintenant=lambda: instant())
        bilan = await worker.une_passe()
        return collection, bilan

    collection, bilan = asyncio.run(scenario())

    assert bilan["reussis"] == 0 and bilan["echecs"] == 1
    assert collection.documents[0]["etat"] == "failed"
    assert collection.documents[0]["tentatives"] == 1
    assert "panne applicative" in collection.documents[0]["derniere_erreur"]
    assert collection.documents[0]["prochaine_tentative"] > instant()


def test_un_evenement_failed_est_repris_apres_l_echeance(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement())
        appels = {"n": 0}

        def appliquer(ev):
            appels["n"] += 1
            if appels["n"] == 1:
                raise RuntimeError("première panne")
            return {"canonical_ids": ev["canonical_ids"], "ecrits": ev["canonical_ids"]}

        worker = pont_worker.WorkerPont(
            depot, appliquer, worker_id="worker-a", maintenant=lambda: instant())
        premier = await worker.une_passe()
        # Le backoff est encore actif : une seconde passe immédiate ne fait rien.
        deuxieme = await worker.une_passe()
        collection.documents[0]["disponible_le"] = "2026-11-06T11:00:00+00:00"
        collection.documents[0]["prochaine_tentative"] = "2026-11-06T11:00:00+00:00"
        troisieme = await worker.une_passe()
        return collection, premier, deuxieme, troisieme, appels

    collection, premier, deuxieme, troisieme, appels = asyncio.run(scenario())

    assert premier["echecs"] == 1 and premier["reussis"] == 0
    assert deuxieme["traites"] == 0
    assert troisieme["reussis"] == 1
    assert appels["n"] == 2
    assert collection.documents[0]["etat"] == "done"


def test_rollback_au_troisieme_objet_marque_failed_puis_retry(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")
    vrai = entreprise_depot.enregistrer_objet

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement())
        conn = ConnexionPont()
        compteur = {"appels": 0}

        def echouer_au_troisieme(conn_, tenant, objet, **options):
            compteur["appels"] += 1
            if compteur["appels"] == 3:
                raise RuntimeError("panne injectée au 3e objet")
            return vrai(conn_, tenant, objet, **options)

        monkeypatch.setattr(entreprise_depot, "enregistrer_objet", echouer_au_troisieme)
        worker = pont_worker.WorkerPont(
            depot, lambda ev: pont_pg.appliquer_evenement(conn, ev),
            worker_id="worker-a", maintenant=lambda: instant())
        premier = await worker.une_passe()
        stock_apres_echec = dict(conn.stock)
        etat_apres_echec = collection.documents[0]["etat"]
        erreur_apres_echec = collection.documents[0]["derniere_erreur"]

        monkeypatch.setattr(entreprise_depot, "enregistrer_objet", vrai)
        collection.documents[0]["disponible_le"] = "2026-11-06T11:00:00+00:00"
        collection.documents[0]["prochaine_tentative"] = "2026-11-06T11:00:00+00:00"
        second = await worker.une_passe()
        return (collection, conn, premier, stock_apres_echec, etat_apres_echec,
                erreur_apres_echec, second)

    (collection, conn, premier, stock_apres_echec, etat_apres_echec,
     erreur_apres_echec, second) = asyncio.run(scenario())

    assert premier["echecs"] == 1 and premier["reussis"] == 0
    assert stock_apres_echec == {}
    assert etat_apres_echec == "failed"
    assert "panne injectée au 3e objet" in erreur_apres_echec
    assert second["reussis"] == 1
    assert collection.documents[0]["etat"] == "done"
    assert len(conn.stock) == 3


def test_conflit_d_origine_marque_failed_et_conserve_l_objet(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        await depot.enfiler(_evenement())
        conn = ConnexionPont()
        existant = {
            "id": "sit-1", "tenant_id": TENANT, "famille": "emergence", "type": "SITUATION",
            "mode": "DECLARED", "titre": "Version canonique",
            "donnees": {"origine": "api-canonique"}, "version": 7,
            "observe_le": instant(), "valide_depuis": instant(), "valide_jusqua": None,
            "cree_le": instant(), "maj_le": instant(),
        }
        conn.stock[(TENANT, "sit-1")] = copy.deepcopy(existant)
        worker = pont_worker.WorkerPont(
            depot, lambda ev: pont_pg.appliquer_evenement(conn, ev),
            worker_id="worker-a", maintenant=lambda: instant())
        bilan = await worker.une_passe()
        return collection, conn, existant, bilan

    collection, conn, existant, bilan = asyncio.run(scenario())

    assert bilan["echecs"] == 1
    assert collection.documents[0]["etat"] == "dead"
    assert "origine" in collection.documents[0]["derniere_erreur"]
    assert conn.stock[(TENANT, "sit-1")] == existant
    assert conn.ecritures == []


def test_tenant_mismatch_marque_failed_sans_ecriture(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        evenement = _evenement()
        evenement["payload"]["situation"]["tenant_id"] = "assurance"
        evenement["source"]["hash"] = pont.hash_contenu(evenement["payload"])
        evenement["hash"] = pont.hash_contenu(evenement["payload"])
        evenement = pont.signer_evenement(evenement)
        await depot.enfiler(evenement)
        conn = ConnexionPont()
        worker = pont_worker.WorkerPont(
            depot, lambda ev: pont_pg.appliquer_evenement(conn, ev),
            worker_id="worker-a", maintenant=lambda: instant())
        bilan = await worker.une_passe()
        return collection, conn, bilan

    collection, conn, bilan = asyncio.run(scenario())

    assert bilan["echecs"] == 1
    assert collection.documents[0]["etat"] == "dead"
    assert conn.stock == {} and conn.ecritures == []


def test_un_echec_de_terminer_par_fencing_n_ecrase_pas_l_etat(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class DepotFencing:
        def __init__(self):
            self.evenement = pont.signer_evenement({
                "_id": "evt-1", "etat": "pending", "lock_token": "jeton-a",
                "locked_until": "2026-11-06T12:00:00+00:00", "canonical_ids": ["sit-1"],
                "tentatives": 0,
            })
            self.termine = False
            self._servi = False

        async def reprendre_expires(self):
            return 0

        async def reclamer(self, worker_id, limite=1, bail_secondes=60):
            if self._servi:
                return []
            self._servi = True
            return [dict(self.evenement)]

        async def terminer(self, identifiant, jeton, canonical_ids=None, resultat=None):
            self.termine = True
            return False

        async def echouer(self, identifiant, jeton, erreur):
            raise AssertionError("un échec de fencing ne doit pas marquer failed")

        async def statistiques(self):
            return {"pont_events_pending": 0, "pont_lag_seconds": 0.0}

    depot = DepotFencing()
    worker = pont_worker.WorkerPont(
        depot, lambda ev: {"canonical_ids": ev["canonical_ids"]},
        worker_id="worker-a", maintenant=lambda: instant())

    bilan = asyncio.run(worker.une_passe())

    assert depot.termine is True
    assert bilan["reussis"] == 0
    assert bilan["ignores"] == 1
    assert bilan["echecs"] == 0


def test_le_lot_est_borne_et_les_metriques_sont_nommees(monkeypatch, caplog):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        for rang in range(5):
            await depot.enfiler(pont.evenement_depuis_situation(
                _situation(id=f"sit-{rang}"), source_event_id=f"maj-{rang}",
                maintenant=instant()))
        worker = pont_worker.WorkerPont(
            depot, lambda ev: {"canonical_ids": ev["canonical_ids"]},
            worker_id="worker-a", lot=2, maintenant=lambda: instant())
        return worker, await worker.une_passe()

    with caplog.at_level(logging.INFO, logger="meridian.pont_worker"):
        worker, bilan = asyncio.run(scenario())

    assert bilan["traites"] == 2
    instantane = worker.metriques.instantane()
    assert set(instantane) >= {
        "pont_events_pending", "pont_lag_seconds", "pont_failed_total",
        "pont_apply_duration_seconds"}
    texte = caplog.text
    assert "pont_apply_duration_seconds" in texte
    assert "pont_events_pending" in texte
    assert "pont_events_failed" in texte
    assert "pont_events_dead" in texte
    assert "pont_lag_seconds" in texte


def test_une_panne_de_claim_ne_remonte_pas(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class DepotEnPanne:
        async def reprendre_expires(self):
            return 0

        async def reclamer_lot(self, *args, **kwargs):
            raise RuntimeError("mongo indisponible")

        async def statistiques(self):
            return {"pont_events_pending": 0, "pont_lag_seconds": 0.0}

    worker = pont_worker.WorkerPont(
        DepotEnPanne(), lambda ev: pytest.fail("ne doit pas être appelé"),
        worker_id="worker-a")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["actif"] is True
    assert bilan["echecs"] == 1 and bilan["traites"] == 0


def test_une_panne_de_statistiques_ne_remonte_pas(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class DepotSansStats:
        async def reprendre_expires(self):
            return 0

        async def reclamer_lot(self, *args, **kwargs):
            return []

        async def statistiques(self):
            raise RuntimeError("stats indisponibles")

    worker = pont_worker.WorkerPont(DepotSansStats(), lambda ev: None,
                                    worker_id="worker-a")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["traites"] == 0


def test_tourner_s_arrete_proprement(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class DepotVide:
        def __init__(self):
            self.passes = 0

        async def reprendre_expires(self):
            return 0

        async def reclamer_lot(self, *args, **kwargs):
            self.passes += 1
            return []

        async def statistiques(self):
            return {"pont_events_pending": 0, "pont_lag_seconds": 0.0}

    async def scenario():
        depot = DepotVide()
        worker = pont_worker.WorkerPont(depot, lambda ev: None,
                                        worker_id="worker-a", intervalle=0.01)
        tache = asyncio.create_task(worker.tourner())
        await asyncio.sleep(0.03)
        worker.arreter()
        await tache
        return depot

    depot = asyncio.run(scenario())

    assert depot.passes >= 1


def test_une_panne_de_reprise_ou_de_terminer_ne_remonte_pas(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class Depot:
        def __init__(self):
            self._servi = False

        async def reprendre_expires(self):
            raise RuntimeError("reprise indisponible")

        async def reclamer_lot(self, *args, **kwargs):
            if self._servi:
                return []
            self._servi = True
            return [pont.signer_evenement(
                {"_id": "evt-1", "lock_token": "jeton", "canonical_ids": []})]

        async def terminer(self, *args, **kwargs):
            raise RuntimeError("terminaison indisponible")

        async def statistiques(self):
            return {}

    worker = pont_worker.WorkerPont(
        Depot(), lambda ev: {"canonical_ids": []}, worker_id="worker-a")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["ignores"] == 1
    assert bilan["echecs"] == 0


def test_une_panne_d_echouer_ne_remonte_pas(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class Depot:
        def __init__(self):
            self._servi = False

        async def reprendre_expires(self):
            return 0

        async def reclamer_lot(self, *args, **kwargs):
            if self._servi:
                return []
            self._servi = True
            return [pont.signer_evenement(
                {"_id": "evt-1", "lock_token": "jeton", "canonical_ids": []})]

        async def echouer(self, *args, **kwargs):
            raise RuntimeError("échec indisponible")

        async def statistiques(self):
            return {}

    worker = pont_worker.WorkerPont(
        Depot(), lambda ev: (_ for _ in ()).throw(RuntimeError("panne")),
        worker_id="worker-a")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["echecs"] == 1
    assert worker.metriques.pont_failed_total == 1


def test_worker_reclame_un_evenement_a_la_fois_et_verifie_le_bail(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")
    sequence = []

    class Depot:
        def __init__(self):
            self.evenements = [_evenement(source_event_id="maj-1"),
                               _evenement(source_event_id="maj-2")]
            self.index = 0

        async def reprendre_expires(self):
            return 0

        async def reclamer(self, *args, **kwargs):
            sequence.append("claim")
            if self.index >= len(self.evenements):
                return None
            evenement = self.evenements[self.index]
            self.index += 1
            return evenement

        async def verifier_bail(self, *args, **kwargs):
            sequence.append("bail")
            return True

        async def terminer(self, *args, **kwargs):
            sequence.append("terminer")
            return True

        async def statistiques(self):
            return {}

    def appliquer(evenement):
        sequence.append("apply")
        return {"canonical_ids": evenement["canonical_ids"]}

    worker = pont_worker.WorkerPont(
        Depot(), appliquer, worker_id="worker-a", lot=2)

    bilan = asyncio.run(worker.une_passe())

    assert bilan["traites"] == 2 and bilan["reussis"] == 2
    assert sequence == ["claim", "bail", "apply", "terminer",
                        "claim", "bail", "apply", "terminer"]


def test_worker_n_applique_pas_si_le_bail_est_perdu(monkeypatch):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")

    class DepotBailPerdu:
        def __init__(self):
            self._servi = False

        async def reprendre_expires(self):
            return 0

        async def reclamer(self, *args, **kwargs):
            if self._servi:
                return None
            self._servi = True
            return _evenement()

        async def verifier_bail(self, *args, **kwargs):
            return False

        async def statistiques(self):
            return {}

    worker = pont_worker.WorkerPont(
        DepotBailPerdu(), lambda ev: pytest.fail("le bail est perdu"),
        worker_id="worker-a")

    bilan = asyncio.run(worker.une_passe())

    assert bilan["ignores"] == 1 and bilan["reussis"] == 0


def test_worker_filtre_les_tenants_et_borne_les_timeouts():
    async def scenario():
        collection = CollectionPont()
        depot = pont_mongo.DepotPontCanonique(collection, horloge=lambda: instant())
        for tenant in ("banque", "assurance"):
            evenement = _evenement(source_event_id=f"maj-{tenant}")
            evenement["tenant_id"] = tenant
            evenement["_id"] = f"evt-{tenant}"
            evenement["etat"] = "pending"
            evenement["disponible_le"] = instant()
            evenement["cree_le"] = instant()
            collection.documents.append(evenement)
        resultat = await depot.reclamer_lot("worker-a", limite=1, tenants=["banque"])
        return resultat

    resultat = asyncio.run(scenario())

    assert [evenement["tenant_id"] for evenement in resultat] == ["banque"]
    assert "statement_timeout" in pont_worker.DSN_OPTIONS
    assert "lock_timeout" in pont_worker.DSN_OPTIONS
    assert 30 < 60  # statement_timeout (30 s) < bail par défaut (60 s)


def test_metriques_vides_ont_des_valeurs_neutres():
    instantane = pont_worker.MetriquesPont().instantane()

    assert instantane["pont_events_pending"] == 0
    assert instantane["pont_lag_seconds"] == 0.0
    assert instantane["pont_failed_total"] == 0
    assert instantane["pont_apply_duration_seconds"]["count"] == 0


def test_cli_once_avec_flag_off_sort_sans_connexion(monkeypatch, capsys):
    monkeypatch.delenv(pont_worker.FLAG_ENV, raising=False)

    code = pont_worker.principal(["--once"])

    capture = capsys.readouterr()
    assert code == 0
    assert "désactivé" in capture.out.lower()


def test_cli_flag_on_sans_configuration_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE_PONT)
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("JUMEAU_WORKER_PG_DSN", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)

    code = pont_worker.principal(["--once"])

    capture = capsys.readouterr()
    assert code == 2
    assert "MONGO_URL" in capture.err


def test_cli_flag_on_sans_dsn_retourne_2(monkeypatch, capsys):
    monkeypatch.setenv(pont_worker.FLAG_ENV, "1")
    monkeypatch.setenv(pont.PONT_KEY_ENV, CLE_PONT)
    monkeypatch.delenv("JUMEAU_WORKER_PG_DSN", raising=False)
    monkeypatch.delenv("JUMEAU_PG_DSN", raising=False)

    code = pont_worker.principal(["--once", "--mongo-url", "mongodb://localhost"])

    capture = capsys.readouterr()
    assert code == 2
    assert "DSN" in capture.err
