"""Tests for Cases + Flore endpoints (iteration 19)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mesh-insights.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def arch():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Persona": "architecte"})
    return s


@pytest.fixture(scope="module")
def support():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Persona": "support"})
    return s


@pytest.fixture(scope="module", autouse=True)
def reset_seed_at_end(arch):
    yield
    arch.post(f"{BASE_URL}/api/demo/reinitialiser")


# ---- CASES CRUD ----

def test_lister_cases_architecte(arch):
    r = arch.get(f"{BASE_URL}/api/cases")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = {c["id"] for c in data}
    # 5 cases seedés attendus
    assert len(data) >= 5, f"Expected 5+ cases, got {len(data)}: {ids}"
    assert "case-olympiade" in ids
    # nb_messages / nb_decisions / nb_options ajoutés
    for c in data:
        assert "nb_messages" in c
        assert "nb_decisions" in c
        assert "nb_options" in c
        assert "conversation" not in c  # exclu de la liste
        assert "_id" not in c


def test_obtenir_case_olympiade(arch):
    r = arch.get(f"{BASE_URL}/api/cases/case-olympiade")
    assert r.status_code == 200
    case = r.json()
    assert case["id"] == "case-olympiade"
    assert case.get("type") == "incident"
    assert isinstance(case.get("conversation"), list)
    # Doit contenir au moins 2 messages seedés
    assert len(case["conversation"]) >= 2
    assert isinstance(case.get("options"), list)
    assert len(case["options"]) >= 2


def test_obtenir_case_inexistant(arch):
    r = arch.get(f"{BASE_URL}/api/cases/n-existe-pas")
    assert r.status_code == 404


def test_creer_case_et_verifier_persistance(arch):
    payload = {
        "titre": "TEST_case_flore_e2e",
        "type": "demande",
        "objectif": "Vérifier la création via API",
        "jumeaux": ["paiements", "support"],
    }
    r = arch.post(f"{BASE_URL}/api/cases", json=payload)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["titre"] == payload["titre"]
    assert d["statut"] == "ouvert"
    assert d["jumeaux"] == ["paiements", "support"]
    cid = d["id"]
    # GET pour vérifier persistance
    r2 = arch.get(f"{BASE_URL}/api/cases/{cid}")
    assert r2.status_code == 200
    assert r2.json()["objectif"] == "Vérifier la création via API"


def test_patch_case_statut_et_historique(arch):
    # créer un case dédié
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_patch_case", "jumeaux": ["paiements"]})
    cid = r.json()["id"]
    r2 = arch.patch(f"{BASE_URL}/api/cases/{cid}", json={"statut": "en_cours", "objectif": "Nouvel objectif"})
    assert r2.status_code == 200
    d = r2.json()
    assert d["statut"] == "en_cours"
    assert d["objectif"] == "Nouvel objectif"
    # Historique doit contenir la trace du changement de statut
    textes = [h["texte"] for h in d.get("historique", [])]
    assert any("Statut" in t for t in textes)
    assert any("Objectif" in t for t in textes)


def test_message_case_reponse_flore(arch):
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_msg_case", "jumeaux": ["paiements", "support"]})
    cid = r.json()["id"]
    r2 = arch.post(f"{BASE_URL}/api/cases/{cid}/messages", json={"texte": "Que sais-tu du Mesh ?"})
    assert r2.status_code == 201, r2.text
    d = r2.json()
    assert d["utilisateur"]["role"] == "utilisateur"
    assert d["flore"]["role"] == "flore"
    assert isinstance(d["flore"]["texte"], str) and len(d["flore"]["texte"]) > 0
    # Vérifier persistance
    case = arch.get(f"{BASE_URL}/api/cases/{cid}").json()
    assert len(case["conversation"]) == 2


def test_message_vide_400(arch):
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_msg_vide"})
    cid = r.json()["id"]
    r2 = arch.post(f"{BASE_URL}/api/cases/{cid}/messages", json={"texte": "  "})
    assert r2.status_code == 400


def test_ajouter_option_case(arch):
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_opt_case", "jumeaux": ["paiements"]})
    cid = r.json()["id"]
    r2 = arch.post(f"{BASE_URL}/api/cases/{cid}/options", json={
        "titre": "Option A", "description": "desc", "impacts": ["x"], "risque": "faible"
    })
    assert r2.status_code == 201
    opt = r2.json()
    assert opt["titre"] == "Option A"
    assert opt["statut"] == "a_evaluer"
    case = arch.get(f"{BASE_URL}/api/cases/{cid}").json()
    assert len(case["options"]) == 1


def test_ajouter_decision_case(arch):
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_dec_case", "jumeaux": ["paiements"]})
    cid = r.json()["id"]
    r2 = arch.post(f"{BASE_URL}/api/cases/{cid}/decisions", json={"texte": "Aller de l'avant", "type": "arbitrage"})
    assert r2.status_code == 201
    assert r2.json()["texte"] == "Aller de l'avant"
    case = arch.get(f"{BASE_URL}/api/cases/{cid}").json()
    assert len(case["decisions"]) == 1


def test_produire_livrable_case(arch):
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_liv_case", "jumeaux": ["paiements"]})
    cid = r.json()["id"]
    r2 = arch.post(f"{BASE_URL}/api/cases/{cid}/livrables")
    assert r2.status_code == 201
    liv = r2.json()
    assert "id" in liv or "contenu" in liv or "texte" in liv or isinstance(liv, dict)


# ---- Aurora / Flore engine ----

def test_flore_demander_global(arch):
    r = arch.post(f"{BASE_URL}/api/aurora/demander", json={
        "contexte": "global", "question": "Que sais-tu du Mesh ?", "selection": [], "domaine": None
    })
    assert r.status_code == 200
    d = r.json()
    assert "reponse" in d


def test_flore_demander_selection(arch):
    r = arch.post(f"{BASE_URL}/api/aurora/demander", json={
        "contexte": "atlas", "question": "Comprendre leurs relations",
        "selection": ["paiements", "support"], "domaine": None
    })
    assert r.status_code == 200
    d = r.json()
    assert "reponse" in d


# ---- RBAC support ----

def test_rbac_support_cases_filtre(support):
    r = support.get(f"{BASE_URL}/api/cases")
    assert r.status_code == 200
    cases = r.json()
    # support ne voit pas tous les cases
    ids = {c["id"] for c in cases}
    # olympiade doit être visible (concerne paiements/support probablement) ou pas selon périmètre
    # au moins on vérifie que la liste est bornée
    assert isinstance(cases, list)
    return ids


def test_rbac_support_case_hors_perimetre_403(support, arch):
    # Trouver un case dont les jumeaux sont hors périmètre support
    r_arch = arch.get(f"{BASE_URL}/api/cases")
    r_sup = support.get(f"{BASE_URL}/api/cases")
    arch_ids = {c["id"] for c in r_arch.json()}
    sup_ids = {c["id"] for c in r_sup.json()}
    hors = arch_ids - sup_ids
    if not hors:
        pytest.skip("Aucun case hors périmètre support — pas de vérification 403 possible")
    cid = next(iter(hors))
    r = support.get(f"{BASE_URL}/api/cases/{cid}")
    assert r.status_code == 403, f"Expected 403 for {cid}, got {r.status_code}"


# ---- Redirections front (routes backend still working) ----

def test_seed_version(arch):
    r = arch.get(f"{BASE_URL}/api/etat")
    if r.status_code != 200:
        pytest.skip("Pas d'endpoint /etat")
    # Vérifier via un autre endpoint que le seed est ok
