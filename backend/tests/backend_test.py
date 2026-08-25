"""End-to-end backend API tests for Méridian."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
# Fallback to reading frontend/.env if not set at test run time
if "REACT_APP_BACKEND_URL" not in os.environ:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/") + "/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- santé ----------
def test_health(s):
    r = s.get(f"{BASE}/health", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- mesh ----------
def test_mesh(s):
    r = s.get(f"{BASE}/mesh", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert len(data["jumeaux"]) >= 12
    assert len(data["relations"]) >= 13
    assert len(data["regions"]) == 6


# ---------- situations ----------
def test_situations_tri(s):
    r = s.get(f"{BASE}/situations", timeout=15)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) >= 7  # peut être <7 si un test précédent a agi (statut change mais pas suppression)
    scores = [d["score"] for d in docs]
    assert scores == sorted(scores, reverse=True)
    top = docs[0]
    assert top["id"] == "sit-latence-paiements"
    assert top["score"] == 94


def test_situation_action_surveiller(s):
    # utilise une situation moins prioritaire pour éviter d'écraser sit-latence-paiements
    sid = "sit-connaissance-support"
    r = s.post(f"{BASE}/situations/{sid}/action", json={"action": "surveiller"})
    assert r.status_code == 200
    assert r.json()["statut"] == "surveillée"
    # persistance
    r2 = s.get(f"{BASE}/situations/{sid}")
    assert r2.json()["statut"] == "surveillée"


def test_situation_decision_persistee(s):
    sid = "sit-latence-paiements"
    r = s.post(f"{BASE}/situations/{sid}/decision", json={"decision": "Basculer R-118 en mode asynchrone"})
    assert r.status_code == 200
    r2 = s.get(f"{BASE}/situations/{sid}")
    j = r2.json()
    assert j["statut"] == "décidée"
    assert "R-118" in j["decision"]


def test_situation_action_invalide(s):
    r = s.post(f"{BASE}/situations/sit-latence-paiements/action", json={"action": "bidon"})
    assert r.status_code == 400


# ---------- change lab ----------
def test_change_lab_get(s):
    r = s.get(f"{BASE}/change-lab", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "changement" in d
    assert len(d.get("scenarios", [])) == 3


def test_change_lab_simuler(s):
    r = s.post(f"{BASE}/change-lab/simuler", json={"description": "Test simulation"})
    assert r.status_code == 200
    assert r.json()["changement"] == "Test simulation"


def test_change_lab_dossier(s):
    r = s.post(f"{BASE}/change-lab/dossier",
               json={"scenario": "double-champ", "changement": "Test"})
    assert r.status_code == 201
    d = r.json()
    assert d["id"].startswith("DC-")
    assert d["statut"] == "ouvert"


# ---------- aurora ----------
def test_aurora_registry_support(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "registry",
                     "question": "Pourquoi la connaissance de Support est-elle incomplète ?"})
    assert r.status_code == 200
    body = r.text
    assert "62" in body  # doit contenir "62 %"


def test_aurora_fallback(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "global", "question": "zorglub quantique"})
    assert r.status_code == 200
    d = r.json()
    txt = (d.get("titre", "") + " " + d.get("reponse", "")).lower()
    assert "connaissance" in txt or "manquante" in txt or d.get("fallback") is True or "manqu" in txt


def test_aurora_suggestions(s):
    r = s.get(f"{BASE}/aurora/suggestions", params={"contexte": "radar"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- jumeaux ----------
def test_jumeaux_liste(s):
    r = s.get(f"{BASE}/jumeaux", timeout=15)
    assert r.status_code == 200
    assert len(r.json()) >= 12


def test_creer_et_admettre_jumeau(s):
    payload = {"nom": "TEST Remboursements", "proprietaire": "Équipe Test",
               "mission": "Traite les remboursements", "sources": {"datadog": True}}
    r = s.post(f"{BASE}/jumeaux", json=payload)
    if r.status_code == 409:
        jid = "test-remboursements"
    else:
        assert r.status_code == 201
        jid = r.json()["id"]

    r2 = s.post(f"{BASE}/jumeaux/{jid}/admettre")
    assert r2.status_code == 200
    assert r2.json()["statut"] == "actif"

    r3 = s.get(f"{BASE}/jumeaux")
    j = next((x for x in r3.json() if x["id"] == jid), None)
    assert j is not None
    assert j["statut"] == "actif"


def test_examiner_jumeau(s):
    r = s.post(f"{BASE}/jumeaux/paiements/examiner")
    assert r.status_code == 200
    d = r.json()
    for k in ("identite", "capacites", "comportements", "relations_supposees", "connaissances_manquantes"):
        assert k in d


def test_admettre_inexistant(s):
    r = s.post(f"{BASE}/jumeaux/inconnu-xyz/admettre")
    assert r.status_code == 404


# ---------- démo & activité ----------
def test_demo_actes(s):
    r = s.get(f"{BASE}/demo/actes")
    assert r.status_code == 200
    assert len(r.json()) == 7


def test_activite(s):
    r = s.get(f"{BASE}/activite")
    assert r.status_code == 200
    assert len(r.json()) == 6
