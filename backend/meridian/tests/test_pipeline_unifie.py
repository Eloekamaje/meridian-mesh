"""Pipeline unifié `/demander` + `/analyser` (plan Cognition IA, D9).

Une machine, deux profils d'effort : `leger` court-circuite ou réduit le budget,
`standard` est le pipeline normal, `approfondi` est le « mode analyse » — la
même machine profonde que `/analyser` (spécialistes, dossier persisté), sans
code copié. Ces tests n'ouvrent ni modèle, ni Postgres, ni Mongo : les bords
sont remplacés par des factices.
"""
import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "meridian_tests")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import limites
import server  # == meridian.adapters.inbound.http.legacy (point d'entrée ASGI)
from meridian.adapters.inbound.http import cognitif
from meridian.application import (
    analyse_service, contrat_question, noyau_raisonnement, pipeline_unifie)


# ---------------------------------------------------------------------------
# Factices de bord
# ---------------------------------------------------------------------------


def _resoudre_perimetre(acteur, x_espace):
    return acteur, {"id": x_espace or "espace-demo", "jumeaux": "*"}


def _droits(espace, ids):
    return {ident: "complet" for ident in ids}


class _Db:
    def __init__(self, jumeaux=()):
        self.jumeaux = _Collection(list(jumeaux))


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, filtre, projection=None):
        lot = list(self.docs)

        class Curseur:
            async def to_list(self, n):
                return lot[:n]

        return Curseur()


class RuntimeFactice:
    """Runtime minimal du pipeline profond : ni Postgres, ni graphe, ni LLM."""

    def __init__(self):
        self.specialistes_lances = []

    def mode_auth(self):
        return "demo"

    def assainir(self, valeur):
        return valeur

    async def agreger_portefeuille(self, tenant, *, domaine=None, limite=100):
        return {"propositions": [], "limites": [], "valeur": None}

    async def lancer_specialistes(self, noms, base, tenant):
        self.specialistes_lances.append(list(noms))
        return [{
            "specialiste": nom, "statut": "ok",
            "propositions": [{
                "specialiste": nom, "type": "CONSTAT",
                "titre": f"constat {nom}", "confiance": 0.7,
            }],
            "limites": [],
        } for nom in noms]

    def proximite_graphe(self, tenant, twin_ids):
        return {}

    async def rechercher_refutation(self, tenant, **kwargs):
        return {"faits": [], "contradictions": []}

    async def recuperer_memoire(self, tenant, **kwargs):
        return []

    def enrichir_pack(self, pack, candidats, *, max_tokens=None):
        return {**dict(pack), "memoire": []}

    async def memoriser_session(self, tenant, session_id, question, resume, *,
                                acteur, donnees=None):
        return None

    async def lire_calibration(self, tenant, prediction_id):
        return None

    async def calibrer_decision(self, tenant, decision_support, **kwargs):
        return None

    def decision_support_enrichi(self, decision_support, **kwargs):
        return dict(decision_support or {})


def _monder_tour(monkeypatch, *, sonde=None):
    """Factice les bords du tour Flore : base vide, pas de modèle, sonde imposée."""
    monkeypatch.setattr(server, "resoudre_perimetre", _resoudre_perimetre)
    monkeypatch.setattr(server, "autorisations", _droits)
    monkeypatch.setattr(server, "db", _Db())
    monkeypatch.setattr(limites.partage, "actif", lambda: False)
    limites.reinitialiser()

    async def sonder(question, tenant):
        return sonde

    async def jumeaux(db, tenant, *a, **k):
        return []

    monkeypatch.setattr(server, "_sonder_tour", sonder)
    monkeypatch.setattr(server, "jumeaux_du_tenant", jumeaux)


def _client_legacy():
    app = FastAPI()
    app.include_router(server.api_router)
    return TestClient(app)


def _client_cognitif():
    app = FastAPI()
    app.include_router(cognitif.router, prefix="/api")
    return TestClient(app)


def _epargne_epilogue(monkeypatch):
    """L'épilogue et la persistance du dossier n'ouvrent aucune connexion."""
    monkeypatch.setattr(server, "_consigner_epilogue", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Profil d'effort (contrat B9)
# ---------------------------------------------------------------------------


def test_contrat_effort_borne_la_demande_et_deduit_de_la_sonde():
    sonde_incertaine = {"verdict": "incertain", "indices": [],
                        "preuves": [], "manque": ["aucune preuve"]}
    assert pipeline_unifie.contrat_effort(
        "q ?", sonde=sonde_incertaine)["effort"] == "approfondi"
    assert pipeline_unifie.contrat_effort(
        "q ?", effort="leger")["effort"] == "leger"
    # Un profil demandé hors des valeurs connues est ignoré, jamais honoré.
    assert pipeline_unifie.contrat_effort(
        "q ?", effort="extreme")["effort"] == "standard"


def test_le_budget_du_noyau_suit_l_effort_du_contrat():
    question = "Conçois une application de paiement"
    standard = noyau_raisonnement.preparer_dossier(
        question, contexte={
            "sans_questions": True,
            "contrat": {"effort": "standard", "artefacts_requis": []}})
    approfondi = noyau_raisonnement.preparer_dossier(
        question, contexte={
            "sans_questions": True,
            "contrat": {"effort": "approfondi", "artefacts_requis": []}})
    leger = noyau_raisonnement.preparer_dossier(
        question, contexte={
            "sans_questions": True,
            "contrat": {"effort": "leger", "artefacts_requis": []}})
    base = standard.plan.budget["appels_outils"]
    assert approfondi.plan.budget["appels_outils"] == base * 2
    assert leger.plan.budget["appels_outils"] == max(1, round(base * 0.5))
    assert standard.plan.budget != approfondi.plan.budget


# ---------------------------------------------------------------------------
# `/demander` — profils leger et standard
# ---------------------------------------------------------------------------


def test_demander_leger_court_circuite_sans_dossier(monkeypatch):
    """Une question triviale : réponse déterministe, aucune analyse consommée."""
    _monder_tour(monkeypatch, sonde={
        "verdict": "trivial", "indices": [{"source": "question",
                                           "identifiants": ["paiements"]}],
        "preuves": [{"jumeau_id": "paiements", "titre": "Paiements",
                     "score": 1.0}],
        "manque": []})
    _epargne_epilogue(monkeypatch)

    async def jamais(*a, **k):
        raise AssertionError("l'orchestrateur ne doit pas être appelé")

    async def pas_analyse(*a, **k):
        raise AssertionError("le mode analyse ne doit pas être appelé")

    monkeypatch.setattr(server.jumeau_orchestrateur, "executer_raisonne", jamais)
    monkeypatch.setattr(
        pipeline_unifie.analyse_service, "executer", pas_analyse)

    r = _client_legacy().post("/api/aurora/demander",
                              json={"question": "Paiements ?",
                                    "effort": "leger"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["effort"] == "leger"
    assert "analyse" not in corps and "dossier" not in corps


def test_demander_standard_reste_le_pipeline_normal(monkeypatch):
    """Même question qu'en analyse : le pipeline conversationnel, à budget nominal."""
    _monder_tour(monkeypatch, sonde={
        "verdict": "clair", "indices": [], "manque": [],
        "preuves": [{"jumeau_id": "paiements", "titre": "Paiements",
                     "score": 0.9}]})
    _epargne_epilogue(monkeypatch)
    vus = {}

    async def orchestree(*a, **k):
        vus["contexte"] = k.get("contexte")
        return {"comportement": "repondre", "reponse": "Réponse standard.",
                "preuves": [], "contributions": [],
                "jumeaux_participants": [],
                "orchestration": {"outils": [], "erreurs": []}}

    async def pas_analyse(*a, **k):
        raise AssertionError("le mode analyse ne doit pas être appelé")

    monkeypatch.setattr(
        server.jumeau_orchestrateur, "executer_raisonne", orchestree)
    monkeypatch.setattr(
        pipeline_unifie.analyse_service, "executer", pas_analyse)

    r = _client_legacy().post("/api/aurora/demander",
                              json={"question": "Que fait Paiements ?"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["effort"] == "standard"
    assert corps["reponse"] == "Réponse standard."
    assert "analyse" not in corps and "dossier" not in corps
    # Le contrat B9 a bien alimenté le contexte de raisonnement du tour.
    assert (vus["contexte"] or {}).get("contrat", {}).get("effort") == "standard"


# ---------------------------------------------------------------------------
# `/demander` approfondi == `/analyser` : même machine, sortie différente
# ---------------------------------------------------------------------------


def test_demander_approfondi_passe_par_la_machine_d_analyse(monkeypatch):
    """`/demander` à effort approfondi : même sous-pipeline que `/analyser`."""
    _monder_tour(monkeypatch)
    _epargne_epilogue(monkeypatch)
    captures = {}
    persistes = []

    async def executer(**kwargs):
        captures.update(kwargs)
        return {
            "tenant": kwargs["tenant"], "effort": "approfondi",
            "specialistes_executes": ["preuve"],
            "dossier": {"statut": "ok", "propositions": [],
                        "specialistes": [], "limites": []},
            "reponse": {
                "question": kwargs["payload"]["question"],
                "socle": {"faits": [], "preuves": [], "incertitudes": [],
                          "limites": []},
                "lecture": {"synthese": [{"titre": "Constat majeur"}]},
                "decision_support": {"recommandation": "Valider la piste."},
                "avertissements": [],
            },
            "dossier_raisonnement": {"id": "dossier-1", "statut": "reponse"},
            "evaluation": {"score": 0.8},
            "qualite": {"faits": 1},
        }

    async def persister(tenant, dossier):
        persistes.append((tenant, dossier))

    async def jamais(*a, **k):
        raise AssertionError("l'orchestrateur ne doit pas être appelé")

    monkeypatch.setattr(
        pipeline_unifie.analyse_service, "executer", executer)
    monkeypatch.setattr(
        cognitif, "_persister_dossier_raisonnement", persister)
    monkeypatch.setattr(server.jumeau_orchestrateur, "executer_raisonne", jamais)

    r = _client_legacy().post("/api/aurora/demander",
                              json={"question": "Impact de la refonte ?",
                                    "effort": "approfondi",
                                    "profondeur": 3})
    assert r.status_code == 200, r.text
    corps = r.json()
    # La sortie `demander` : réponse + traçabilité, jamais le dossier complet.
    assert corps["effort"] == "approfondi"
    assert "Constat majeur" in corps["reponse"]
    assert "Valider la piste." in corps["reponse"]
    assert corps["analyse"]["dossier_id"] == "dossier-1"
    assert "dossier_raisonnement" not in corps
    # La machine profonde a reçu l'entrée unifiée : question + effort forcé.
    assert captures["payload"]["effort"] == "approfondi"
    assert captures["payload"]["profondeur"] == 3
    assert captures["payload"]["question"] == "Impact de la refonte ?"
    # Le dossier est persisté comme sur `/analyser`.
    assert persistes and persistes[0][1]["id"] == "dossier-1"


def test_analyser_est_l_alias_approfondi_du_pipeline_unifie(monkeypatch):
    """Rétro-compat : la route `/analyser` garde sa forme, effort forcé, dossier."""
    captures = {}

    async def executer(**kwargs):
        captures.update(kwargs)
        return {
            "tenant": kwargs["tenant"], "effort": "approfondi",
            "reponse": {"socle": {"faits": [], "preuves": []}},
            "dossier": {"statut": "ok"},
            "dossier_raisonnement": {"id": "d-9"},
            "evaluation": {"score": 1.0},
        }

    async def persister(tenant, dossier):
        return None

    monkeypatch.setattr(cognitif, "_runtime_analyse", RuntimeFactice)
    monkeypatch.setattr(cognitif.analyse_service, "executer", executer)
    monkeypatch.setattr(cognitif, "_persister_dossier_raisonnement", persister)

    r = _client_cognitif().post(
        "/api/boucle/analyser",
        json={"question": "impact ?", "effort": "leger"},
        headers={"X-Tenant": "banque"})
    assert r.status_code == 200, r.text
    # L'alias force `approfondi` : un effort adverse n'est pas honoré.
    assert captures["payload"].effort == "approfondi"
    corps = r.json()
    assert corps["effort"] == "approfondi"
    assert corps["dossier"]["statut"] == "ok"
    assert corps["dossier_raisonnement"]["id"] == "d-9"


# ---------------------------------------------------------------------------
# La machine profonde honore le profil (budget ∝ effort, spécialistes)
# ---------------------------------------------------------------------------


def _charge(effort=None, **options):
    options.setdefault("twin_ids", ["app-1"])
    return pipeline_unifie.charge_analyse(
        "Impact de la refonte ?", effort=effort, **options)


def test_la_machine_profonde_porte_l_effort_effectif():
    """Le service profond rend `effort` : le tour est mesurable, jamais muet."""
    resultat = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="demo",
        payload=_charge("approfondi"), runtime=RuntimeFactice()))
    assert resultat["effort"] == "approfondi"
    budget = resultat["dossier_raisonnement"]["plan"]["budget"]
    assert budget["appels_outils"] >= 20  # base 12 × facteur approfondi
    assert resultat["specialistes_executes"]


def test_la_meme_machine_a_budget_different_selon_l_effort():
    """Même sous-pipeline : standard et approfondi partagent le code, pas le budget."""
    standard = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="demo",
        payload=_charge("standard"), runtime=RuntimeFactice()))
    approfondi = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="demo",
        payload=_charge("approfondi"), runtime=RuntimeFactice()))
    assert standard["effort"] == "standard"
    assert approfondi["effort"] == "approfondi"
    base = standard["dossier_raisonnement"]["plan"]["budget"]["appels_outils"]
    elargi = approfondi["dossier_raisonnement"]["plan"]["budget"]["appels_outils"]
    assert elargi == base * 2
    # Le dossier porte le contrat qui a piloté le budget.
    assert approfondi["dossier_raisonnement"]["contrat"]["effort"] == "approfondi"


def test_effort_leger_ne_consomme_pas_d_analyse_profonde():
    """Budget minimal : aucun spécialiste n'est lancé, le dossier le dit."""
    runtime = RuntimeFactice()
    resultat = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="demo",
        payload=_charge("leger"), runtime=runtime))
    assert resultat["effort"] == "leger"
    assert resultat["specialistes_executes"] == []
    assert runtime.specialistes_lances == []
    budget = resultat["dossier_raisonnement"]["plan"]["budget"]
    assert budget["appels_outils"] <= 6  # base 12 × facteur leger


def test_le_sans_effort_reste_le_profil_nominal_approfondi():
    """Rétro-compat stricte : un appel sans `effort` garde le comportement d'avant."""
    resultat = asyncio.run(analyse_service.executer(
        tenant="banque", acteur="demo",
        payload=_charge(), runtime=RuntimeFactice()))
    assert resultat["effort"] == "approfondi"
