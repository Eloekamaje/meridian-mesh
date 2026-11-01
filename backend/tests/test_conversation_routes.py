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
import limites
import pieces
from seed_data import ESPACES
from jumeau import flux


class Collection:
    def __init__(self, docs=()):
        self.docs = [copy.deepcopy(d) for d in docs]

    def _ok(self, d, f):
        for k, v in f.items():
            if k == "$or":
                if not any(self._ok(d, condition) for condition in v):
                    return False
            elif isinstance(v, dict) and any(operateur in v for operateur in ("$exists", "$lte", "$in", "$ne")):
                if "$exists" in v and (k in d) != v["$exists"]:
                    return False
                if "$lte" in v and (d.get(k) is None or d.get(k) > v["$lte"]):
                    return False
                if "$in" in v and d.get(k) not in v["$in"]:
                    return False
                if "$ne" in v and (d.get(k) == v["$ne"]
                                   or (isinstance(d.get(k), list) and v["$ne"] in d.get(k))):
                    return False
            elif d.get(k) != v:
                return False
        return True

    async def find_one(self, f, proj=None):
        return next((copy.deepcopy(d) for d in self.docs if self._ok(d, f)), None)

    def find(self, f, proj=None):
        lot = [copy.deepcopy(d) for d in self.docs if self._ok(d, f)]

        class Curseur:
            def sort(self, cle, sens=1):
                lot.sort(key=lambda d: d.get(cle) or 0, reverse=sens < 0)
                return self

            async def to_list(self, n):
                return lot[:n]

            def __aiter__(self):
                self._iter = iter(lot)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration
        return Curseur()

    def _appliquer(self, d, maj):
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
        for k, v in maj.get("$addToSet", {}).items():
            if v not in d.setdefault(k, []):
                d[k].append(copy.deepcopy(v))
        for k in maj.get("$unset", {}):
            d.pop(k, None)
        for k, v in maj.get("$inc", {}).items():
            d[k] = (d.get(k) or 0) + v

    async def update_one(self, f, maj):
        class Resultat:
            matched_count = 0
            modified_count = 0
        resultat = Resultat()
        d = next((d for d in self.docs if self._ok(d, f)), None)
        if d is None:
            return resultat
        resultat.matched_count = resultat.modified_count = 1
        self._appliquer(d, maj)
        return resultat

    async def find_one_and_update(self, f, maj):
        d = next((d for d in self.docs if self._ok(d, f)), None)
        if d is None:
            return None
        avant = copy.deepcopy(d)
        self._appliquer(d, maj)
        return avant

    async def insert_one(self, d):
        self.docs.append(copy.deepcopy(d))

    async def delete_one(self, f):
        self.docs = [d for d in self.docs if not self._ok(d, f)]

    async def delete_many(self, f):
        self.docs = [d for d in self.docs if not self._ok(d, f)]

    async def count_documents(self, f):
        return sum(1 for d in self.docs if self._ok(d, f))


class Db:
    def __init__(self, cases, jumeaux=()):
        self.cases, self.jumeaux, self.retours = Collection(cases), Collection(jumeaux), Collection()
        self.notifications = Collection()
        self.pieces = Collection()  # pièces jointes du Travail (P4)
        self.relations, self.situations = Collection(), Collection()


def un_fil():
    return [{"role": "utilisateur", "texte": "Quel est le socle ?", "quand": "t"},
            c.message_flore({"reponse": "Le socle est Kafka.", "origine": "modele"}),
            {"role": "utilisateur", "texte": "Et la dette ?", "quand": "t"},
            c.message_flore({"reponse": "Elle est faible.", "origine": "modele"})]


CASE = {"id": "t1", "titre": "Socle Kafka", "responsable": "demo", "portee": "personnel", "jumeaux": [], "conversation": un_fil(),
        "historique": [], "maj_le": "2026-01-01"}
AUTRE = {"id": "t2", "titre": "Dette technique", "responsable": "demo", "jumeaux": [],
         "conversation": [{"role": "utilisateur", "texte": "ÉTAT des lieux", "quand": "t"}], "historique": [],
         "maj_le": "2026-02-01"}


def resoudre_perimetre(acteur, espace_id):
    """Même règle que server.resoudre_perimetre : l'espace demandé, sinon le Mesh global."""
    espace = next((e for e in ESPACES if e["id"] == espace_id), None) or next(e for e in ESPACES if e.get("global"))
    return acteur, espace


class Faux:
    """generer_reponse_flore remplacé : émet un brouillon puis rend une réponse ; ou bloque pour simuler un arrêt."""

    def __init__(self):
        self.appels, self.reponse, self.bloque, self.muet = [], "Nouvelle réponse.", False, False
        self.participants = []

    async def __call__(self, contexte, question, selection, domaine, acteur, espace, travail=None, emit=None,
                       autoriser_ecriture=False):
        self.appels.append({"contexte": contexte, "question": question, "selection": selection, "domaine": domaine,
                            "travail": travail, "autoriser_ecriture": autoriser_ecriture})
        if self.muet:
            await asyncio.sleep(30)
        if emit:
            await emit({"type": "outil", "id": "u1", "nom": "lire_code", "libelle": "Je lis le code concerné…", "etat": "en_cours"})
            await emit({"type": "outil", "id": "u1", "etat": "fait", "duree": 0.1, "extrait": "def f()"})
            await emit({"type": "texte", "delta": self.reponse[:4]})
            await emit({"type": "texte", "delta": self.reponse[4:8]})
        if self.bloque:
            await asyncio.sleep(30)
        return {"reponse": self.reponse, "comportement": "repondre", "preuves": [], "contributions": [],
                "jumeaux_participants": self.participants,
                "relecture_etat": "relue", "corrige": False, "origine": "modele", "durees": {}}


def droits(espace, ids):
    """Les droits d'un espace, comme server.autorisations : « * » = tout complet, sinon par jumeau (ou « * »),
    et un jumeau sans règle est absent (jamais autorisé)."""
    regles = espace["jumeaux"]
    if regles == "*":
        return {i: "complet" for i in ids}
    niveaux = {i: regles.get(i, regles.get("*")) for i in ids}
    return {i: n for i, n in niveaux.items() if n is not None}


@pytest.fixture
def monde(monkeypatch):
    class Ecriture:
        def __init__(self, db, cid): pass
        async def retirer_precision(self): return None
    monkeypatch.setattr(cases_routes, "EcritureTravail", Ecriture)
    db, faux = Db([CASE, AUTRE]), Faux()

    async def rien(*a, **k): return None

    async def noter(type_, texte, lien):
        await db.notifications.insert_one({"type": type_, "texte": texte, "lien": lien})
    router = cases_routes.build_cases_router({
        "db": db, "resoudre_perimetre": resoudre_perimetre,
        "autorisations": droits, "journaler": rien, "notifier": noter,
        "generer_reponse_flore": faux, "slugify": lambda s: s, "NO_ID": {"_id": 0},
        "datetime": __import__("datetime").datetime, "timezone": __import__("datetime").timezone})
    api = APIRouter(prefix="/api")
    api.include_router(router)
    app = FastAPI()
    app.include_router(api)
    return TestClient(app), db, faux


def evenements(rep):
    return [json.loads(ligne[6:]) for ligne in rep.text.splitlines() if ligne.startswith("data: ")]


def conv(db, cid="t1"):
    return next(d for d in db.cases.docs if d["id"] == cid)["conversation"]


def test_nouvelle_question_enregistre_un_message_de_flore_du_contrat(monde):
    client, db, faux = monde
    ev = evenements(client.post("/api/cases/t1/messages/flux", json={"texte": "Et la sécurité ?"}))
    assert ev[0]["type"] == "RUN_STARTED" and ev[0]["threadId"] == "t1" and ev[-1]["type"] == "RUN_FINISHED"
    m = conv(db)[-1]
    assert m["texte"] == "Nouvelle réponse." and m["version"] == 0 and len(m["versions"]) == 1 and m["interrompu"] is False
    assert faux.appels[0]["travail"] == "t1" and faux.appels[0]["contexte"] == "case"


def test_le_panneau_peut_passer_contexte_selection_domaine(monde):
    client, _, faux = monde
    client.post("/api/cases/t1/messages/flux", json={"texte": "Q", "contexte": "global", "selection": ["a"], "domaine": "Client"})
    assert faux.appels[0] | {} == {"contexte": "global", "question": "Q", "selection": ["a"], "domaine": "Client",
                                   "travail": "t1", "autoriser_ecriture": False}


def test_le_jumeau_consulte_arrive_avec_ses_sources_dans_le_fil(monde):
    client, db, faux = monde
    db.jumeaux.docs = [{"id": "tbt", "nom": "TBT", "domaine": "Support", "mission": "Missions TBT",
                        "sources_detail": [{"cle": "git-tbt", "nom": "Dépôt TBT", "statut": "prete"}]}]
    faux.participants = [{"id": "tbt", "app_id": "tbt", "nom": "TBT", "domaine": "Support", "participe": True}]
    client.post("/api/cases/t1/messages/flux", json={"texte": "Que fait TBT ?"})
    case = client.get("/api/cases/t1").json()
    dernier = [m for m in case["conversation"] if m["role"] == "flore"][-1]
    participant = next(p for p in dernier["jumeaux_participants"] if p["app_id"] == "tbt")
    assert participant["sources_detail"] == [{"cle": "git-tbt", "nom": "Dépôt TBT", "statut": "prete"}]


def test_seuls_les_livrables_du_tour_sont_nouveaux():
    ancien = [{"id": "liv-1", "titre": "Ancien"}]
    apres = [*ancien, {"id": "liv-2", "titre": "Nouveau"}]
    assert cases_routes._nouveaux_livrables(ancien, apres) == [{"id": "liv-2", "titre": "Nouveau"}]
    assert cases_routes._nouveaux_livrables(ancien, ancien) == []


def test_les_mentions_ajoutent_au_selection(monde):
    client, _, faux = monde
    client.post("/api/cases/t1/messages/flux", json={"texte": "@TBT que fais-tu ?", "mentions": ["tbt", "tbt", ""]})
    assert faux.appels[-1]["selection"] == ["tbt"]


def test_le_message_transmet_l_autorisation_d_ecriture(monde):
    client, _, faux = monde
    client.post("/api/cases/t1/messages/flux", json={"texte": "Q", "autoriser_ecriture": True})
    assert faux.appels[-1]["autoriser_ecriture"] is True
    client.post("/api/cases/t1/messages", json={"texte": "Q", "autoriser_ecriture": True})
    assert faux.appels[-1]["autoriser_ecriture"] is True


def test_le_drapeau_n_est_passe_qu_aux_generateurs_qui_l_acceptent():
    async def avec(question, autoriser_ecriture=False): pass
    async def sans(question): pass
    async def generique(*args, **kwargs): pass
    assert cases_routes._accepte_autorisation_ecriture(avec)
    assert not cases_routes._accepte_autorisation_ecriture(sans)
    assert cases_routes._accepte_autorisation_ecriture(generique)


def test_les_regenerations_n_autorisent_pas_l_ecriture_par_defaut(monde):
    client, _, faux = monde
    evenements(client.post("/api/cases/t1/messages/3/regenerer/flux", json={}))
    assert faux.appels[-1]["autoriser_ecriture"] is False
    evenements(client.post("/api/cases/t1/messages/3/regenerer/flux", json={"autoriser_ecriture": True}))
    assert faux.appels[-1]["autoriser_ecriture"] is True


def test_regenerer_ajoute_une_version_active_et_reprend_la_question_precedente(monde):
    client, db, faux = monde
    faux.reponse = "Autre version."
    ev = evenements(client.post("/api/cases/t1/messages/3/regenerer/flux", json={}))
    assert faux.appels[0]["question"] == "Et la dette ?"
    final = ev[-1]["result"]
    assert final["texte"] == "Autre version." and final["version"] == 1 and len(final["versions"]) == 2
    # `durees.premier_texte` est une mesure du flux, ajoutée par en_flux à la seule copie envoyée au client
    assert {**conv(db)[3], "durees": {}} == {**final, "durees": {}} and len(conv(db)) == 4
    assert "premier_texte" not in conv(db)[3]["durees"] and "premier_texte" in final["durees"]


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
    msgs = ev[-1]["result"]["messages"]
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


def test_travail_inconnu(monde):
    client, _, _ = monde
    assert client.post("/api/cases/nope/messages/1/version", json={"index": 0}).status_code == 404


# ---- recherche ----
def noms(client, q=None, inclure=False, **kw):
    params = {**({"q": q} if q is not None else {}), **({"inclure_conversations": 1} if inclure else {})}
    return [x["id"] for x in client.get("/api/cases", params=params or None, **kw).json()]


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
def lancer_puis_couper(monde, chemin, corps, lectures=2, arreter=True):
    """Appel ASGI direct (le client de test met la réponse en tampon, il ne sait pas couper) : après `lectures`
    événements reçus, le client demande l'arrêt du tour (comme le bouton « Arrêter ») puis se déconnecte. Avec
    `arreter=False`, il se déconnecte seulement (coupure de réseau) : le tour doit se terminer quand même."""
    client, db, faux = monde
    faux.bloque = not faux.muet and arreter
    octets = json.dumps(corps).encode()

    async def scenario():
        parti, recus, corps_envoye = asyncio.Event(), [], False

        async def receive():
            nonlocal corps_envoye
            if not corps_envoye:
                corps_envoye = True
                return {"type": "http.request", "body": octets, "more_body": False}
            await parti.wait()
            return {"type": "http.disconnect"}

        async def couper():
            if arreter:
                debut = json.loads(recus[0].decode().split("data: ", 1)[1].split("\n", 1)[0])
                assert debut["type"] == "RUN_STARTED"
                await flux.arreter(debut["runId"], "demo")
            parti.set()

        async def send(message):
            if message["type"] == "http.response.body" and b"data:" in message.get("body", b""):
                recus.append(message["body"])
                if len(recus) == max(lectures, 1):
                    if arreter:
                        asyncio.get_running_loop().call_later(
                            0.3 if lectures == 0 else 0, lambda: asyncio.ensure_future(couper()))
                    else:
                        parti.set()  # coupure réelle : le serveur doit la voir avant la fin du tour
                        await asyncio.sleep(0)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "path": chemin,
                 "raw_path": chemin.encode(), "query_string": b"", "root_path": "", "scheme": "http",
                 "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(octets)).encode())],
                 "client": ("t", 1), "server": ("t", 80)}
        await asyncio.wait_for(client.app(scope, receive, send), 10)
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
    avant = conv(monde[1])
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/3/regenerer/flux", {}, lectures=0)
    assert msgs == avant


def test_arret_modification_garde_la_branche_la_question_et_la_reponse_partielle(monde):
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/0/modifier/flux", {"texte": "Autre question ?"})
    assert [m["role"] for m in msgs] == ["utilisateur", "flore"]
    assert msgs[0]["texte"] == "Autre question ?" and len(msgs[0]["branches"]) == 2
    assert len(msgs[0]["branches"][0]["suite"]) == 3
    assert msgs[1]["interrompu"] is True and msgs[1]["texte"] == "Nouvelle réponse."[:8]


# ---- une conversation est un Travail privé à l'état « conversation » ----
@pytest.fixture
def avec_conversation(monde):
    client, db, faux = monde
    r = client.post("/api/cases", json={"titre": "Ma question", "portee": "entreprise"}.copy() | {"statut": "conversation"})
    assert r.status_code == 201, r.text
    return client, db, faux, r.json()["id"]


def test_creer_une_conversation_enregistre_statut_et_auteur(avec_conversation):
    _, db, _, cid = avec_conversation
    doc = next(d for d in db.cases.docs if d["id"] == cid)
    assert doc["statut"] == "conversation" and doc["auteur"] == "demo"


def test_creer_refuse_un_autre_statut(monde):
    assert monde[0].post("/api/cases", json={"titre": "x", "statut": "clos"}).status_code == 400


def test_un_travail_ordinaire_n_a_pas_de_statut_conversation(monde):
    client, db, _ = monde
    cid = client.post("/api/cases", json={"titre": "Ordinaire"}).json()["id"]
    assert next(d for d in db.cases.docs if d["id"] == cid)["statut"] == "ouvert"


def test_la_liste_par_defaut_exclut_les_conversations_et_le_parametre_les_inclut(avec_conversation):
    client, _, _, cid = avec_conversation
    assert cid not in noms(client)
    assert cid in noms(client, inclure=True)
    assert cid in noms(client, "ma question", inclure=True) and cid not in noms(client, "ma question")


def test_on_ne_transforme_pas_un_travail_en_conversation(monde):
    assert monde[0].patch("/api/cases/t1", json={"statut": "conversation"}).status_code == 400


def test_un_travail_conserve_ne_se_supprime_pas_par_cette_route(monde):
    client, db, _ = monde
    cid = client.post("/api/cases", json={"titre": "Ordinaire"}).json()["id"]
    assert client.delete(f"/api/cases/{cid}").status_code == 400
    assert cid in [d["id"] for d in db.cases.docs]


def test_l_activite_est_enregistree_avec_la_reponse_et_avec_un_tour_arrete(monde):
    client, db, faux = monde
    evenements(client.post("/api/cases/t1/messages/flux", json={"texte": "Et la sécurité ?"}))
    outil = conv(db)[-1]["activite"][0]["outil"]
    assert outil["nom"] == "lire_code" and outil["etat"] == "fait"
    faux.bloque = True
    lancer_puis_couper(monde, "/api/cases/t1/messages/flux", {"texte": "Autre ?"})
    assert conv(db)[-1]["interrompu"] is True and conv(db)[-1]["activite"][0]["outil"]["nom"] == "lire_code"


def test_une_coupure_sans_arret_laisse_la_reponse_se_terminer_et_l_enregistre(monde):
    msgs = lancer_puis_couper(monde, "/api/cases/t1/messages/flux", {"texte": "Et la sécurité ?"}, arreter=False)
    assert msgs[-1]["texte"] == "Nouvelle réponse." and msgs[-1]["interrompu"] is False


def test_reprendre_un_tour_depuis_une_position_puis_seul_l_auteur(monde):
    client, db, faux = monde
    ev = evenements(client.post("/api/cases/t1/messages/flux", json={"texte": "Et la sécurité ?"}))
    run = ev[0]["runId"]
    suite = evenements(client.get(f"/api/tours/{run}/flux", params={"depuis": 3}))
    assert suite == ev[3:] and suite[-1]["type"] == "RUN_FINISHED"
    assert client.get("/api/tours/inconnu/flux").status_code == 404


# ---- approbation en ligne : une connaissance proposée par Flore, tranchée dans la conversation ----
@pytest.fixture
def avec_proposition(monde, monkeypatch):
    client, db, faux = monde
    revues = []

    def reviser(claim, jumeau, acteur, decision, motif):
        if any(r[0] == claim for r in revues):
            raise ValueError("Connaissance déjà revue")
        revues.append((claim, jumeau, acteur, decision, motif))
    monkeypatch.setattr(cases_routes, "reviser_proposee", reviser)
    doc = next(d for d in db.cases.docs if d["id"] == "t1")
    doc["conversation"][3] = c.message_flore({"reponse": "Elle est faible.", "a_approuver": [
        {"claim": 7, "jumeau": "conduit", "nom": "Conduit", "predicat": "AUTORISE", "objet": "publier"}]})
    return client, db, revues


def test_approuver_execute_la_revue_une_fois_et_l_inscrit_dans_le_message(avec_proposition):
    client, db, revues = avec_proposition
    r = client.post("/api/cases/t1/messages/3/approbation", json={"claim": 7, "decision": "ACCEPTED"})
    assert r.status_code == 200, r.text
    assert r.json()["a_approuver"][0]["decision"]["valeur"] == "ACCEPTED"
    assert conv(db)[3]["a_approuver"][0]["decision"]["par"] == "demo"
    assert revues == [(7, "conduit", "demo", "ACCEPTED", None)]
    assert client.post("/api/cases/t1/messages/3/approbation", json={"claim": 7, "decision": "CONTESTED"}).status_code == 409
    assert len(revues) == 1


def test_approbation_sans_permission_valider_refusee_sans_rien_executer(avec_proposition):
    client, db, revues = avec_proposition
    r = client.post("/api/cases/t1/messages/3/approbation", json={"claim": 7, "decision": "ACCEPTED"},
                    headers={"X-Espace": "espace-architecture"})  # « relations » seulement sur Conduit
    assert r.status_code == 403 and revues == [] and "decision" not in conv(db)[3]["a_approuver"][0]


def test_approbation_d_une_proposition_absente_ou_deja_revue_ailleurs(avec_proposition, monkeypatch):
    client, db, revues = avec_proposition
    assert client.post("/api/cases/t1/messages/3/approbation", json={"claim": 8, "decision": "ACCEPTED"}).status_code == 404
    assert client.post("/api/cases/t1/messages/0/approbation", json={"claim": 7, "decision": "ACCEPTED"}).status_code == 404

    def deja(*a):
        raise ValueError("Connaissance déjà revue")
    monkeypatch.setattr(cases_routes, "reviser_proposee", deja)  # tranchée sur la page Revue entre-temps
    r = client.post("/api/cases/t1/messages/3/approbation", json={"claim": 7, "decision": "ACCEPTED"})
    assert r.status_code == 409 and "déjà revue" in r.text and "decision" not in conv(db)[3]["a_approuver"][0]


def test_une_reponse_finie_apres_le_depart_de_l_interlocuteur_le_previent(monde):
    client, db, faux = monde
    lancer_puis_couper(monde, "/api/cases/t1/messages/flux", {"texte": "Et la sécurité ?"}, arreter=False)
    assert conv(db)[-1]["texte"] == "Nouvelle réponse."
    assert [(n["type"], n["lien"]) for n in db.notifications.docs] == [("investigation_terminee", "/travaux/t1")]


# ---- autorisations des routes voisines (P4) ----
def test_le_remplacement_arbitraire_d_un_case_n_existe_plus(monde):
    client, db, _ = monde
    avant = next(d["titre"] for d in db.cases.docs if d["id"] == "t1")
    assert client.put("/api/cases/t1", json={"titre": "pirate"}).status_code == 405
    assert next(d["titre"] for d in db.cases.docs if d["id"] == "t1") == avant


# ---- intégrité de la conversation : un lecteur ne modifie pas, PATCH ne touche pas au fil ----
def test_patch_ne_touche_pas_a_la_conversation(monde):
    client, db, _ = monde
    avant = conv(db)
    r = client.patch("/api/cases/t1", json={"conversation": [{"role": "utilisateur", "texte": "pirate"}]})
    assert r.status_code == 400
    assert r.json()["detail"] == "La conversation s'ajoute par /messages ou /fusion"
    assert conv(db) == avant


def _source(client, messages):
    return client.post("/api/cases", json={"titre": "Source", "statut": "conversation", "conversation": messages}).json()["id"]


def test_fusion_d_une_conversation_par_le_responsable(monde):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    messages = [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}]
    source = _source(client, messages)
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 200, r.text
    assert [m["texte"] for m in r.json()["conversation"]] == ["Bonjour"]
    assert source not in [d["id"] for d in db.cases.docs]
    doc = next(d for d in db.cases.docs if d["id"] == cible)
    assert [m["texte"] for m in doc["conversation"]] == ["Bonjour"]
    assert any("fusionnée" in entree["texte"].lower() for entree in doc["historique"])


def test_une_double_fusion_ne_duplique_pas_les_messages(monde):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    source = _source(client, [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}])
    assert client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source}).status_code == 200
    seconde = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert seconde.status_code == 200, seconde.text
    assert [m["texte"] for m in seconde.json()["conversation"]] == ["Bonjour"]
    assert [m["texte"] for m in next(d for d in db.cases.docs if d["id"] == cible)["conversation"]] == ["Bonjour"]


def test_la_fusion_deplace_les_pieces_avant_les_messages(monde, monkeypatch):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    source = _source(client, [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}])
    db.pieces.docs.append({"id": "p1", "case_id": source})
    etapes = []

    async def deplacer(db_, source_cid, cible_cid):
        etapes.append("pieces")
        for doc in db_.pieces.docs:
            if doc["case_id"] == source_cid:
                doc["case_id"] = cible_cid
        return 1

    monkeypatch.setattr(cases_routes.pieces, "deplacer_pieces", deplacer)
    update_one = db.cases.update_one

    async def tracer(filtre, maj):
        if filtre.get("id") == cible and "conversation" in maj.get("$push", {}):
            etapes.append("messages")
        return await update_one(filtre, maj)

    monkeypatch.setattr(db.cases, "update_one", tracer)
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 200, r.text
    assert etapes == ["pieces", "messages"]
    assert [p["case_id"] for p in db.pieces.docs] == [cible]


def test_fusion_cible_pleine_refusee_sans_ajouter_de_messages(monde):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Pleine"}).json()["id"]
    next(d for d in db.cases.docs if d["id"] == cible)["pieces_count"] = pieces.MAX_PAR_CASE
    source = _source(client, [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}])
    db.pieces.docs.append({"id": "p1", "case_id": source})
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 400 and "quota" in r.json()["detail"]
    assert next(d for d in db.cases.docs if d["id"] == cible)["conversation"] == []
    source_doc = next(d for d in db.cases.docs if d["id"] == source)
    assert "fusion_vers" not in source_doc and "fusion_id" not in source_doc and "fusion_etat" not in source_doc
    assert [p["case_id"] for p in db.pieces.docs] == [source]


def test_fusion_d_une_source_deja_reservee_est_refusee_409(monde):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    source = _source(client, [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}])
    next(d for d in db.cases.docs if d["id"] == source)["fusion_vers"] = "autre-cible"
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 409 and "déjà fusionnée" in r.json()["detail"]
    assert next(d for d in db.cases.docs if d["id"] == cible)["conversation"] == []


def test_un_import_forge_ne_transporte_pas_les_champs_de_confiance(monde):
    client, db, _ = monde
    forge = [
        {"role": "utilisateur", "texte": "Q", "preuves": [{"id": "fausse"}], "decisions": [{"texte": "x"}]},
        {"role": "flore", "texte": "R", "preuves": [{"id": "fausse"}], "a_approuver": [{"claim": 1}],
         "versions": [{"texte": "R"}], "version_active": 3, "documentCanvas": "x", "kpis": {"gain": "1"}},
        {"role": "systeme", "texte": "ignoré"},
        {"role": "utilisateur", "texte": "x" * 20_001},
        "pas un message",
    ]
    cid = client.post("/api/cases", json={"titre": "Import", "conversation": forge}).json()["id"]
    messages = next(d for d in db.cases.docs if d["id"] == cid)["conversation"]
    assert [m["role"] for m in messages] == ["utilisateur", "flore"]
    assert messages[0]["texte"] == "Q" and "preuves" not in messages[0] and "decisions" not in messages[0]
    for champ in ("preuves", "a_approuver", "versions", "version_active", "documentCanvas", "kpis"):
        assert champ not in messages[1]
    assert messages[1]["importe"] is True


def test_la_fusion_normalise_aussi_les_messages_importes(monde):
    client, db, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    source = _source(client, [])
    next(d for d in db.cases.docs if d["id"] == source)["conversation"] = [
        {"role": "flore", "texte": "R", "preuves": [{"id": "fausse"}], "a_approuver": [{"claim": 1}],
         "retour": {"valeur": "utile"}},
    ]
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 200, r.text
    message = r.json()["conversation"][0]
    assert message["importe"] is True and "preuves" not in message and "a_approuver" not in message
    assert "retour" not in message


def test_le_demarrage_reconcilie_les_reservations_de_quota_orphelines(monde):
    client, db, _ = monde
    next(d for d in db.cases.docs if d["id"] == "t1")["pieces_count"] = 3
    handler = next(f for f in client.app.router.on_startup if f.__name__ == "reconcilier_les_compteurs")
    asyncio.run(handler())
    assert next(d for d in db.cases.docs if d["id"] == "t1")["pieces_count"] == 0  # aucune pièce réelle


def test_une_source_qui_n_est_pas_une_conversation_est_refusee(monde):
    client, _, _ = monde
    cible = client.post("/api/cases", json={"titre": "Cible"}).json()["id"]
    source = client.post("/api/cases", json={"titre": "Travail"}).json()["id"]
    r = client.post(f"/api/cases/{cible}/fusion", json={"source_cid": source})
    assert r.status_code == 400 and "conversation" in r.json()["detail"]


# ---- jumeaux hors périmètre : jamais dans la vue d'un travail ----
def test_les_jumeaux_hors_perimetre_ne_sortent_pas_du_travail(monde):
    client, db, _ = monde
    db.jumeaux.docs = [{"id": "paiements", "nom": "Paiements", "domaine": "Paiements"},
                       {"id": "fraude", "nom": "Fraude", "domaine": "Risque"}]
    h = {"X-Espace": "espace-support"}
    cid = client.post("/api/cases", json={"titre": "Périmètre", "portee": "entreprise",
                                          "jumeaux": ["paiements", "fraude"]}, headers=h).json()["id"]
    vue = client.get(f"/api/cases/{cid}", headers=h).json()
    assert vue["jumeaux"] == ["paiements"]
    assert [p["app_id"] for p in vue["jumeaux_participants"]] == ["paiements"]
    item = next(c for c in client.get("/api/cases", headers=h).json() if c["id"] == cid)
    assert item["jumeaux"] == ["paiements"]

    patche = client.patch(f"/api/cases/{cid}", json={"objectif": "Filtré"}, headers=h)
    assert patche.status_code == 200 and patche.json()["jumeaux"] == ["paiements"]

    source = client.post("/api/cases", json={"titre": "Source", "statut": "conversation", "conversation": [{"role": "utilisateur", "texte": "Bonjour", "quand": "t"}]}, headers=h).json()["id"]
    fusion = client.post(f"/api/cases/{cid}/fusion", json={"source_cid": source}, headers=h)
    assert fusion.status_code == 200 and fusion.json()["jumeaux"] == ["paiements"]


# ---- limites et situations : les routes globales (server.py) ----
@pytest.fixture
def serveur():
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "meridian_tests")
    import server
    return server


def _client_serveur(serveur):
    app = FastAPI()
    app.include_router(serveur.api_router)
    return TestClient(app)


def test_aurora_demander_est_limite_429(serveur, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("TOURS_RATE_MAX", "1")
    monkeypatch.setenv("TOURS_RATE_FENETRE", "60")
    monkeypatch.setattr(limites.partage, "actif", lambda: False)
    limites.reinitialiser()
    monkeypatch.setattr(serveur, "resoudre_perimetre", resoudre_perimetre)
    monkeypatch.setattr(serveur, "autorisations", droits)
    monkeypatch.setattr(serveur, "db", Db([]))
    client = _client_serveur(serveur)
    assert client.post("/api/aurora/demander", json={"question": ""}).status_code == 200
    r = client.post("/api/aurora/demander", json={"question": ""})
    assert r.status_code == 429 and "Trop de tours Flore" in r.json()["detail"]


def test_une_situation_hors_perimetre_est_refusee(serveur, monkeypatch):
    db = Db([])
    db.jumeaux.docs = [{"id": "fraude"}]
    db.situations.docs = [{"id": "sit-fraude", "jumeaux": ["fraude"], "statut": "active"}]
    monkeypatch.setattr(serveur, "resoudre_perimetre", resoudre_perimetre)
    monkeypatch.setattr(serveur, "autorisations", droits)
    monkeypatch.setattr(serveur, "db", db)

    async def rien(*a, **k):
        return None
    monkeypatch.setattr(serveur, "journaler", rien)
    client = _client_serveur(serveur)
    h = {"X-Espace": "espace-support"}
    assert client.post("/api/situations/sit-fraude/action", json={"action": "surveiller"}, headers=h).status_code == 403
    assert client.post("/api/situations/sit-fraude/decision", json={"decision": "x"}, headers=h).status_code == 403
    assert db.situations.docs[0]["statut"] == "active"


def test_une_situation_autorisee_journalise_dans_l_espace(serveur, monkeypatch):
    db = Db([])
    db.jumeaux.docs = [{"id": "support"}]
    db.situations.docs = [{"id": "sit-support", "jumeaux": ["support"], "statut": "active"}]
    captures = []

    async def noter(acteur, espace, action, cible, detail=""):
        captures.append((acteur, espace, action, cible))
    monkeypatch.setattr(serveur, "resoudre_perimetre", resoudre_perimetre)
    monkeypatch.setattr(serveur, "autorisations", droits)
    monkeypatch.setattr(serveur, "db", db)
    monkeypatch.setattr(serveur, "journaler", noter)
    client = _client_serveur(serveur)
    r = client.post("/api/situations/sit-support/decision", json={"decision": "x"},
                    headers={"X-Espace": "espace-support"})
    assert r.status_code == 200
    assert captures == [("demo", "espace-support", "décision", "sit-support")]
