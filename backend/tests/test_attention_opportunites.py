"""Budget d'attention de la vue « Aujourd'hui », opportunités (genre à part entière), actualités écartées, note de passation saisie."""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}
OPP = "sit-sit-mutualisation-notifications"


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


@pytest.fixture(scope="module")
def crees():
    """Les travaux créés par ces tests sont supprimés en base à la fin (l'API n'a pas de suppression)."""
    ids = []
    yield ids
    if not ids:
        return
    from pymongo import MongoClient
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
    MongoClient(env.get("MONGO_URL", "mongodb://localhost:27017"))[env.get("DB_NAME", "meridian_db")].cases.delete_many({"id": {"$in": ids}})


def _aujourdhui(api):
    return api.get(f"{BASE}/actualites", headers=H).json()


# ---- budget d'attention ----------------------------------------------------------------------------
def test_budget_aujourdhui_limite_ce_qui_est_montre(api):
    d = _aujourdhui(api)
    hs = d["histoires"]
    assert sum(1 for h in hs if h.get("attention") == "critique") <= 3
    assert sum(1 for h in hs if h.get("attention") == "pertinent") <= 5
    montres = [h["id"] for s in d["sections"] for h in s["histoires"]]
    assert all(next(h for h in hs if h["id"] == i).get("attention") for i in montres)
    reste = [h["id"] for s in d["reste"] for h in s["histoires"]]
    assert len(reste) == d["budget"]["reste"] and not set(reste) & set(montres)
    assert not any(h["genre"] == "gouvernance" and h.get("attention") for h in hs)  # le journal n'est jamais une priorité
    assert str(len(montres)) in d["briefing"]["accroche"]  # le briefing compte ce qui est montré, pas tout


def test_une_periode_n_a_pas_de_budget(api):
    d = api.get(f"{BASE}/actualites", headers=H, params={"jours": 7}).json()
    assert d["budget"] is None and d["reste"] == []


# ---- opportunités ------------------------------------------------------------------------------------
def test_opportunite_est_un_genre_avec_sa_place(api):
    d = _aujourdhui(api)
    o = next(h for h in d["histoires"] if h["id"] == OPP)
    assert o["genre"] == "opportunite" and o["section"] == "opportunites" and o["attention"]  # jamais urgente, mais toujours vue
    assert o["action_label"] == "Évaluer l'opportunité" and o["pourquoi_maintenant"]
    assert "opportunites" in [s["id"] for s in d["sections"]]


def test_ouvrir_une_opportunite_flore_presente_gain_effort_et_inaction(api, crees):
    r = api.post(f"{BASE}/actualites/histoire/{OPP}/travail", headers=H, json={"intention": "comprendre"}).json()
    crees.append(r["id"])
    c = api.get(f"{BASE}/cases/{r['id']}", headers=H).json()
    m = c["conversation"][0]
    assert c["type"] == "opportunite" and m["texte"].startswith("J'ai repéré une opportunité")
    for morceau in ("Ce qu'on peut y gagner", "Ce que cela demande", "Si rien n'est fait"):
        assert morceau in m["texte"]
    assert m["decisions"] == ["Poursuivre l'opportunité", "Reporter", "Écarter"]


def test_poursuivre_une_opportunite_propose_la_note_de_passation(api, crees):
    r = api.post(f"{BASE}/actualites/histoire/{OPP}/travail", headers=H, json={"intention": "comprendre"}).json()
    crees.append(r["id"])
    c = api.post(f"{BASE}/cases/{r['id']}/decision-attendue", headers=H, json={"texte": "Poursuivre l'opportunité"}).json()
    dernier = c["conversation"][-1]
    assert dernier["role"] == "flore" and dernier["propose_passation"] is True
    assert c["decisions"][-1]["texte"] == "Poursuivre l'opportunité"
    b = api.get(f"{BASE}/cases/{r['id']}/passation/brouillon", headers=H).json()
    assert b["decision"] == "Poursuivre l'opportunité" and b["hypotheses"] and b["inconnues"]
    assert b["gain"] and b["attendus"] == [] and b["risques"] == []  # Flore rappelle le gain annoncé mais n'invente ni indicateur ni chiffre
    revue = datetime.fromisoformat(b["revue_le"])
    assert timedelta(days=28) < revue - datetime.now(timezone.utc) < timedelta(days=31)


def test_reporter_ou_ecarter_ne_propose_pas_de_passation(api, crees):
    r = api.post(f"{BASE}/actualites/histoire/{OPP}/travail", headers=H, json={"intention": "comprendre"}).json()
    crees.append(r["id"])
    c = api.post(f"{BASE}/cases/{r['id']}/decision-attendue", headers=H, json={"texte": "Reporter"}).json()
    assert not c["conversation"][-1].get("propose_passation") and "Reportée" in c["conversation"][-1]["texte"]


# ---- écarter avec une raison -------------------------------------------------------------------------
def test_ecarter_puis_retablir(api):
    assert api.post(f"{BASE}/actualites/histoire/{OPP}/ecarter", headers=H, json={"raison": "n'importe quoi"}).status_code == 400
    try:
        assert api.post(f"{BASE}/actualites/histoire/{OPP}/ecarter", headers=H, json={"raison": "trop_tot"}).json()["raison"] == "Trop tôt"
        d = _aujourdhui(api)
        assert OPP not in [h["id"] for h in d["histoires"]]
        assert {"id": OPP, "titre": "Opportunité : mutualiser l'envoi d'alertes entre Commandes et Facturation", "raison": "Trop tôt"} in d["ecartees"]
        # l'écart est personnel
        autre = api.get(f"{BASE}/actualites", headers={"X-Persona": "support"}).json()
        assert OPP not in [e["id"] for e in autre["ecartees"]]
    finally:
        api.delete(f"{BASE}/actualites/histoire/{OPP}/ecarter", headers=H)
    d = _aujourdhui(api)
    assert OPP in [h["id"] for h in d["histoires"]] and not any(e["id"] == OPP for e in d["ecartees"])


def test_ecarter_hors_perimetre_est_refuse(api):
    assert api.post(f"{BASE}/actualites/histoire/sit-inexistante/ecarter", headers=H, json={"raison": "connu"}).status_code == 404


# ---- note de passation saisie -------------------------------------------------------------------------
def _nouveau(api, crees):
    c = api.post(f"{BASE}/cases", headers=H, json={"titre": "Essai passation (test)", "jumeaux": ["paiements"]}).json()
    crees.append(c["id"])
    return c["id"]


def test_passation_saisie_recoit_ids_et_sens(api, crees):
    cid = _nouveau(api, crees)
    r = api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json={"texte": "Basculer en asynchrone", "passation": {
        "hypotheses": ["La bascule réduit la latence.", "  "],
        "attendus": [{"indicateur": "Latence p95", "depart": "1900", "cible": 300, "unite": "ms"}, {"indicateur": "  ", "depart": 1, "cible": 2}],
        "risques": [{"texte": "Doublons", "jumeau": "paiements", "seuil": 0, "unite": "doublons"}],
        "inconnues": [{"texte": "Effet sur Support"}], "revue_le": "2026-12-01"}})
    assert r.status_code == 201
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    p = c["veille"]["passation"]
    assert c["veille"]["statut"] == "en_veille" and c["statut"] == "en_cours"
    assert p["hypotheses"] == ["La bascule réduit la latence."] and len(p["attendus"]) == 1
    assert p["attendus"][0] == {"id": "att-1", "indicateur": "Latence p95", "sens": "baisse", "depart": 1900.0, "cible": 300, "unite": "ms"}
    assert p["risques"][0]["id"] == "risque-1" and p["risques"][0]["sens"] == "hausse" and p["inconnues"][0]["id"] == "inc-1"
    assert p["revue_le"].startswith("2026-12-01") and c["conversation"][-1]["texte"].startswith("J'ai enregistré votre décision")
    # un jumeau peut observer contre cette note générée
    assert api.post(f"{BASE}/cases/{cid}/veille/observations", headers=H, json={"cible": "att-1", "jumeau": "paiements", "valeur": 1200, "unite": "ms"}).status_code in (200, 201)


def test_passation_invalide_est_refusee(api, crees):
    cid = _nouveau(api, crees)
    corps = lambda p: {"texte": "Décider", "passation": p}
    assert api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json=corps({"attendus": [{"indicateur": "x", "depart": "abc", "cible": 1}]})).status_code == 400
    assert api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json=corps({"risques": [{"texte": "x", "seuil": None}]})).status_code == 400
    assert api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json=corps({"inconnues": [{"texte": "x"}], "revue_le": "bientôt"})).status_code == 400
    assert "veille" not in api.get(f"{BASE}/cases/{cid}", headers=H).json()


def test_passation_sans_rien_a_observer_garde_la_decision_sans_veille(api, crees):
    cid = _nouveau(api, crees)
    assert api.post(f"{BASE}/cases/{cid}/decisions", headers=H, json={"texte": "Décider", "passation": {"hypotheses": ["Une hypothèse"]}}).status_code == 201
    c = api.get(f"{BASE}/cases/{cid}", headers=H).json()
    assert c["decisions"][-1]["texte"] == "Décider" and "veille" not in c
