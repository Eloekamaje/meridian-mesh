"""Iteration 20 — Notifications + trigger 'à revoir' + responsable notifs."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mesh-insights.preview.emergentagent.com").rstrip("/")


def _session(persona="architecte"):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Persona": persona})
    return s


@pytest.fixture(scope="module")
def arch():
    return _session("architecte")


@pytest.fixture(scope="module")
def paiements():
    return _session("paiements")


@pytest.fixture(scope="module")
def support():
    return _session("support")


@pytest.fixture(scope="module", autouse=True)
def reset_at_end(arch):
    # Ensure clean seed at start too, in case a previous run left state
    arch.post(f"{BASE_URL}/api/demo/reinitialiser")
    yield
    arch.post(f"{BASE_URL}/api/demo/reinitialiser")


# ---------- Notifications endpoints ----------

def test_lister_notifications_architecte(arch):
    r = arch.get(f"{BASE_URL}/api/notifications")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "notifications" in d and "non_lues" in d
    # 2 seed notifs for architecte, both non-lues
    assert d["non_lues"] >= 2, f"expected 2+ non-lues, got {d['non_lues']}: {d}"
    ids = {n["id"] for n in d["notifications"]}
    assert {"notif-1", "notif-2"}.issubset(ids)


def test_lister_notifications_paiements(paiements):
    r = paiements.get(f"{BASE_URL}/api/notifications")
    assert r.status_code == 200
    d = r.json()
    ids = {n["id"] for n in d["notifications"]}
    assert "notif-3" in ids


def test_marquer_notif_lue(arch):
    r = arch.post(f"{BASE_URL}/api/notifications/notif-1/lue")
    assert r.status_code == 200
    d = arch.get(f"{BASE_URL}/api/notifications").json()
    n1 = next(n for n in d["notifications"] if n["id"] == "notif-1")
    assert n1["lu"] is True


def test_notifications_tout_lire(arch):
    r = arch.post(f"{BASE_URL}/api/notifications/tout-lire")
    assert r.status_code == 200
    d = arch.get(f"{BASE_URL}/api/notifications").json()
    assert d["non_lues"] == 0


# ---------- Trigger 'à revoir' via confirmation de relation ----------

def test_confirmer_relation_r6_marque_case_a_revoir(arch, paiements):
    # Confirm r6 (paiements -> support)
    r = arch.post(f"{BASE_URL}/api/relations/r6/confirmer")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("etat") == "confirmee"

    # case-olympiade should now be a_revoir=True + historique
    r2 = arch.get(f"{BASE_URL}/api/cases/case-olympiade")
    assert r2.status_code == 200
    case = r2.json()
    assert case.get("a_revoir") is True
    textes = [h["texte"] for h in case.get("historique", [])]
    assert any("À revoir" in t and "paiements" in t and "support" in t for t in textes), textes

    # A notification a_revoir should be present for paiements (participant)
    notifs = paiements.get(f"{BASE_URL}/api/notifications").json()["notifications"]
    a_revoir_notifs = [n for n in notifs if n.get("type") == "a_revoir"]
    assert any("case-olympiade" in (n.get("lien") or "") for n in a_revoir_notifs), a_revoir_notifs


def test_patch_a_revoir_false_ajoute_historique(arch):
    r = arch.patch(f"{BASE_URL}/api/cases/case-olympiade", json={"a_revoir": False})
    assert r.status_code == 200, r.text
    case = r.json()
    assert case.get("a_revoir") is False
    textes = [h["texte"] for h in case.get("historique", [])]
    assert any("Revue effectuée" in t for t in textes), textes


# ---------- Responsable + notification d'assignation ----------

def test_creer_case_avec_responsable_notifie(arch, support):
    payload = {"titre": "TEST_assignation_support", "type": "demande",
               "jumeaux": ["support"], "responsable": "support"}
    r = arch.post(f"{BASE_URL}/api/cases", json=payload)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["responsable"] == "support"
    assert "support" in d["participants"]
    # Notification d'assignation créée pour support
    notifs = support.get(f"{BASE_URL}/api/notifications").json()["notifications"]
    assert any(n.get("type") == "assignation" and d["id"] in (n.get("lien") or "")
               for n in notifs), notifs


def test_patch_responsable_notifie_le_nouveau(arch, paiements):
    # Create case with architecte as responsable
    r = arch.post(f"{BASE_URL}/api/cases", json={"titre": "TEST_reassign", "jumeaux": ["paiements"]})
    cid = r.json()["id"]
    # Reassign to paiements
    r2 = arch.patch(f"{BASE_URL}/api/cases/{cid}", json={"responsable": "paiements"})
    assert r2.status_code == 200
    assert r2.json()["responsable"] == "paiements"
    # paiements should have received an assignation notif for this case
    notifs = paiements.get(f"{BASE_URL}/api/notifications").json()["notifications"]
    assert any(n.get("type") == "assignation" and cid in (n.get("lien") or "")
               for n in notifs), [n for n in notifs if n.get("type") == "assignation"]
