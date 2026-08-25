"""Backend tests v3 — matrice de refus par périmètre (personas + espaces).

Tous les tests mutatifs restaurent l'état initial via pymongo à la fin.
"""
import os
import pytest
import requests
from pymongo import MongoClient

if "REACT_APP_BACKEND_URL" not in os.environ:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()
                break

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

MONGO = MongoClient("mongodb://localhost:27017")
DB = MONGO["test_database"]


def H(persona, espace=None):
    h = {"X-Persona": persona}
    if espace:
        h["X-Espace"] = espace
    return h


# ---------- Personas / Espaces ----------
def test_personas():
    r = requests.get(f"{BASE}/personas")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert set(ids) >= {"architecte", "paiements", "support"}


def test_espaces_paiements():
    r = requests.get(f"{BASE}/espaces", headers=H("paiements"))
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert ids == ["espace-paiements"]


def test_perimetre_paiements():
    r = requests.get(f"{BASE}/perimetre", headers=H("paiements", "espace-paiements"))
    assert r.status_code == 200
    d = r.json()
    assert d["persona"]["id"] == "paiements"
    assert d["espace"]["id"] == "espace-paiements"
    assert set(d["autorisations"].keys()) == {"paiements", "facturation", "comptes"}
    assert d["autorisations"]["comptes"] == "relations"


# ---------- Mesh : matrice de refus ----------
def test_mesh_paiements_resume_autorise():
    r = requests.get(f"{BASE}/mesh", headers=H("paiements", "espace-paiements"))
    assert r.status_code == 200
    d = r.json()
    ids = {j["id"] for j in d["jumeaux"] if not j.get("anonyme")}
    assert ids == {"paiements", "facturation", "comptes"}
    # nœuds restreints anonymisés « Application restreinte — domaine X »
    anon = [j for j in d["jumeaux"] if j.get("anonyme")]
    assert len(anon) >= 1
    assert all(n["nom"].startswith("Application restreinte") for n in anon)
    # aucun jumeau réel non autorisé ne fuite (les anonymes affichent le domaine)
    real_ids = {j["id"] for j in d["jumeaux"] if not j.get("anonyme")}
    for forbidden in ("fraude", "support", "conformite", "identite", "notifications"):
        assert forbidden not in real_ids
    # champs sensibles : comptes est niveau "relations" → pas de proprietaire ni sources
    comptes = next(j for j in d["jumeaux"] if j.get("id") == "comptes")
    assert "proprietaire" not in comptes
    assert "sources" not in comptes
    # perimetre marker
    assert d["perimetre"]["politique"] == "resume"


def test_mesh_support_anonymisee_sans_domaine():
    r = requests.get(f"{BASE}/mesh", headers=H("support", "espace-support"))
    assert r.status_code == 200
    d = r.json()
    anon = [j for j in d["jumeaux"] if j.get("anonyme")]
    assert len(anon) >= 1
    # anonymisée => libellé sans domaine
    for n in anon:
        assert n["nom"] == "Dépendance externe restreinte"


def test_mesh_risque_masquage():
    # architecte peut switcher espace-risque
    r = requests.get(f"{BASE}/mesh", headers=H("architecte", "espace-risque"))
    assert r.status_code == 200
    d = r.json()
    ids = {j["id"] for j in d["jumeaux"]}
    # policy masquage : aucune anonyme
    assert not any(j.get("anonyme") for j in d["jumeaux"])
    # aucune relation ne va vers non-autorisé
    for rel in d["relations"]:
        assert rel["source"] in ids and rel["cible"] in ids


# ---------- Situations : filtrage & 404 ----------
def test_situations_paiements_filtrees():
    r = requests.get(f"{BASE}/situations", headers=H("paiements", "espace-paiements"))
    assert r.status_code == 200
    docs = r.json()
    ids = {s["id"] for s in docs}
    assert "sit-connaissance-support" not in ids
    # sit-latence-paiements présent + restreinte:true (car support retiré)
    lat = next((s for s in docs if s["id"] == "sit-latence-paiements"), None)
    assert lat is not None
    assert lat.get("restreinte") is True


def test_situation_support_404_pour_paiements():
    r = requests.get(f"{BASE}/situations/sit-connaissance-support",
                     headers=H("paiements", "espace-paiements"))
    assert r.status_code == 404


# ---------- Aurora ----------
def test_aurora_hors_perimetre_paiements_sur_support():
    r = requests.post(f"{BASE}/aurora/demander",
                      headers=H("paiements", "espace-paiements"),
                      json={"contexte": "jumeaux",
                            "question": "Pourquoi la connaissance de Support est-elle incomplète ?"})
    assert r.status_code == 200
    assert r.json().get("hors_perimetre") is True


def test_aurora_normal_architecte_mesh_global():
    r = requests.post(f"{BASE}/aurora/demander",
                      headers=H("architecte", "mesh-global"),
                      json={"contexte": "jumeaux",
                            "question": "Pourquoi la connaissance de Support est-elle incomplète ?"})
    assert r.status_code == 200
    j = r.json()
    assert not j.get("hors_perimetre")
    txt = str(j.get("reponse", ""))
    assert "62" in txt or "Support" in txt or "support" in txt


def test_aurora_suggestions_paiements_pas_support():
    r = requests.get(f"{BASE}/aurora/suggestions",
                     headers=H("paiements", "espace-paiements"),
                     params={"contexte": "jumeaux"})
    assert r.status_code == 200
    sugs = r.json()
    assert not any("support" in s.lower() for s in sugs)


# ---------- Relations : confirmer (guards 403) ----------
def test_confirmer_r6_espace_support_reussit():
    """Support est complet dans espace-support ; r6 = paiements→support → complet sur cible."""
    r = requests.post(f"{BASE}/relations/r6/confirmer",
                      headers=H("support", "espace-support"))
    try:
        assert r.status_code == 200
        assert r.json()["etat"] == "confirmee"
    finally:
        DB["relations"].update_one(
            {"id": "r6"},
            {"$set": {"etat": "validation"}, "$pull": {"confirmee_par": "Validation humaine"}},
        )


def test_confirmer_r12_espace_paiements_403():
    """r12 = fraude→conformite ; en espace-paiements, aucune extrémité autorisée."""
    r = requests.post(f"{BASE}/relations/r12/confirmer",
                      headers=H("paiements", "espace-paiements"))
    assert r.status_code == 403


# ---------- Jumeaux : admettre (404 vs 200) ----------
def test_admettre_conformite_paiements_404():
    r = requests.post(f"{BASE}/jumeaux/conformite/admettre",
                      headers=H("paiements", "espace-paiements"))
    assert r.status_code == 404


def test_admettre_conformite_architecte_200():
    # snapshot
    before = DB["jumeaux"].find_one({"id": "conformite"}, {"_id": 0})
    try:
        r = requests.post(f"{BASE}/jumeaux/conformite/admettre",
                          headers=H("architecte", "mesh-global"))
        assert r.status_code == 200
        assert r.json()["statut"] == "actif"
    finally:
        DB["jumeaux"].update_one(
            {"id": "conformite"},
            {"$set": {"statut": before.get("statut", "en construction"),
                      "autonomie": before.get("autonomie", "aucune")}},
        )


# ---------- Activité / Décisions ----------
def test_activite_paiements_pool_filtre():
    r = requests.get(f"{BASE}/activite", headers=H("paiements", "espace-paiements"))
    assert r.status_code == 200
    for ev in r.json():
        assert ev["jumeau"] in {"paiements", "facturation", "comptes"}


def test_decisions_paiements_pas_r12_r14():
    r = requests.get(f"{BASE}/decisions", headers=H("paiements", "espace-paiements"))
    assert r.status_code == 200
    rids = {x["id"] for x in r.json().get("relations", [])}
    assert "r12" not in rids and "r14" not in rids


# ---------- Vues ----------
def test_vues_paiements_liste_deux():
    r = requests.get(f"{BASE}/vues", headers=H("paiements"))
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_creer_vue_puis_verifier_puis_delete():
    nom = "TEST_vue_perim"
    try:
        r = requests.post(f"{BASE}/vues",
                          headers=H("paiements"),
                          json={"nom": nom, "type": "selection",
                                "jumeaux": ["paiements", "facturation"]})
        assert r.status_code == 201
        vue = r.json()
        assert vue["nom"] == nom
        # verifier
        r2 = requests.get(f"{BASE}/vues", headers=H("paiements"))
        assert any(v["nom"] == nom for v in r2.json())
    finally:
        DB["vues"].delete_many({"nom": nom})


# ---------- Journal ----------
def test_journal_endpoint():
    # écrire une entrée d'abord pour garantir des données
    requests.post(f"{BASE}/journal",
                  headers=H("architecte", "mesh-global"),
                  json={"action": "test", "detail": "backend_test_perimetres"})
    r = requests.get(f"{BASE}/journal")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1
