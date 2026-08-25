"""End-to-end backend API tests for Méridian v2 (repositionnement Découverte/Comprendre/Décider)."""
import os
import pytest
import requests

# Read REACT_APP_BACKEND_URL from env or from frontend/.env
if "REACT_APP_BACKEND_URL" not in os.environ:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()
                break

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---------- Santé ----------
def test_health(s):
    r = s.get(f"{BASE}/health", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- Mesh ----------
def test_mesh(s):
    r = s.get(f"{BASE}/mesh", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert len(data["jumeaux"]) >= 12
    assert len(data["relations"]) >= 14
    assert len(data["regions"]) == 6
    # nouveau : relations ont un champ etat
    etats = {r_.get("etat") for r_ in data["relations"]}
    assert etats & {"confirmee", "validation", "supposee", "contestee", "obsolete", "observee"}


# ---------- Situations (11, avec verbe/nature) ----------
def test_situations_liste(s):
    r = s.get(f"{BASE}/situations", timeout=15)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) >= 11
    # tri décroissant par score
    scores = [d["score"] for d in docs]
    assert scores == sorted(scores, reverse=True)
    # champs v2
    for d in docs:
        assert "verbe" in d
        assert "nature" in d


def test_situation_detail_sit_relation_emergente(s):
    r = s.get(f"{BASE}/situations/sit-relation-emergente")
    assert r.status_code == 200
    j = r.json()
    assert j["id"] == "sit-relation-emergente"
    assert j.get("nature") == "relation"


def test_situation_action_coincidence_puis_restore(s):
    sid = "sit-regle-implicite"
    # snapshot
    before = s.get(f"{BASE}/situations/{sid}").json()
    statut_initial = before.get("statut", "active")
    # action
    r = s.post(f"{BASE}/situations/{sid}/action", json={"action": "coincidence"})
    assert r.status_code == 200
    assert r.json()["statut"] == "classée"
    # persistance
    r2 = s.get(f"{BASE}/situations/{sid}")
    assert r2.json()["statut"] == "classée"
    # restauration via API decision (n'existe pas) → on rétablit directement via update Mongo
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    client["test_database"]["situations"].update_one({"id": sid}, {"$set": {"statut": statut_initial}})
    r3 = s.get(f"{BASE}/situations/{sid}")
    assert r3.json()["statut"] == statut_initial


def test_situation_action_invalide(s):
    r = s.post(f"{BASE}/situations/sit-latence-paiements/action", json={"action": "bidon"})
    assert r.status_code == 400


# ---------- Relations : confirmer + restore ----------
def test_confirmer_relation_r6_puis_restore(s):
    r = s.post(f"{BASE}/relations/r6/confirmer")
    assert r.status_code == 200
    body = r.json()
    assert body["etat"] == "confirmee"
    assert body["memoire"] == "enrichie"
    # vérifie via /mesh
    mesh = s.get(f"{BASE}/mesh").json()
    r6 = next((x for x in mesh["relations"] if x["id"] == "r6"), None)
    assert r6 and r6["etat"] == "confirmee"
    assert "Validation humaine" in r6.get("confirmee_par", [])
    # restore
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    client["test_database"]["relations"].update_one(
        {"id": "r6"},
        {"$set": {"etat": "validation"}, "$pull": {"confirmee_par": "Validation humaine"}},
    )
    mesh2 = s.get(f"{BASE}/mesh").json()
    r6b = next((x for x in mesh2["relations"] if x["id"] == "r6"), None)
    assert r6b["etat"] == "validation"


def test_confirmer_relation_inexistante(s):
    r = s.post(f"{BASE}/relations/rXXX/confirmer")
    assert r.status_code == 404


# ---------- Décisions ----------
def test_decisions_endpoint(s):
    r = s.get(f"{BASE}/decisions")
    assert r.status_code == 200
    d = r.json()
    assert set(d.keys()) >= {"situations", "admissions", "relations"}
    # Selon la spec : 4 situations à décider, 3 relations, 2 admissions
    assert len(d["situations"]) >= 3
    assert len(d["relations"]) >= 3
    assert len(d["admissions"]) >= 2


# ---------- Change Lab ----------
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


# ---------- Aurora prescripté ----------
def test_aurora_atlas_mentionne_APP_2748(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "atlas", "question": "Que cherches-tu encore à comprendre ?"})
    assert r.status_code == 200
    body = r.text
    assert "APP-2748" in body


def test_aurora_comportement_investigation(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "investigation",
                     "question": "Pourquoi considères-tu que Paiements influence Support ?"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("comportement") == "expliquer"


def test_aurora_comportement_decisions(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "decisions",
                     "question": "Que devrions-nous faire concernant cette relation ?"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("comportement") == "recommander"


def test_aurora_fallback(s):
    r = s.post(f"{BASE}/aurora/demander",
               json={"contexte": "global", "question": "zorglub quantique"})
    assert r.status_code == 200
    d = r.json()
    txt = (str(d.get("reponse", ""))).lower()
    assert "manqu" in txt or "connaissance" in txt


def test_aurora_suggestions_par_contexte(s):
    for ctx in ("aujourdhui", "atlas", "investigation", "decisions", "jumeaux"):
        r = s.get(f"{BASE}/aurora/suggestions", params={"contexte": ctx})
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1


# ---------- Jumeaux ----------
def test_jumeaux_liste(s):
    r = s.get(f"{BASE}/jumeaux", timeout=15)
    assert r.status_code == 200
    assert len(r.json()) >= 12


def test_creer_admettre_supprimer_jumeau(s):
    # nom conforme à la spec : "TEST Relances" → id "test-relances"
    payload = {"nom": "TEST Relances", "proprietaire": "Équipe Test",
               "mission": "Traite les relances", "sources": {"datadog": True}}
    r = s.post(f"{BASE}/jumeaux", json=payload)
    if r.status_code == 409:
        jid = "test-relances"
    else:
        assert r.status_code == 201, r.text
        jid = r.json()["id"]

    r2 = s.post(f"{BASE}/jumeaux/{jid}/admettre")
    assert r2.status_code == 200
    assert r2.json()["statut"] == "actif"

    lst = s.get(f"{BASE}/jumeaux").json()
    assert any(x["id"] == jid for x in lst)

    # Nettoyage direct MongoDB (spec)
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    client["test_database"]["jumeaux"].delete_one({"id": jid})
    lst2 = s.get(f"{BASE}/jumeaux").json()
    assert not any(x["id"] == jid for x in lst2)


def test_examiner_jumeau(s):
    r = s.post(f"{BASE}/jumeaux/paiements/examiner")
    assert r.status_code == 200
    d = r.json()
    for k in ("identite", "capacites", "comportements", "relations_supposees", "connaissances_manquantes"):
        assert k in d


def test_admettre_inexistant(s):
    r = s.post(f"{BASE}/jumeaux/inconnu-xyz/admettre")
    assert r.status_code == 404


# ---------- Démo Olympiade (3 actes) & activité ----------
def test_demo_actes_3(s):
    r = s.get(f"{BASE}/demo/actes")
    assert r.status_code == 200
    d = r.json()
    assert len(d) == 3
    assert [a["acte"] for a in d] == [1, 2, 3]
    assert d[0]["route"] == "/atlas"
    assert d[1]["route"] == "/investigations/sit-relation-emergente"
    assert d[2]["route"] == "/decisions"


def test_activite(s):
    r = s.get(f"{BASE}/activite")
    assert r.status_code == 200
    # random.sample(ACTIVITE, 6) → 6 éléments
    assert len(r.json()) == 6
