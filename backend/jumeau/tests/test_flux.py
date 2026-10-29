"""Réponse au fil de l'eau : étapes, brouillon, puis réponse finale ; une erreur reste lisible."""
import json

import pytest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jumeau import flux


def evenements(produire):
    app = FastAPI()
    app.post("/f")(lambda: flux.en_flux(produire))
    texte = TestClient(app).post("/f").text
    return [json.loads(l[6:]) for l in texte.splitlines() if l.startswith("data: ")]


def test_etapes_brouillon_puis_final():
    async def produire(emit):
        await emit({"type": "etape", "libelle": "Je regarde Conduit…"})
        await emit({"type": "texte", "delta": "Publier "})
        await emit({"type": "relecture"})
        return {"reponse": "Publier un article.", "relu": True}
    assert [e["type"] for e in evenements(produire)] == ["etape", "texte", "relecture", "final"]
    assert evenements(produire)[-1]["reponse"]["relu"] is True


def test_erreur_lisible_sans_fuite():
    async def refuse(emit):
        raise HTTPException(404, "Travail introuvable")

    async def panne(emit):
        raise RuntimeError("secret interne")
    assert evenements(refuse) == [{"type": "erreur", "message": "Travail introuvable"}]
    assert evenements(panne) == [{"type": "erreur", "message": "Flore est momentanément injoignable."}]


# ---- arrêt : la déconnexion annule la génération et le brouillon écrit est remis au rappel ----
import asyncio


def _lancer(produire, **kw):
    return flux.en_flux(produire, **kw).body_iterator


def test_fermeture_du_flux_annule_et_remet_le_brouillon():
    etat = {"annule": False, "brouillon": None}

    async def produire(emit):
        await emit({"type": "texte", "delta": "Bon"})
        await emit({"type": "texte", "delta": "jour"})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            etat["annule"] = True
            raise

    async def sur_interruption(brouillon):
        etat["brouillon"] = brouillon

    async def scenario():
        it = _lancer(produire, sur_interruption=sur_interruption)
        await it.__anext__()
        await it.__anext__()
        await it.aclose()  # le client est parti
        await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
    asyncio.run(scenario())
    assert etat == {"annule": True, "brouillon": "Bonjour"}


def test_requete_deconnectee_annule_sans_attendre_la_fermeture():
    etat = {"annule": False, "brouillon": None}

    class Requete:
        def __init__(self):
            self.parti = False

        async def is_disconnected(self):
            return self.parti

    async def produire(emit):
        await emit({"type": "texte", "delta": "Début"})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            etat["annule"] = True
            raise

    async def sur_interruption(brouillon):
        etat["brouillon"] = brouillon

    async def scenario():
        requete = Requete()
        it = _lancer(produire, sur_interruption=sur_interruption, requete=requete)
        await it.__anext__()
        requete.parti = True
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(it.__anext__(), 5)
        await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
    asyncio.run(scenario())
    assert etat == {"annule": True, "brouillon": "Début"}


def test_pas_d_interruption_quand_la_reponse_est_finie():
    appels = []

    async def produire(emit):
        await emit({"type": "texte", "delta": "ok"})
        return {"reponse": "ok"}

    async def sur_interruption(brouillon):
        appels.append(brouillon)

    async def scenario():
        it = _lancer(produire, sur_interruption=sur_interruption)
        async for _ in it:
            pass
        await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
    asyncio.run(scenario())
    assert appels == []


def test_sans_rappel_la_reponse_se_termine_quand_meme():
    fini = []

    async def produire(emit):
        await emit({"type": "texte", "delta": "x"})
        await asyncio.sleep(0.05)
        fini.append(True)
        return {}

    async def scenario():
        it = _lancer(produire)
        await it.__anext__()
        await it.aclose()
        await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
    asyncio.run(scenario())
    assert fini == [True]
