"""Iteration 21 — Cockpit case + resume/hypotheses/investigations + DELETE jumeau + evolutions_recentes."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://mesh-insights.preview.emergentagent.com").rstrip("/") + "/api"


def H(persona="architecte"):
    return {"X-Persona": persona, "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def _reset_after():
    yield
    requests.post(f"{BASE}/demo/reinitialiser", headers=H(), timeout=15)


# --- 1. GET /cases/{id} contient num/resume/sensibilite/evolutions_recentes ---
def test_case_detail_contient_nouveaux_champs():
    r = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H(), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["num"] == 42
    assert "resume" in d
    assert d["sensibilite"] in ("interne", "restreinte", "publique", "confidentiel")
    assert "evolutions_recentes" in d
    assert isinstance(d["evolutions_recentes"], list)


def test_case_olympiade_num_41():
    r = requests.get(f"{BASE}/cases/case-olympiade", headers=H(), timeout=15)
    assert r.status_code == 200
    assert r.json()["num"] == 41


# --- 2. POST /cases/{id}/resume ---
def test_actualiser_resume():
    r = requests.post(f"{BASE}/cases/case-paiement-differe/resume", headers=H(), timeout=15)
    assert r.status_code == 201
    data = r.json()
    assert "resume" in data and isinstance(data["resume"], str) and len(data["resume"]) > 0
    # GET to verify persistence
    g = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H(), timeout=15).json()
    assert g["resume"] == data["resume"]


# --- 3. POST /cases/{id}/hypotheses ---
def test_ajouter_hypothese_persistance():
    payload = {"texte": "TEST_hyp — les décalages viennent d'un lot batch"}
    r = requests.post(f"{BASE}/cases/case-paiement-differe/hypotheses", headers=H(), json=payload, timeout=15)
    assert r.status_code == 201
    h = r.json()
    assert h["texte"] == payload["texte"]
    assert h["statut"] == "a_valider"
    g = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H(), timeout=15).json()
    assert any(x["id"] == h["id"] for x in g.get("hypotheses", []))


def test_hypothese_vide_400():
    r = requests.post(f"{BASE}/cases/case-paiement-differe/hypotheses", headers=H(), json={"texte": "   "}, timeout=15)
    assert r.status_code == 400


# --- 4. POST /cases/{id}/investigations crée une situation liée ---
def test_ouvrir_investigation_cree_situation():
    payload = {"texte": "TEST_invest — comprendre l'écart Cs-Rb"}
    r = requests.post(f"{BASE}/cases/case-paiement-differe/investigations", headers=H(), json=payload, timeout=15)
    assert r.status_code == 201
    sit = r.json()
    sid = sit["id"]
    assert sit["nature"] == "investigation"
    assert sit["question"] == payload["texte"]
    # Situation créée en base
    g = requests.get(f"{BASE}/situations/{sid}", headers=H(), timeout=15)
    assert g.status_code == 200
    # Attachée au case
    c = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H(), timeout=15).json()
    assert sid in c.get("situations", [])


# --- 5. Evolutions_recentes : première visite (historique récent) puis rien de nouveau ---
def test_evolutions_recentes_multi_persona():
    # architecte fait une action (ajoute hypothèse -> génère historique)
    requests.post(
        f"{BASE}/cases/case-paiement-differe/hypotheses",
        headers=H("architecte"),
        json={"texte": "TEST_evo_track_" + str(int(time.time()))},
        timeout=15,
    )
    # support visite : première visite -> pas de dernière visite donc evolutions = [] (historique filtré uniquement si derniere)
    r1 = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H("support"), timeout=15)
    assert r1.status_code == 200
    # architecte fait une nouvelle action
    requests.post(
        f"{BASE}/cases/case-paiement-differe/hypotheses",
        headers=H("architecte"),
        json={"texte": "TEST_evo_apres_visite_" + str(int(time.time()))},
        timeout=15,
    )
    # support revient : devrait voir cette évolution
    r2 = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H("support"), timeout=15).json()
    evos = r2.get("evolutions_recentes", [])
    assert any("Hypothèse ajoutée" in e.get("texte", "") for e in evos), f"Aucune évolution captée: {evos}"
    # Visite suivante immédiate : rien de nouveau
    r3 = requests.get(f"{BASE}/cases/case-paiement-differe", headers=H("support"), timeout=15).json()
    assert r3.get("evolutions_recentes", []) == []


# --- 6. DELETE /api/jumeaux/{id} : CRUD complet ---
def test_delete_jumeau_cycle():
    # Create
    payload = {"nom": "TEST Del Jumeau", "proprietaire": "test", "mission": "test cycle"}
    r = requests.post(f"{BASE}/jumeaux", headers=H(), json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    jid = r.json()["id"]
    # Delete
    d = requests.delete(f"{BASE}/jumeaux/{jid}", headers=H(), timeout=15)
    assert d.status_code in (200, 204), d.text
    # Verify via list (no GET /jumeaux/{id})
    g = requests.get(f"{BASE}/jumeaux", headers=H(), timeout=15).json()
    ids = [j["id"] for j in g]
    assert jid not in ids


def test_delete_jumeau_inexistant_404():
    r = requests.delete(f"{BASE}/jumeaux/inexistant-xyz", headers=H(), timeout=15)
    assert r.status_code == 404


# --- 7. Reset conserve notifications correctement ---
def test_reset_purge_notifications():
    r = requests.post(f"{BASE}/demo/reinitialiser", headers=H(), timeout=20)
    assert r.status_code == 200
    n = requests.get(f"{BASE}/notifications", headers=H(), timeout=15)
    assert n.status_code == 200
    # après reset, les 2 notifs seedées existent
    lst = n.json()
    # notifications endpoint returns {notifications: [...], non_lues: N}
    if isinstance(lst, dict):
        lst = lst.get("notifications", [])
    assert isinstance(lst, list) and len(lst) >= 1
