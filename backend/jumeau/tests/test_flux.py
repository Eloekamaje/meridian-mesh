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
    assert [e["type"] for e in evenements(produire)] == [
        "RUN_STARTED", "STEP_STARTED", "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END", "CUSTOM",
        "STEP_FINISHED", "RUN_FINISHED"]
    assert evenements(produire)[-1]["result"]["relu"] is True


def test_erreur_lisible_sans_fuite():
    async def refuse(emit):
        raise HTTPException(404, "Travail introuvable")

    async def panne(emit):
        raise RuntimeError("secret interne")
    assert evenements(refuse)[1:] == [{"type": "RUN_ERROR", "message": "Travail introuvable"}]
    assert evenements(panne)[1:] == [{"type": "RUN_ERROR", "message": "Flore est momentanément injoignable."}]


# ---- arrêt : seul « Arrêter » annule ; un lecteur qui part laisse le tour se terminer ----
import asyncio


def _lancer(produire, **kw):
    return flux.en_flux(produire, **kw).body_iterator


def _tour(ligne):
    return json.loads(ligne[6:])["runId"]


def test_arreter_annule_remet_le_brouillon_et_finit_le_tour_cancelled():
    etat = {"annule": False, "brouillon": None}

    async def produire(emit):
        await emit({"type": "texte", "delta": "Bon"})
        await emit({"type": "texte", "delta": "jour"})
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            etat["annule"] = True
            raise

    async def sur_interruption(brouillon, activite=None):
        etat["brouillon"] = brouillon

    async def scenario():
        it = _lancer(produire, sur_interruption=sur_interruption, proprietaire="moi")
        tour = _tour(await it.__anext__())
        assert await flux.arreter(tour, "quelqu'un d'autre") is False
        assert await flux.arreter(tour, "moi") is True
        reste = [json.loads(l[6:]) async for l in it]
        assert reste[-1] == {"type": "RUN_FINISHED", "threadId": tour, "runId": tour, "outcome": {"type": "cancelled"}}
        assert await flux.arreter(tour, "moi") is False  # déjà fini
    asyncio.run(scenario())
    assert etat == {"annule": True, "brouillon": "Bonjour"}


def test_un_lecteur_qui_part_n_annule_rien_le_tour_se_termine():
    etat = {"interrompu": False, "fini": False}

    class Requete:
        def __init__(self):
            self.parti = False

        async def is_disconnected(self):
            return self.parti

    async def produire(emit):
        await emit({"type": "texte", "delta": "Début"})
        await asyncio.sleep(0.6)
        etat["fini"] = True
        return {"reponse": "Début et fin"}

    async def sur_interruption(brouillon, activite=None):
        etat["interrompu"] = True

    async def scenario():
        requete = Requete()
        it = _lancer(produire, sur_interruption=sur_interruption, requete=requete)
        tour = _tour(await it.__anext__())
        while "TEXT_MESSAGE_CONTENT" not in await it.__anext__():
            pass
        requete.parti = True
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(it.__anext__(), 5)  # ce lecteur s'arrête…
        await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
        # … le tour non : la reprise lit tout, jusqu'à la réponse relue
        reprise = [json.loads(l[6:]) async for l in flux.TOURS[tour].lire(0)]
        assert reprise[-1]["type"] == "RUN_FINISHED" and reprise[-1]["result"] == {"reponse": "Début et fin"}
    asyncio.run(scenario())
    assert etat == {"interrompu": False, "fini": True}


def test_pas_d_interruption_quand_la_reponse_est_finie():
    appels = []

    async def produire(emit):
        await emit({"type": "texte", "delta": "ok"})
        return {"reponse": "ok"}

    async def sur_interruption(brouillon, activite=None):
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


def test_l_activite_suit_etapes_et_outils_dans_l_ordre_sans_muter():
    a = flux.Activite()
    a.suivre({"type": "etape", "libelle": "Je regarde Conduit…"})
    a.suivre({"type": "outil", "id": "u1", "nom": "lire_code", "libelle": "Je lis…", "etat": "en_cours"})
    avant = a.ops[1]
    a.suivre({"type": "texte", "delta": "x"})  # le texte n'est pas de l'activité
    a.suivre({"type": "outil", "id": "u1", "arguments": {"chemin": "a.py"}})
    a.suivre({"type": "outil", "id": "u1", "etat": "fait", "duree": 0.2, "extrait": "def f()"})
    assert [o["label"] for o in a.ops] == ["Je regarde Conduit…", "Je lis…"]
    assert a.ops[1]["outil"] == {"id": "u1", "nom": "lire_code", "libelle": "Je lis…", "etat": "fait",
                                 "arguments": {"chemin": "a.py"}, "duree": 0.2, "extrait": "def f()"}
    assert avant["outil"]["etat"] == "en_cours"


def test_l_interruption_remet_aussi_l_activite():
    recu = {}

    async def produire(emit):
        await emit({"type": "outil", "id": "u1", "nom": "lire_code", "libelle": "Je lis…", "etat": "en_cours"})
        await emit({"type": "texte", "delta": "Bon"})
        await asyncio.sleep(30)

    async def sur_interruption(brouillon, activite):
        recu.update(brouillon=brouillon, activite=activite)

    async def scenario():
        it = _lancer(produire, sur_interruption=sur_interruption)
        tour = _tour(await it.__anext__())
        while "TEXT_MESSAGE_CONTENT" not in await it.__anext__():
            pass
        await flux.arreter(tour, None)
    asyncio.run(scenario())
    assert recu["brouillon"] == "Bon" and recu["activite"][0]["outil"]["etat"] == "en_cours"


def test_suivi_des_outils_d_un_sous_agent_marques_de_leur_parent_sans_son_texte():
    evts = []

    async def emit(e):
        evts.append(e)

    async def scenario():
        s = flux.SuiviOutils(emit, parent="conduit", ignorer={"Contribution"})
        for e in [{"current_tool_use": {"toolUseId": "u1", "name": "lire_code"}},
                  {"current_tool_use": {"toolUseId": "u1", "name": "lire_code"}},
                  {"current_tool_use": {"toolUseId": "s1", "name": "Contribution"}},
                  {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "u1", "status": "success",
                                                                           "content": [{"text": "def f()"}]}}]}}]:
            assert await s.suivre(e) is True
        assert await s.suivre({"data": "texte du sous-agent"}) is False
    asyncio.run(scenario())
    assert [(e["id"], e.get("etat")) for e in evts] == [("u1", "en_cours"), ("u1", "fait")]
    assert evts[0]["parent"] == "conduit" and evts[0]["libelle"] == flux.LIBELLES_OUTILS["lire_code"]


def test_la_fin_d_une_mission_s_attache_a_la_consultation_de_son_jumeau():
    a = flux.Activite()
    a.suivre({"type": "outil", "id": "c1", "nom": "consulter_jumeau", "libelle": "x", "etat": "en_cours"})
    a.suivre({"type": "outil", "id": "c1", "arguments": {"jumeau": "conduit", "mission": "m"}})
    a.suivre({"type": "outil", "id": "u1", "nom": "lire_code", "etat": "en_cours", "parent": "conduit"})
    a.suivre({"type": "mission", "jumeau": "conduit", "etat": "fait", "confiance": "elevee", "preuves": 3, "constat": "c"})
    assert a.ops[0]["outil"]["mission"] == {"etat": "fait", "confiance": "elevee", "preuves": 3, "constat": "c"}
    assert a.ops[1]["outil"]["parent"] == "conduit"


def test_une_mission_montre_les_outils_de_son_jumeau_puis_son_bilan(monkeypatch):
    from jumeau import mobilisation

    class Resultat:
        structured_output = mobilisation.Contribution(constat="Conduit garde tout dans une base.", preuves=["a.py#L1-L2"],
                                                      confiance="elevee")

    class SousAgent:
        async def stream_async(self, consigne, structured_output_model=None):
            yield {"current_tool_use": {"toolUseId": "u1", "name": "lire_code"}}
            yield {"data": "je réfléchis"}
            yield {"message": {"role": "user", "content": [{"toolResult": {"toolUseId": "u1", "status": "success",
                                                                           "content": [{"text": "x"}]}}]}}
            yield {"result": Resultat()}

    monkeypatch.setattr(mobilisation.agent, "construire", lambda *a, **k: SousAgent())

    async def garder(preuves, sources):
        return preuves
    monkeypatch.setattr(mobilisation, "preuves_verifiees", garder)
    evts = []

    async def emit(e):
        evts.append(e)
    mob = mobilisation.Mobilisation({"conduit": {"jumeau": {"nom": "Conduit"}, "sources": []}}, "dsn", "m", emit=emit)
    sortie = asyncio.run(mob.consulter("conduit", "Que se passe-t-il si tu tombes ?"))
    assert "Conduit garde tout" in sortie
    assert [(e["type"], e.get("etat")) for e in evts] == [("outil", "en_cours"), ("outil", "fait"), ("mission", "fait")]
    assert evts[0]["parent"] == "conduit"
    assert evts[2] == {"type": "mission", "jumeau": "conduit", "etat": "fait", "confiance": "elevee", "preuves": 1,
                       "constat": "Conduit garde tout dans une base."}
