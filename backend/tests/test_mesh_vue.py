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
    """À tout zoom, ce sont toujours de VRAIS jumeaux (jamais une grappe qui en tient lieu) — juste bornés."""
    r = p100k.vue(*fenetre(zoom), zoom)
    assert len(r["jumeaux"]) <= pyramide.MAX_JUMEAUX
    assert len(r["liens"]) <= pyramide.MAX_LIENS_JUMEAUX
    assert r["n_total"] == p100k.n
    assert all({"i", "x", "y", "dom", "degre", "ecart", "alerte"} <= j.keys() for j in r["jumeaux"])


def test_la_taille_de_la_reponse_reste_bornee_par_une_constante_quel_que_soit_n():
    """La réponse ne grandit jamais avec n : elle reste sous un plafond FIXE, que le Mesh ait 20 000 ou 400 000
    jumeaux. Un petit Mesh peut légitimement montrer PLUS de détail réel (ses points tiennent dans le budget) —
    ce n'est pas un défaut : mieux vaut de vrais points qu'une bulle, dès que c'est possible."""
    plafond = pyramide.MAX_JUMEAUX + pyramide.MAX_LIENS_JUMEAUX
    for taille in (20_000, 400_000):
        p = pyramide.synthetique(taille)
        for z in (0.03, 0.2, 0.9):
            r = p.vue(*fenetre(z, 9000, 9000), z)
            assert len(r["jumeaux"]) + len(r["liens"]) <= plafond


def test_zoom_proche_donne_des_jumeaux_avec_leurs_liens(p100k):
    r = p100k.vue(*fenetre(1.5), 1.5)
    assert r["mode"] == "jumeaux"
    if r["jumeaux"]:
        ids = {j["i"] for j in r["jumeaux"]}
        assert all(l["source"] in ids and l["cible"] in ids for l in r["liens"])


def test_dezoome_montre_les_jumeaux_les_mieux_connectes_dabord(p100k):
    """Fenêtre bien plus dense que le budget : la sélection privilégie le DEGRÉ — jamais un tirage arbitraire —
    et porte quand même les signaux réels (écarts) puisque ce sont de vrais jumeaux, pas une forme qui les tait."""
    r = p100k.vue(*fenetre(0.02, 20000, 20000, 1400), 0.02)
    assert r["mode"] == "jumeaux" and len(r["jumeaux"]) == pyramide.MAX_JUMEAUX  # fenêtre bien plus dense que le budget
    degres = [j["degre"] for j in r["jumeaux"]]
    assert min(degres) >= np.median(p100k.degre)  # la sélection ne pioche pas au hasard : elle privilégie les mieux connectés
    assert any(j["ecart"] for j in r["jumeaux"])


def test_zoomer_ne_fait_jamais_disparaitre_un_jumeau_deja_montre(p100k):
    """Le maillage se REMPLIT en zoomant, il ne « saute » jamais d'un rendu à l'autre : tout jumeau montré dans une
    fenêtre large reste montré dans une fenêtre plus étroite qui le contient encore (même budget)."""
    large = p100k.vue(*fenetre(0.02, 20000, 20000, 1400), 0.02)
    x0, y0, x1, y1 = fenetre(0.05, 20000, 20000, 1400)  # sous-fenêtre, plus proche, toujours centrée pareil
    etroite = p100k.vue(x0, y0, x1, y1, 0.05)
    dedans = {j["i"]: j for j in large["jumeaux"] if x0 <= j["x"] <= x1 and y0 <= j["y"] <= y1}
    montres = {j["i"] for j in etroite["jumeaux"]}
    assert dedans and set(dedans) <= montres


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
    assert len(d["jumeaux"]) <= pyramide.MAX_JUMEAUX


def test_endpoint_refuse_une_fenetre_vide_et_un_zoom_nul(api):
    assert _vue(api, x1=-5000).status_code == 422
    assert _vue(api, zoom=0).status_code == 422
