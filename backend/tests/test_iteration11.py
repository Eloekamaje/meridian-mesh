"""Iteration 11 — Refonte Aurora↔Atlas : intentions calculées, RBAC, accusé contexte."""
import os
import pytest
import requests
from pathlib import Path

def _load_url():
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = _load_url().rstrip("/")
AURORA = f"{BASE_URL}/api/aurora/demander"


def _post(payload, espace=None):
    headers = {"Content-Type": "application/json"}
    if espace:
        headers["X-Espace"] = espace
    return requests.post(AURORA, json=payload, headers=headers, timeout=15)


# ---------- Intention: relations ----------
def test_intention_relations_paiements_fraude_identite():
    r = _post({"question": "Comprendre leurs relations", "selection": ["paiements", "fraude", "identite"]})
    assert r.status_code == 200
    data = r.json()
    txt = data["reponse"]
    assert "Paiements" in txt and "Fraude" in txt
    assert "Identité" in txt or "Identite" in txt
    # contradiction (Identité → Paiements contestée)
    assert "Contradiction" in txt or "contestée" in txt or "contestee" in txt
    assert data.get("commande_carte", {}).get("type") == "relations"
    ids = data["commande_carte"]["ids"]
    assert "r5" in ids and "r14" in ids


# ---------- Intention: inconnues ----------
def test_intention_inconnues_propose_voisin():
    r = _post({"question": "Rechercher des dépendances inconnues", "selection": ["paiements", "facturation"]})
    assert r.status_code == 200
    data = r.json()
    # Relations non confirmées listées
    assert "non confirmée" in data["reponse"] or "non confirmee" in data["reponse"]
    props = data.get("propositions", [])
    assert props, "Attendu au moins une proposition"
    # Support attendu comme voisin proposé (le plus lié à la sélection en non-confirmé)
    noms = [p["nom"] for p in props]
    assert any("Support" in n for n in noms), f"Support attendu dans propositions, reçu: {noms}"


# ---------- Intention: impact ----------
def test_intention_impact_change_lab():
    r = _post({"question": "Analyser un changement", "selection": ["paiements"]})
    assert r.status_code == 200
    data = r.json()
    assert "voisin" in data["reponse"].lower()
    assert data.get("action", {}).get("route") == "/decisions"
    assert "Change Lab" in data["action"]["label"]


# ---------- Intention: parcours ----------
def test_intention_parcours():
    r = _post({"question": "Optimiser ce parcours", "selection": ["commandes", "paiements", "comptes"]})
    assert r.status_code == 200
    data = r.json()
    assert data.get("commande_carte", {}).get("type") == "parcours"
    assert set(data["commande_carte"]["ids"]) == {"commandes", "paiements", "comptes"}


# ---------- Intention: investigation ----------
def test_intention_investigation():
    r = _post({"question": "Ouvrir une investigation", "selection": ["paiements", "support"]})
    assert r.status_code == 200
    data = r.json()
    assert data.get("action", {}).get("route") == "/investigations"
    assert data["action"]["label"] == "Transformer en investigation"


# ---------- Accusé de contexte : sélection SANS intention ----------
def test_accuse_contexte_sans_intention():
    r = _post({"question": "bonjour", "selection": ["paiements", "comptes"]})
    assert r.status_code == 200
    data = r.json()
    txt = data["reponse"]
    # Reformule la sélection, pas d'analyse
    assert "Paiements" in txt and "Comptes" in txt
    assert "Contexte actif" in txt or "jumeau" in txt.lower()
    # Pas de commande_carte pour un simple accusé
    assert "commande_carte" not in data or not data.get("commande_carte")


# ---------- Domaine sans sélection ----------
def test_domaine_sans_selection_utilise_jumeaux_du_domaine():
    r = _post({"question": "Comprendre les relations internes", "domaine": "Paiement"})
    assert r.status_code == 200
    data = r.json()
    # doit exploiter les twins Paiement (paiements, facturation)
    assert data.get("commande_carte", {}).get("type") == "relations" or "relation" in data["reponse"].lower()


# ---------- RBAC : support ne voit pas Paiements ----------
