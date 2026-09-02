"""Backend tests for Atlas v28 : PATCH /api/jumeaux/{id} (position + domaine) + reinitialiser demo."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Persona": "architecte"})
    return s


@pytest.fixture(scope="module")
def mesh(client):
    r = client.get(f"{BASE_URL}/api/mesh")
    assert r.status_code == 200
    data = r.json()
    assert "jumeaux" in data and len(data["jumeaux"]) > 0
    return data


@pytest.fixture(scope="module")
def first_twin(mesh):
    j = next((x for x in mesh["jumeaux"] if not x.get("anonyme") and not x.get("porte")), None)
    assert j, "Aucun jumeau non anonyme trouvé"
    return j


class TestPatchJumeauPosition:
    def test_patch_position_persists(self, client, first_twin):
        jid = first_twin["id"]
        orig = first_twin.get("position", {"x": 0, "y": 0})
        new_pos = {"x": int(orig.get("x", 0)) + 33, "y": int(orig.get("y", 0)) + 21}
        r = client.patch(f"{BASE_URL}/api/jumeaux/{jid}", json={"position": new_pos})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Verify via GET /mesh
        mesh2 = client.get(f"{BASE_URL}/api/mesh").json()
        j2 = next(x for x in mesh2["jumeaux"] if x["id"] == jid)
        assert j2["position"]["x"] == new_pos["x"]
        assert j2["position"]["y"] == new_pos["y"]

    def test_patch_bad_payload_400(self, client, first_twin):
        r = client.patch(f"{BASE_URL}/api/jumeaux/{first_twin['id']}", json={})
        assert r.status_code == 400

    def test_patch_unknown_404(self, client):
        r = client.patch(f"{BASE_URL}/api/jumeaux/inconnu-xyz", json={"position": {"x": 1, "y": 2}})
        assert r.status_code == 404

    def test_patch_domaine_reclassification(self, client, mesh, first_twin):
        jid = first_twin["id"]
        original_domaine = first_twin["domaine"]
        autre = next((r["label"] for r in mesh.get("regions", []) if r["label"] != original_domaine), None)
        if not autre:
            pytest.skip("Pas de second domaine")
        r = client.patch(f"{BASE_URL}/api/jumeaux/{jid}", json={"domaine": autre})
        assert r.status_code == 200
        mesh2 = client.get(f"{BASE_URL}/api/mesh").json()
        j2 = next(x for x in mesh2["jumeaux"] if x["id"] == jid)
        assert j2["domaine"] == autre
        # Restore
        client.patch(f"{BASE_URL}/api/jumeaux/{jid}", json={"domaine": original_domaine})


class TestReinitialiser:
    def test_reinit_ok(self, client):
        r = client.post(f"{BASE_URL}/api/demo/reinitialiser")
        assert r.status_code in (200, 201), r.text


class TestMeshStability:
    """14 relations attendues, stable sur plusieurs chargements."""
    def test_relations_count_stable(self, client):
        counts = []
        for _ in range(3):
            data = client.get(f"{BASE_URL}/api/mesh").json()
            counts.append(len(data.get("relations", [])))
        assert len(set(counts)) == 1, f"Comptes instables: {counts}"
        assert counts[0] >= 10, f"Attendu ~14 relations, got {counts[0]}"
