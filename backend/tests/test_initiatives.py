"""Tests des Initiatives du Mesh et des délégations (grammaire d'interaction)."""
import os
import pytest
import requests

if "REACT_APP_BACKEND_URL" not in os.environ:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()
                break

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def test_compteurs(s):
    d = s.get(f"{BASE}/initiatives/compteurs", headers={}, timeout=15).json()
    assert d["a_traiter"] >= 4
    assert d["radar"] >= 1


def test_a_traiter_contenu(s):
    d = s.get(f"{BASE}/initiatives?vue=a_traiter", headers={}, timeout=15).json()
    ids = {i["id"] for i in d}
    assert "init-decision-utc" in ids and "init-investigation-degradation" in ids
    # les initiatives de l'équipe Paiements sont visibles depuis le Mesh global (architecte)
    assert "init-contrat-paiements" in ids
    for i in d:
        assert i["statut"] == "en_attente"
        assert i["pourquoi_vous"] and i["attendu"]  # 7 questions


def test_reponse_suivre_puis_409(s):
    r = s.post(f"{BASE}/initiatives/init-delais-coordonnes/repondre", json={"choix": "Suivre"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["initiative"]["statut"] == "suivi"
    r2 = s.post(f"{BASE}/initiatives/init-delais-coordonnes/repondre", json={"choix": "Ignorer"}, timeout=15)
    assert r2.status_code == 409
    suivis = s.get(f"{BASE}/initiatives?vue=suivis", headers={}, timeout=15).json()
    assert any(i["id"] == "init-delais-coordonnes" for i in suivis)


def test_reponse_confirmation_par_destinataire(s):
    r = s.post(
        f"{BASE}/initiatives/init-contrat-paiements/repondre",
        json={"choix": "Version 3 — le code fait foi"},
        headers={},
        timeout=15,
    )
    assert r.status_code == 200
    rep = r.json()["initiative"]["reponse"]
    assert rep["par"] == "paiements"


def test_reponse_rejet_motif_conserve(s):
    r = s.post(
        f"{BASE}/initiatives/init-admission-conformite/repondre",
        json={"choix": "Rejeter la proposition", "motif": "Couverture 43 % insuffisante, Splunk en retard"},
        timeout=15,
    )
    assert r.status_code == 200
    init = r.json()["initiative"]
    assert init["statut"] == "refusee"
    assert "Couverture" in init["reponse"]["motif"]


def test_reponse_creer_travail(s):
    r = s.post(f"{BASE}/initiatives/init-investigation-degradation/repondre", json={"choix": "Créer un nouveau travail"}, timeout=15)
    assert r.status_code == 200
    tid = r.json()["travail_id"]
    assert tid and tid.startswith("case-")
    case = s.get(f"{BASE}/cases/{tid}", timeout=15).json()
    assert case["jumeaux"] == ["paiements", "fraude", "comptes", "support"]
    assert case["type"] == "investigation"


def test_delegations_cycle(s):
    r = s.post(f"{BASE}/delegations", json={"type": "surveillance", "jumeaux": ["paiements", "fraude"], "duree_h": 24}, timeout=15)
    assert r.status_code == 201
    d = r.json()
    assert d["statut"] == "active" and d["livrable"] and d["validation_requise"]
    liste = s.get(f"{BASE}/delegations", timeout=15).json()
    assert any(x["id"] == d["id"] for x in liste)
    # délégation sans jumeau autorisé → 400
    r2 = s.post(f"{BASE}/delegations", json={"type": "surveillance", "jumeaux": ["inconnu"]}, timeout=15)
    assert r2.status_code == 400
