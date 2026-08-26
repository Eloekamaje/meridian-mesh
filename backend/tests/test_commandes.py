"""Tests backend pour l'atelier de commande d'un jumeau (Méridian iter14)."""
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


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    yield sess
    # Nettoyage final : ré-initialisation démo
    try:
        sess.post(f"{BASE}/demo/reinitialiser", timeout=30)
    except Exception:
        pass


# ---------- Catalogue connecteurs ----------
def test_connecteurs_catalogue(s):
    r = s.get(f"{BASE}/connecteurs", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "connecteurs" in d and "contributions" in d and "profils" in d
    assert len(d["connecteurs"]) == 12, f"attendu 12 connecteurs, reçu {len(d['connecteurs'])}"
    categories = {c.get("categorie") for c in d["connecteurs"]}
    assert len(categories) == 10, f"attendu 10 catégories, reçu {len(categories)} : {categories}"
    # PostgreSQL doit exposer les 6 champs
    pg = next(c for c in d["connecteurs"] if c["id"] == "postgresql")
    cles = {ch["cle"] for ch in pg["champs"]}
    assert cles >= {"hote", "port", "base", "schemas", "secret", "frequence"}, cles
    assert len(d["profils"]) >= 2


# ---------- Liste et brouillon de démo ----------
def test_commandes_seed_remboursements(s):
    r = s.get(f"{BASE}/commandes", timeout=15)
    assert r.status_code == 200
    lst = r.json()
    cmd = next((c for c in lst if c["id"] == "cmd-remboursements"), None)
    assert cmd, "cmd-remboursements manquant dans les brouillons"
    assert len(cmd["sources"]) == 8, f"attendu 8 sources, reçu {len(cmd['sources'])}"
    assert cmd["jumeau"]["nom"] == "Remboursements"


def test_lire_commande_remboursements(s):
    r = s.get(f"{BASE}/commandes/cmd-remboursements", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == "cmd-remboursements"
    assert any(x["id"] == "src-oracle" for x in d["sources"])


# ---------- Création & PATCH ----------
def test_creer_et_patch_commande(s):
    r = s.post(f"{BASE}/commandes", json={"nom": "TEST Cmd", "mission": "test", "proprietaire": "QA"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["etat"] == "brouillon"
    assert doc["sources"] == []
    cid = doc["id"]

    # PATCH : ajouter une source
    r2 = s.patch(f"{BASE}/commandes/{cid}", json={"sources": [{"id": "s1", "connecteur": "postgresql", "nom": "x", "config": {}, "statut": "a_configurer", "erreur": None, "dernier_test": None, "perimetre": ""}]})
    assert r2.status_code == 200
    r3 = s.get(f"{BASE}/commandes/{cid}")
    assert len(r3.json()["sources"]) == 1

    # cleanup
    from pymongo import MongoClient
    MongoClient("mongodb://localhost:27017")["test_database"]["commandes"].delete_one({"id": cid})


# ---------- /tester ----------
def test_tester_oracle_configuration_incomplete(s):
    r = s.post(f"{BASE}/commandes/cmd-remboursements/tester", json={"ids": ["src-oracle"]}, timeout=15)
    assert r.status_code == 200
    res = r.json()["resultats"]["src-oracle"]
    assert res["statut"] == "configuration_incomplete"
    assert res["erreur"]["titre"]
    # persistance
    doc = s.get(f"{BASE}/commandes/cmd-remboursements").json()
    src = next(x for x in doc["sources"] if x["id"] == "src-oracle")
    assert src["statut"] == "configuration_incomplete"


def test_tester_pg_prete(s):
    r = s.post(f"{BASE}/commandes/cmd-remboursements/tester", json={"ids": ["src-pg-prod"]}, timeout=15)
    assert r.status_code == 200
    res = r.json()["resultats"]["src-pg-prod"]
    assert res["statut"] == "prete", res


# ---------- /import/apercu ----------
def test_import_apercu_cmdb(s):
    r = s.post(f"{BASE}/commandes/cmd-remboursements/import/apercu", json={"mode": "cmdb"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["detectees"] == 7, d
    # PostgreSQL Production doit être détecté comme déjà présent
    presentes_noms = [p["nom"] for p in d["presentes"]]
    assert "PostgreSQL Production" in presentes_noms
    assert len(d["nouvelles"]) == 5
    assert any(x["nom"] == "SAP FI" for x in d["a_mapper"])


# ---------- /lancer ----------
def test_lancer_incomplet_422(s):
    # Créer une commande sans identité complète
    r = s.post(f"{BASE}/commandes", json={"nom": ""})
    cid = r.json()["id"]
    r2 = s.post(f"{BASE}/commandes/{cid}/lancer")
    assert r2.status_code == 422
    # cleanup
    from pymongo import MongoClient
    MongoClient("mongodb://localhost:27017")["test_database"]["commandes"].delete_one({"id": cid})


def test_lancer_complet_puis_409(s):
    # Sur cmd-remboursements, il y a src-pg-prod prête
    r = s.post(f"{BASE}/commandes/cmd-remboursements/lancer")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["jumeau_id"] == "remboursements"
    # Vérifier création du jumeau
    lst = s.get(f"{BASE}/jumeaux").json()
    assert any(j["id"] == "remboursements" for j in lst)
    # 409 si relance : la commande est passée en "lancee", donc lister /commandes ne la montre plus
    # Créons une nouvelle commande avec même nom pour tester le 409
    r2 = s.post(f"{BASE}/commandes", json={"nom": "Remboursements", "mission": "x", "proprietaire": "y"})
    cid2 = r2.json()["id"]
    # Ajouter une source prête
    src = {"id": "sx", "connecteur": "postgresql", "nom": "z", "config": {"hote": "h", "port": 5432, "base": "b", "schemas": "s", "secret": "sec", "frequence": "horaire"}, "perimetre": "s", "statut": "prete", "erreur": None, "dernier_test": None}
    s.patch(f"{BASE}/commandes/{cid2}", json={"sources": [src]})
    r3 = s.post(f"{BASE}/commandes/{cid2}/lancer")
    assert r3.status_code == 409, r3.text


# ---------- Non-régression : réinit démo remet l'état ----------
def test_reinitialiser_demo_restaure_cmd(s):
    r = s.post(f"{BASE}/demo/reinitialiser", timeout=30)
    assert r.status_code == 200
    # cmd-remboursements doit exister à nouveau
    lst = s.get(f"{BASE}/commandes").json()
    assert any(c["id"] == "cmd-remboursements" for c in lst)
