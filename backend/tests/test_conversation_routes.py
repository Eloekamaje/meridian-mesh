"""Routes de la conversation d'un Travail : versions, branches, régénération, modification, arrêt, recherche.
Sans serveur réel, sans modèle : la base est un faux minimal, Flore un faux qui émet des événements."""
import asyncio
import copy
import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import cases_routes
import conversation as c
from jumeau import flux


class Collection:
    def __init__(self, docs=()):
        self.docs = [copy.deepcopy(d) for d in docs]

    def _ok(self, d, f):
        return all(d.get(k) == v for k, v in f.items())

    async def find_one(self, f, proj=None):
        return next((copy.deepcopy(d) for d in self.docs if self._ok(d, f)), None)

    def find(self, f, proj=None):
        lot = [copy.deepcopy(d) for d in self.docs if self._ok(d, f)]

        class Curseur:
            async def to_list(self, n):
                return lot
        return Curseur()

    async def update_one(self, f, maj):
        d = next((d for d in self.docs if self._ok(d, f)), None)
        if d is None:
            return
        for k, v in maj.get("$set", {}).items():
            *chemin, dernier = k.split(".")  # « conversation.3.retour » : chemin à points, comme Mongo
            cible = d
            for morceau in chemin:
                cible = cible[int(morceau)] if isinstance(cible, list) else cible.setdefault(morceau, {})
            if isinstance(cible, list):
                cible[int(dernier)] = copy.deepcopy(v)
            else:
                cible[dernier] = copy.deepcopy(v)
        for k, v in maj.get("$push", {}).items():
            lot = v["$each"] if isinstance(v, dict) and "$each" in v else [v]
            d.setdefault(k, []).extend(copy.deepcopy(lot))

    async def insert_one(self, d):
        self.docs.append(copy.deepcopy(d))


class Db:
    def __init__(self, cases):
        self.cases, self.jumeaux, self.retours = Collection(cases), Collection(), Collection()


def un_fil():
    return [{"role": "utilisateur", "texte": "Quel est le socle ?", "quand": "t"},
            c.message_flore({"reponse": "Le socle est Kafka.", "origine": "modele"}),
            {"role": "utilisateur", "texte": "Et la dette ?", "quand": "t"},
            c.message_flore({"reponse": "Elle est faible.", "origine": "modele"})]


CASE = {"id": "t1", "titre": "Socle Kafka", "responsable": "architecte", "jumeaux": [], "conversation": un_fil(),
        "historique": [], "maj_le": "2026-01-01"}
AUTRE = {"id": "t2", "titre": "Dette technique", "responsable": "architecte", "jumeaux": [],
         "conversation": [{"role": "utilisateur", "texte": "ÉTAT des lieux", "quand": "t"}], "historique": [],
         "maj_le": "2026-02-01"}


class Faux:
    """generer_reponse_flore remplacé : émet un brouillon puis rend une réponse ; ou bloque pour simuler un arrêt."""

    def __init__(self):
        self.appels, self.reponse, self.bloque, self.muet = [], "Nouvelle réponse.", False, False

    async def __call__(self, contexte, question, selection, domaine, persona, espace, travail=None, emit=None):
        self.appels.append({"contexte": contexte, "question": question, "selection": selection, "domaine": domaine,
                            "travail": travail})
        if self.muet:
            await asyncio.sleep(30)
        if emit:
            await emit({"type": "texte", "delta": self.reponse[:4]})
            await emit({"type": "texte", "delta": self.reponse[4:8]})
        if self.bloque:
            await asyncio.sleep(30)
        return {"reponse": self.reponse, "comportement": "repondre", "preuves": [], "contributions": [],
                "relecture_etat": "relue", "corrige": False, "origine": "modele", "durees": {}}


@pytest.fixture
def monde(monkeypatch):
    class Ecriture:
        def __init__(self, db, cid): pass
        async def retirer_precision(self): return None
    monkeypatch.setattr(cases_routes, "EcritureTravail", Ecriture)
    db, faux = Db([CASE, AUTRE]), Faux()

    async def rien(*a, **k): return None
    router = cases_routes.build_cases_router({
        "db": db, "resoudre_perimetre": lambda p, e: ({"id": p}, {"id": e or "e"}),
        "autorisations": lambda esp, ids: {i: "complet" for i in ids}, "journaler": rien, "notifier": rien,
        "generer_reponse_flore": faux, "slugify": lambda s: s, "NO_ID": {"_id": 0},
        "datetime": __import__("datetime").datetime, "timezone": __import__("datetime").timezone})
    api = APIRouter(prefix="/api")
    api.include_router(router)
    app = FastAPI()
    app.include_router(api)
    return TestClient(app), db, faux


def evenements(rep):
    return [json.loads(l[6:]) for l in rep.text.splitlines() if l.startswith("data: ")]


def conv(db, cid="t1"):
    return next(d for d in db.cases.docs if d["id"] == cid)["conversation"]


def test_nouvelle_question_enregistre_un_message_de_flore_du_contrat(monde):
    client, db, faux = monde
    ev = evenements(client.post("/api/cases/t1/messages/flux", json={"texte": "Et la sécurité ?"}))
    assert ev[-1]["type"] == "final"
    m = conv(db)[-1]
    assert m["texte"] == "Nouvelle réponse." and m["version"] == 0 and len(m["versions"]) == 1 and m["interrompu"] is False
    assert faux.appels[0]["travail"] == "t1" and faux.appels[0]["contexte"] == "case"


def test_le_panneau_peut_passer_contexte_selection_domaine(monde):
    client, _, faux = monde
    client.post("/api/cases/t1/messages/flux", json={"texte": "Q", "contexte": "global", "selection": ["a"], "domaine": "Client"})
    assert faux.appels[0] | {} == {"contexte": "global", "question": "Q", "selection": ["a"], "domaine": "Client", "travail": "t1"}


def test_regenerer_ajoute_une_version_active_et_reprend_la_question_precedente(monde):
    client, db, faux = monde
    faux.reponse = "Autre version."
    ev = evenements(client.post("/api/cases/t1/messages/3/regenerer/flux", json={}))
    assert faux.appels[0]["question"] == "Et la dette ?"
    final = ev[-1]["reponse"]
    assert final["texte"] == "Autre version." and final["version"] == 1 and len(final["versions"]) == 2
    assert conv(db)[3] == final and len(conv(db)) == 4


def test_regenerer_une_question_est_refuse(monde):
    client, _, _ = monde
    assert client.post("/api/cases/t1/messages/2/regenerer/flux", json={}).status_code == 400
    assert client.post("/api/cases/t1/messages/42/regenerer/flux", json={}).status_code == 404


def test_choisir_une_version(monde):
    client, db, faux = monde
    evenements(client.post("/api/cases/t1/messages/1/regenerer/flux", json={}))
    r = client.post("/api/cases/t1/messages/1/version", json={"index": 0})
    assert r.status_code == 200 and r.json()["texte"] == "Le socle est Kafka." and r.json()["version"] == 0
    assert conv(db)[1]["texte"] == "Le socle est Kafka."
    assert client.post("/api/cases/t1/messages/1/version", json={"index": 7}).status_code == 400
    assert client.post("/api/cases/t1/messages/0/version", json={"index": 0}).status_code == 400


def test_modifier_une_question_range_la_branche_puis_repond(monde):
    client, db, faux = monde
    ev = evenements(client.post("/api/cases/t1/messages/0/modifier/flux", json={"texte": "Quel est le socle exact ?"}))
    msgs = ev[-1]["reponse"]["messages"]
    assert [m["role"] for m in msgs] == ["utilisateur", "flore"]
    assert msgs[0]["texte"] == "Quel est le socle exact ?" and msgs[0]["branche"] == 1
    assert msgs[0]["branches"][0]["texte"] == "Quel est le socle ?" and len(msgs[0]["branches"][0]["suite"]) == 3
    assert faux.appels[0]["question"] == "Quel est le socle exact ?"
    assert conv(db) == msgs


def test_choisir_une_branche_restaure_la_suite(monde):
    client, db, _ = monde
    evenements(client.post("/api/cases/t1/messages/0/modifier/flux", json={"texte": "bis"}))
    r = client.post("/api/cases/t1/messages/0/branche", json={"index": 0})
    assert [m["texte"] for m in r.json()["messages"]][:3] == ["Quel est le socle ?", "Le socle est Kafka.", "Et la dette ?"]
    assert len(conv(db)) == 4
    assert client.post("/api/cases/t1/messages/0/branche", json={"index": 9}).status_code == 400


def test_un_autre_persona_ne_touche_pas_au_travail(monde):
    client, db, _ = monde
    h = {"X-Persona": "intrus"}
    for chemin, corps in [("messages/1/version", {"index": 0}), ("messages/0/branche", {"index": 0}),
                          ("messages/3/regenerer/flux", {}), ("messages/0/modifier/flux", {"texte": "x"})]:
        assert client.post(f"/api/cases/t1/{chemin}", json=corps, headers=h).status_code == 403, chemin
    assert len(conv(db)) == 4 and conv(db)[0]["texte"] == "Quel est le socle ?"


def test_travail_inconnu(monde):
    client, _, _ = monde
    assert client.post("/api/cases/nope/messages/1/version", json={"index": 0}).status_code == 404


# ---- recherche ----
def noms(client, q=None, **kw):
    return [x["id"] for x in client.get("/api/cases", params={"q": q} if q is not None else None, **kw).json()]


def test_recherche_dans_le_titre_et_le_texte_sans_casse(monde):
    client, _, _ = monde
    assert noms(client, "KAFKA") == ["t1"]          # titre ET texte
    assert noms(client, "dette") == ["t1", "t2"] or noms(client, "dette") == ["t2", "t1"]
    assert noms(client, "état") == ["t2"]
    assert noms(client, "zzz") == []


def test_recherche_echappee_jamais_une_regex(monde):
    client, _, _ = monde
    assert noms(client, ".*") == []
    assert noms(client, "(") == []
    assert noms(client, "[") == []


def test_sans_q_la_reponse_est_inchangee(monde):
    client, _, _ = monde
    assert sorted(noms(client)) == ["t1", "t2"] and sorted(noms(client, "")) == ["t1", "t2"]


# ---- arrêt ----
def lancer_puis_couper(monde, chemin, corps, lectures=2):
    """Vrai flux ASGI ; le client lit deux événements « texte » puis coupe. Rend la conversation ensuite."""
    client, db, faux = monde
    faux.bloque = True
    import httpx

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://t") as http:
            async with http.stream("POST", chemin, json=corps) as r:
                lus = 0
                if lectures == 0:
                    await asyncio.sleep(0.3)
                async for ligne in r.aiter_lines():
                    if ligne.startswith("data:"):
                        lus += 1
                    if lus >= lectures:
                        break
        for _ in range(20):
            await asyncio.sleep(0.05)
            await asyncio.gather(*list(flux._TACHES), return_exceptions=True)
    asyncio.run(scenario())
    return conv(db)


def test_arret_nouvelle_question_garde_question_et_reponse_partielle(monde):
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/flux", {"texte": "Et la sécurité ?"})
    assert [m["role"] for m in msgs[-2:]] == ["utilisateur", "flore"] and len(msgs) == 6
    assert msgs[-2]["texte"] == "Et la sécurité ?"
    assert msgs[-1]["texte"] == "Nouvelle réponse."[:8] and msgs[-1]["interrompu"] is True
    assert msgs[-1]["versions"][0]["interrompu"] is True


def test_arret_regeneration_ajoute_une_version_interrompue(monde):
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/3/regenerer/flux", {})
    assert len(msgs) == 4 and msgs[3]["interrompu"] is True and len(msgs[3]["versions"]) == 2
    assert msgs[3]["texte"] == "Nouvelle réponse."[:8] and msgs[3]["versions"][0]["texte"] == "Elle est faible."


def test_arret_regeneration_sans_rien_d_ecrit_n_ajoute_rien(monde):
    monde[2].muet = True
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/3/regenerer/flux", {}, lectures=0)
    assert msgs[3]["versions"] == un_fil()[3]["versions"] and len(msgs) == 4


def test_arret_modification_garde_la_branche_la_question_et_la_reponse_partielle(monde):
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/0/modifier/flux", {"texte": "Autre question ?"})
    assert [m["role"] for m in msgs] == ["utilisateur", "flore"]
    assert msgs[0]["texte"] == "Autre question ?" and len(msgs[0]["branches"]) == 2
    assert len(msgs[0]["branches"][0]["suite"]) == 3
    assert msgs[1]["interrompu"] is True and msgs[1]["texte"] == "Nouvelle réponse."[:8]
