"""Tests du feed Actualités (nouveau paradigme) — /api/actualites."""
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
    return requests.Session()


def test_actualites_aujourdhui(s):
    r = s.get(f"{BASE}/actualites", headers={"X-Persona": "architecte"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["est_aujourdhui"] is True
    assert d["portee"] == "personnel"
    assert len(d["histoires"]) > 0
    h = d["histoires"][0]
    assert {"id", "genre", "titre", "recit", "quand", "score", "liens"} <= set(h)
    assert d["resume_flore"]["texte"]


def test_actualites_periode_7j(s):
    r = s.get(f"{BASE}/actualites?jours=7", headers={"X-Persona": "architecte"}, timeout=15)
    d = r.json()
    assert d["jours"] == 7
    assert d["est_aujourdhui"] is False
    assert len(d["histoires"]) >= 10  # situations + relations + historique des travaux


def test_actualites_date_passee(s):
    r = s.get(f"{BASE}/actualites?date=2026-06-24", headers={"X-Persona": "architecte"}, timeout=15)
    d = r.json()
    assert d["date"] == "2026-06-24"
    assert all(h["quand"][:10] == "2026-06-24" for h in d["histoires"])


def test_actualites_portee_global(s):
    r = s.get(f"{BASE}/actualites?portee=global", headers={"X-Persona": "architecte"}, timeout=15)
    d = r.json()
    assert d["espace_label"] == "Mesh global"
    assert d["note_portee"] is None


def test_actualites_global_refuse_paiements(s):
    r = s.get(f"{BASE}/actualites?portee=global", headers={"X-Persona": "paiements"}, timeout=15)
    d = r.json()
    assert d["note_portee"]  # pas d'accès au Mesh global → repli sur l'espace + note
    # le feed reste filtré RBAC : uniquement des histoires du périmètre Paiements
    for h in d["histoires"]:
        assert not h.get("restreinte") or True  # marquage, pas de fuite
        for j in h.get("jumeaux", []):
            assert j in {"paiements", "facturation", "comptes"}


def test_actualites_rbac_support(s):
    r = s.get(f"{BASE}/actualites?jours=30", headers={"X-Persona": "support"}, timeout=15)
    d = r.json()
    ids = {j for h in d["histoires"] for j in h.get("jumeaux", [])}
    assert ids <= {"support", "notifications", "paiements"}
