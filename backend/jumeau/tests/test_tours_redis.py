"""État partagé des tours : lecture depuis un autre worker, présence et fin.

Ces tests ne tournent qu'avec un Redis de test (`REDIS_URL`), et sous un préfixe unique.
"""
import asyncio
import os
import uuid

import pytest

from jumeau import partage, tours_redis
from jumeau.protocole import Traducteur

pytestmark = pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL absent")

PREFIX = f"test:{uuid.uuid4().hex}:"


@pytest.fixture(autouse=True)
def prefixe(monkeypatch):
    monkeypatch.setenv("REDIS_PREFIX", PREFIX)


def test_un_worker_lit_les_lignes_ecrites_par_un_autre():
    async def scenario():
        tour = tours_redis.TourRedis("travail-partage", "architecte")
        tour.traducteur = Traducteur("travail-partage", tour.id)
        await tour.creer()
        await tour.publier(tour.traducteur.debut())
        assert await tours_redis.actifs("architecte") == ["travail-partage"]

        await tour.terminer()
        lignes = [ligne async for ligne in tours_redis.lire(tour.id, 0)]
        assert lignes and all(ligne.startswith("id: ") and "data: " in ligne for ligne in lignes)
        premier = lignes[0].split("\n", 1)[0][4:]
        suite = [ligne async for ligne in tours_redis.lire(tour.id, premier)]
        assert len(suite) == len(lignes) - 1

        assert await tours_redis.actifs("architecte") == []
        assert (await tours_redis.etat_fin(tour.id))[1] is True

        r = await partage.client()
        cles = [cle async for cle in r.scan_iter(match=f"{PREFIX}*")]
        if cles:
            await r.delete(*cles)
        await partage.fermer()

    asyncio.run(scenario())


def test_un_worker_mort_est_reape_et_le_flux_recoit_une_erreur(monkeypatch):
    monkeypatch.setenv("TOUR_STALE", "0")

    async def scenario():
        tour = tours_redis.TourRedis("travail-orphelin", "architecte")
        tour.traducteur = Traducteur("travail-orphelin", tour.id)
        await tour.creer()
        await tour.publier(tour.traducteur.debut())
        r = await partage.client()
        await r.hset(tours_redis._meta(tour.id), "heartbeat", 0)
        await tours_redis.reaper()

        meta = await r.hgetall(tours_redis._meta(tour.id))
        assert meta.get("fini") == "1"
        assert meta.get("erreur") == "1"
        assert await tours_redis.actifs("architecte") == []
        lignes = await r.xrange(tours_redis._lignes(tour.id))
        assert any("RUN_ERROR" in champs.get("data", "") for _, champs in lignes)
        avant = len(lignes)
        await tour.publier(tour.traducteur.debut())  # un producteur réveillé ne doit plus écrire après le reaper
        assert len(await r.xrange(tours_redis._lignes(tour.id))) == avant
        tours_redis._LOCAUX.discard(tour.id)

        cles = [cle async for cle in r.scan_iter(match=f"{PREFIX}*")]
        if cles:
            await r.delete(*cles)
        await partage.fermer()

    asyncio.run(scenario())
