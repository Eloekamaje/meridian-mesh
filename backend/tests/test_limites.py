"""Limiteur de débit (mémoire et Redis) et garde-fou CORS : unités sans serveur."""
import asyncio

import pytest

import limites


@pytest.fixture(autouse=True)
def compteurs_propres():
    limites.reinitialiser()
    yield
    limites.reinitialiser()


def test_un_maximum_nul_ou_negatif_desactive_la_limite():
    assert asyncio.run(limites.autoriser("libre", 0, 60)) is True
    assert asyncio.run(limites.autoriser("libre", -3, 60)) is True


def test_le_compteur_memoire_refuse_au_dela_du_maximum():
    async def scenario():
        return [await limites.autoriser("tours:a", 2, 60) for _ in range(3)]
    assert asyncio.run(scenario()) == [True, True, False]


def test_les_cles_ne_partagent_pas_leur_compteur():
    async def scenario():
        return (await limites.autoriser("a", 1, 60), await limites.autoriser("b", 1, 60))
    assert asyncio.run(scenario()) == (True, True)


def test_la_fenetre_expiree_redonne_des_jetons(monkeypatch):
    horloge = [100.0]
    monkeypatch.setattr(limites.time, "monotonic", lambda: horloge[0])

    async def scenario():
        avant = [await limites.autoriser("tours:b", 1, 60) for _ in range(2)]
        horloge[0] += 61
        return avant, await limites.autoriser("tours:b", 1, 60)
    assert asyncio.run(scenario()) == ([True, False], True)


def test_maximum_lit_l_environnement_et_retombe_sur_le_defaut(monkeypatch):
    monkeypatch.setenv("UNE_LIMITE", "7")
    assert limites.maximum("UNE_LIMITE", 3) == 7
    monkeypatch.setenv("UNE_LIMITE", "illisible")
    assert limites.maximum("UNE_LIMITE", 3) == 3
    monkeypatch.delenv("UNE_LIMITE")
    assert limites.maximum("UNE_LIMITE", 3) == 3


def test_les_tours_sont_plafonnes_par_defaut_en_production_seulement(monkeypatch):
    monkeypatch.delenv(limites.TOURS_RATE_MAX, raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert limites.maxi_tours() == 0
    monkeypatch.setenv("APP_ENV", "production")
    assert limites.maxi_tours() == limites.MAX_TOURS_PRODUCTION
    monkeypatch.setenv(limites.TOURS_RATE_MAX, "5")
    assert limites.maxi_tours() == 5


def test_le_limiteur_partage_utilise_un_script_lua_atomique(monkeypatch):
    class FauxRedis:
        def __init__(self):
            self.compte = 0
            self.appels = []

        async def eval(self, script, nombre_cles, cle, fenetre):
            self.compte += 1
            self.appels.append((script, nombre_cles, cle, fenetre))
            return self.compte

    faux = FauxRedis()

    async def client():
        return faux

    monkeypatch.setattr(limites.partage, "actif", lambda: True)
    monkeypatch.setattr(limites.partage, "client", client)
    monkeypatch.setattr(limites.partage, "prefixe", lambda: "test:")

    async def scenario():
        return [await limites.autoriser("tours:c", 2, 30) for _ in range(3)]
    assert asyncio.run(scenario()) == [True, True, False]
    assert [(nombre, cle, fenetre) for _, nombre, cle, fenetre in faux.appels] == [
        (1, "test:limites:tours:c", 30)] * 3
    assert all("INCR" in script and "EXPIRE" in script for script, *_ in faux.appels)
    assert all("redis.call" in script for script, *_ in faux.appels)


def test_une_panne_redis_laisse_passer_et_journalise(monkeypatch, caplog):
    class FauxRedis:
        async def eval(self, *args):
            raise ConnectionError("redis absent")

    async def client():
        return FauxRedis()

    monkeypatch.setattr(limites.partage, "actif", lambda: True)
    monkeypatch.setattr(limites.partage, "client", client)
    monkeypatch.setattr(limites.partage, "prefixe", lambda: "test:")

    with caplog.at_level("WARNING", logger="meridian.limites"):
        assert asyncio.run(limites.autoriser("tours:d", 1, 30)) is True
        assert asyncio.run(limites.autoriser("tours:d", 1, 30)) is True
    assert "limiteur Redis indisponible" in caplog.text


def test_cors_refuse_le_joker_en_production_et_l_accepte_ailleurs():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        limites.verifier_cors(["*"], "production")
    assert limites.verifier_cors(["https://meridian.example", " https://app.example "], "production") == [
        "https://meridian.example", "https://app.example"]
    assert limites.verifier_cors(["*"], "development") == ["*"]


def test_cors_lit_app_env_quand_il_n_est_pas_fourni(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        limites.verifier_cors(["*"])
    monkeypatch.setenv("APP_ENV", "test")
    assert limites.verifier_cors(["*"]) == ["*"]
