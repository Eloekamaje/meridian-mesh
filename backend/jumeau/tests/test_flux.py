"""Réponse au fil de l'eau : étapes, brouillon, puis réponse finale ; une erreur reste lisible."""
import json

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
