"""Vue bornée du Mesh : pyramide (unitaire, sans serveur) et /api/mesh/vue (contre le backend lancé)."""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyramide  # noqa: E402

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"


@pytest.fixture(scope="module")
def p100k():
    return pyramide.synthetique(100_000)


def fenetre(zoom, cx=20000.0, cy=20000.0, l=1400.0, h=900.0):
    return cx - l / zoom / 2, cy - h / zoom / 2, cx + l / zoom / 2, cy + h / zoom / 2


# ---- unitaire -----------------------------------------------------------------------------------

def test_hierarchie_conserve_les_effectifs(p100k):
    for niv in (1, 2, 3):
        assert int(p100k.niv[niv].taille.sum()) == p100k.n


@pytest.mark.parametrize("zoom", [0.02, 0.06, 0.2, 0.6, 1.5, 6])
def test_reponse_bornee_quel_que_soit_n(p100k, zoom):
    r = p100k.vue(*fenetre(zoom), zoom)
    assert len(r["grappes"]) <= pyramide.MAX_GRAPPES
    assert len(r["jumeaux"]) <= pyramide.MAX_JUMEAUX
    assert len(r["liens"]) <= max(pyramide.MAX_LIENS_JUMEAUX, pyramide.MAX_LIENS_GRAPPES)
    assert r["n_total"] == p100k.n


def test_la_taille_de_la_reponse_ne_grandit_pas_avec_n():
    petit, grand = pyramide.synthetique(20_000), pyramide.synthetique(400_000)
    for z in (0.03, 0.2, 0.9):
        a, b = petit.vue(*fenetre(z, 9000, 9000), z), grand.vue(*fenetre(z, 9000, 9000), z)
        n = lambda r: len(r["grappes"]) + len(r["jumeaux"]) + len(r["liens"]) + len(r.get("points", {}).get("i", []))
        assert n(b) <= pyramide.MAX_GRAPPES + pyramide.MAX_JUMEAUX + pyramide.MAX_LIENS_JUMEAUX + pyramide.MAX_POINTS
        assert n(a) <= n(b) + 2 * pyramide.MAX_GRAPPES


def test_niveau_monotone_avec_le_zoom(p100k):
    niv = [p100k.niveau_pour(z) for z in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4)]
    assert niv == sorted(niv, reverse=True)


def test_zoom_proche_donne_des_jumeaux_avec_leurs_liens(p100k):
    r = p100k.vue(*fenetre(1.5), 1.5)
    assert r["mode"] == "jumeaux"
    if r["jumeaux"]:
        ids = {j["i"] for j in r["jumeaux"]}
        assert all(l["source"] in ids and l["cible"] in ids for l in r["liens"])


def test_les_grappes_portent_leurs_signaux(p100k):
    r = p100k.vue(*fenetre(0.02, 20000, 20000, 1400), 0.02)
    assert r["mode"] == "grappes"
    assert any(g["ecarts"] > 0 for g in r["grappes"])
    assert all(g["nom"] for g in r["grappes"])


def test_deterministe():
    a = pyramide.synthetique(5000, 3).vue(0, 0, 40000, 40000, 0.02)
    b = pyramide.synthetique(5000, 3).vue(0, 0, 40000, 40000, 0.02)
    a.pop("duree_ms"), b.pop("duree_ms")
    assert a == b


def test_million_de_jumeaux_construit_et_repond_vite():
    t = time.perf_counter()
    p = pyramide.synthetique(1_000_000)
    assert time.perf_counter() - t < 10
    for z in (0.02, 0.2, 1.0):
        t = time.perf_counter()
        p.vue(*fenetre(z, 30000, 30000), z)
        assert time.perf_counter() - t < 0.25


def test_jeu_vide():
    p = pyramide.Pyramide([], [], [], [], [], [])
    assert p.vue(0, 0, 10, 10, 1.0)["mode"] == "vide"


def test_depuis_mesh_ecarte_les_liens_vers_des_jumeaux_non_autorises():
    js = [{"id": "a", "domaine": "X", "position": {"x": 0, "y": 0}}, {"id": "b", "domaine": "X", "position": {"x": 50, "y": 0}}]
    rels = [{"source": "a", "cible": "b", "etat": "confirmee"}, {"source": "a", "cible": "secret", "etat": "confirmee"}]
    p = pyramide.depuis_mesh(js, rels)
    assert p.n == 2 and p.m == 1
    assert p.vue(-100, -100, 100, 100, 2.0)["n_total"] == 2


# ---- endpoint --------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


def _vue(api, persona="architecte", **kw):
    q = {"x0": -5000, "y0": -5000, "x1": 9000, "y1": 9000, "zoom": 0.9, **kw}
    return api.get(f"{BASE}/mesh/vue", params=q, headers={"X-Persona": persona}, timeout=20)


def test_endpoint_respecte_les_perimetres(api):
    for persona in ("architecte", "paiements", "support"):
        mesh = api.get(f"{BASE}/mesh", headers={"X-Persona": persona}, timeout=10).json()
        v = _vue(api, persona).json()
        assert v["n_total"] == mesh["perimetre"]["nb_autorises"]
        ids_autorises = {j["id"] for j in mesh["jumeaux"] if not j.get("anonyme")}
        assert {j["id"] for j in v["jumeaux"]} <= ids_autorises


def test_endpoint_synthetique_borne(api):
    r = _vue(api, zoom=0.03, synthetique=300_000, x0=0, y0=0, x1=40000, y1=40000)
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "synthetique" and d["n_total"] == 300_000
    assert len(d["grappes"]) <= pyramide.MAX_GRAPPES


def test_endpoint_refuse_une_fenetre_vide_et_un_zoom_nul(api):
    assert _vue(api, x1=-5000).status_code == 422
    assert _vue(api, zoom=0).status_code == 422
