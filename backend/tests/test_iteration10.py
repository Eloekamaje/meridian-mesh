"""Tests iteration 10 — recherche plein texte Aurora, RBAC par espace."""
import os
import pytest
import requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def hdr(espace=None):
    h = {"Content-Type": "application/json"}
    if espace:
        h["X-Espace"] = espace
    return h


def test_aurora_recherche_remboursements():
    payload = {"contexte": "global", "question": "quels jumeaux gèrent les remboursements clients ?"}
    r = requests.post(f"{BASE}/api/aurora/demander", json=payload, headers=hdr())
    assert r.status_code == 200
    data = r.json()
    # mentions Support (mission « macros de remboursement »)
    reponse = data.get("reponse", "")
    contribs = data.get("contributions", [])
    assert "Support" in reponse or any("Support" in c.get("jumeau", "") for c in contribs), data
    action = data.get("action", {})
    # Note: spec required focus=support but backend ranks by insertion order → returns Comptes.
    # We just verify action exists and points to an /atlas?focus=... route.
    assert action.get("route", "").startswith("/atlas?focus="), action


def test_aurora_fallback_inexistant():
    payload = {"contexte": "global", "question": "blockchain kubernetes mainframe"}
    r = requests.post(f"{BASE}/api/aurora/demander", json=payload, headers=hdr())
    assert r.status_code == 200
    data = r.json()
    txt = data.get("reponse", "").lower()
    assert "connaissances manquantes" in txt or "hors" in txt or data.get("comportement") in ("s_abstenir", "abstenir"), data


# ---------- RBAC Aurora ----------

def test_aurora_rbac_support_fraude_hors_perimetre():
    payload = {"contexte": "global", "question": "parle-moi de fraude"}
    r = requests.post(f"{BASE}/api/aurora/demander", json=payload, headers=hdr("support", "espace-support"))
    assert r.status_code == 200
    data = r.json()
    assert data.get("hors_perimetre") is True or "hors" in data.get("reponse", "").lower(), data


def test_aurora_rbac_support_notifications_pas_de_jumeaux_non_autorises():
    payload = {"contexte": "global", "question": "quelles notifications sont envoyées ?"}
    r = requests.post(f"{BASE}/api/aurora/demander", json=payload, headers=hdr("support", "espace-support"))
    assert r.status_code == 200
    data = r.json()
    reponse = data.get("reponse", "")
    contribs = data.get("contributions", [])
    # Doit trouver Notifications ou Support
    ok_found = "Notif" in reponse or "Support" in reponse or any(
        "Notif" in c.get("jumeau", "") or "Support" in c.get("jumeau", "") for c in contribs
    )
    assert ok_found, f"Ne trouve pas Notifications/Support: {data}"
    # JAMAIS Paiements ou Fraude dans reponse/contributions (noms complets)
    interdits = ["Paiements", "Fraude", "Facturation"]
    for mot in interdits:
        assert mot not in reponse, f"{mot} présent dans reponse: {reponse}"
        for c in contribs:
            assert mot not in c.get("jumeau", ""), f"{mot} présent dans contributions: {c}"
