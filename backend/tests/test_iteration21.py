"""Iteration 21 — Cockpit case + resume/hypotheses/investigations + DELETE jumeau + evolutions_recentes."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://mesh-insights.preview.emergentagent.com").rstrip("/") + "/api"


def H():
    return {"Content-Type": "application/json"}


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
def test_delete_jumeau_inexistant_404():
    r = requests.delete(f"{BASE}/jumeaux/inexistant-xyz", headers=H(), timeout=15)
    assert r.status_code == 404


# --- 7. Reset conserve notifications correctement ---
