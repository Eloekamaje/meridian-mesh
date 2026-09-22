"""Passage à l'échelle avec des CENTAINES de domaines : palette groupée par famille, disposition organique
(pas une grille), chaque domaine peuplé, et les deux points d'entrée du laboratoire (détail d'un jumeau, recherche)."""
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyramide  # noqa: E402

BASE = os.environ.get("MERIDIAN_API", "http://localhost:8001").rstrip("/") + "/api"
H = {"X-Persona": "architecte"}


@pytest.fixture(scope="module")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("backend non lancé")
    return requests.Session()


# ---- palette : groupée par famille, déterministe, ne dépend que de D ------------------------------------
def test_palette_distingue_des_centaines_de_domaines():
    couleurs, fam = pyramide.palette_domaines(300)
    assert len(couleurs) == len(fam) == 300
    assert len(set(couleurs)) == 300  # aucune collision
    assert all(c.startswith("#") and len(c) == 7 for c in couleurs)
    nfam = len(set(fam))
    assert 16 <= nfam <= 18  # ≈ √300


def test_palette_est_pure_et_stable():
    a, fa = pyramide.palette_domaines(150)
    b, fb = pyramide.palette_domaines(150)
    assert a == b and fa == fb  # aucune graine : la palette d'un compte de domaines donné est toujours la même


def test_palette_vide():
    assert pyramide.palette_domaines(0) == ([], [])


# ---- disposition organique des domaines : pas une grille -------------------------------------------------
def test_disposition_domaines_est_deterministe_et_sans_chevauchement():
    fam = np.array([i % 6 for i in range(40)], dtype=np.int32)
    rayon = np.full(40, 300.0)
    ax1, ay1 = pyramide._disposer_domaines(fam, rayon)
    ax2, ay2 = pyramide._disposer_domaines(fam, rayon)
    assert np.array_equal(ax1, ax2) and np.array_equal(ay1, ay2)  # aucune graine : purement déterministe
    d = np.sqrt((ax1[:, None] - ax1[None, :]) ** 2 + (ay1[:, None] - ay1[None, :]) ** 2)
    np.fill_diagonal(d, np.inf)
    assert d.min() >= (rayon[:, None] + rayon[None, :]).min() * 0.8  # jamais deux domaines l'un sur l'autre


def test_domaines_de_meme_famille_sont_plus_proches_en_moyenne():
    # deux familles bien séparées : la distance moyenne intra-famille doit être nettement plus petite que inter-familles
    fam = np.array([0] * 15 + [1] * 15, dtype=np.int32)
    rayon = np.full(30, 250.0)
    ax, ay = pyramide._disposer_domaines(fam, rayon)
    pos = np.stack([ax, ay], axis=1)
    d = np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1))
    meme = fam[:, None] == fam[None, :]
    np.fill_diagonal(meme, False)
    intra = d[meme].mean()
    inter = d[~meme].mean()
    assert intra < inter


def test_un_seul_domaine_ne_plante_pas():
    ax, ay = pyramide._disposer_domaines(np.zeros(1, dtype=np.int32), np.array([5.0]))
    assert ax.shape == (1,) and ay.shape == (1,)
    ax0, ay0 = pyramide._disposer_domaines(np.zeros(0, dtype=np.int32), np.zeros(0))
    assert ax0.shape == (0,) and ay0.shape == (0,)


# ---- le jeu synthétique à l'échelle : chaque domaine peuplé, la palette embarquée ------------------------
def test_aucun_domaine_ne_domine_l_amas_a_des_centaines():
    """Sans plafond, une loi de puissance peut donner un seul astre géant et de la poussière — plus une
    galaxie de domaines distincts (l'effet recherché, comme graph.html). Vérifié à plusieurs graines."""
    for graine in (1, 2, 3):
        p = pyramide.synthetique(200_000, graine, 200)
        part_max = int(p.niv[3].taille.max()) / p.n
        assert part_max < 0.05, f"graine {graine} : un domaine concentre {part_max:.1%} du Mesh"


def test_les_territoires_des_domaines_ne_se_chevauchent_quasiment_jamais():
    """Le rayon territorial d'un domaine (celui qu'occupent ses communautés) ne doit pas déborder sur son
    voisin — sans quoi deux domaines se fondent visuellement en un seul amas, même à des centaines."""
    p = pyramide.synthetique(200_000, 1, 300)
    v = p.niv[3]
    d = np.sqrt((v.x[:, None] - v.x[None, :]) ** 2 + (v.y[:, None] - v.y[None, :]) ** 2)
    np.fill_diagonal(d, np.inf)
    besoin = v.r[:, None] + v.r[None, :]
    chevauche = d < besoin * 0.85
    np.fill_diagonal(chevauche, False)
    part = int(chevauche.sum()) / 2 / (len(v.r) * (len(v.r) - 1) / 2)
    assert part < 0.01


def test_aucun_domaine_a_zero_jumeau_meme_a_des_centaines():
    p = pyramide.synthetique(150_000, 1, 400)
    assert int((p.niv[3].taille == 0).sum()) == 0
    assert p.niv[3].taille.sum() == p.n


def test_le_jeu_porte_sa_palette():
    p = pyramide.synthetique(20_000, 5, 60)
    assert len(p.couleurs_domaines) == 60 and len(p.familles_domaines) == 60
    assert len(set(p.couleurs_domaines)) == 60


def test_meme_domaines_meme_palette_quelle_que_soit_la_graine():
    a = pyramide.synthetique(5_000, 1, 40)
    b = pyramide.synthetique(5_000, 99, 40)
    assert a.couleurs_domaines == b.couleurs_domaines  # la palette dépend du COMPTE de domaines, pas de la graine


# ---- endpoints du laboratoire ------------------------------------------------------------------------------
def _vue(api, **kw):
    p = {"x0": -40000, "y0": -40000, "x1": 40000, "y1": 40000, "zoom": 0.02, **kw}
    return api.get(f"{BASE}/mesh/vue", params=p, headers=H)


def test_la_vue_porte_couleurs_et_effectifs_par_domaine(api):
    r = _vue(api, synthetique=150_000, domaines=200)
    assert r.status_code == 200
    d = r.json()
    assert len(d["domaines"]) == len(d["domaines_couleur"]) == len(d["domaines_famille"]) == len(d["domaines_taille"]) == 200
    assert sum(d["domaines_taille"]) == 150_000
    assert all(t > 0 for t in d["domaines_taille"])


def test_detail_d_un_jumeau_a_la_forme_d_un_jumeau_reel(api):
    r = api.get(f"{BASE}/mesh/vue/jumeau", params={"i": 12, "synthetique": 80_000, "domaines": 90}, headers=H)
    assert r.status_code == 200
    d = r.json()
    for champ in ("id", "nom", "domaine", "mission", "proprietaire", "statut", "autonomie", "couverture", "fraicheur", "capacites", "sources_detail", "degre"):
        assert champ in d
    assert d["domaine"] in [f"Domaine {i + 1}" for i in range(90)]
    assert 0 <= d["couverture"] <= 100


def test_detail_d_un_jumeau_est_stable_et_hors_bornes_refuse(api):
    a = api.get(f"{BASE}/mesh/vue/jumeau", params={"i": 5, "synthetique": 10_000, "domaines": 20}, headers=H).json()
    b = api.get(f"{BASE}/mesh/vue/jumeau", params={"i": 5, "synthetique": 10_000, "domaines": 20}, headers=H).json()
    assert a == b
    assert api.get(f"{BASE}/mesh/vue/jumeau", params={"i": 999_999, "synthetique": 10_000, "domaines": 20}, headers=H).status_code == 404


def test_localiser_un_jumeau_par_son_numero_et_un_domaine_par_son_nom(api):
    j = api.get(f"{BASE}/mesh/vue/localiser", params={"q": "7", "synthetique": 50_000, "domaines": 40}, headers=H).json()
    assert j["type"] == "jumeau" and j["i"] == 7
    d = api.get(f"{BASE}/mesh/vue/localiser", params={"q": "Domaine 3", "synthetique": 50_000, "domaines": 40}, headers=H).json()
    assert d["type"] == "domaine" and d["nom"] == "Domaine 3" and d["n"] > 0
    assert api.get(f"{BASE}/mesh/vue/localiser", params={"q": "Atlantide", "synthetique": 50_000, "domaines": 40}, headers=H).status_code == 404
    assert api.get(f"{BASE}/mesh/vue/localiser", params={"q": "999999999", "synthetique": 50_000, "domaines": 40}, headers=H).status_code == 404


def test_localiser_les_memes_coordonnees_que_le_rendu(api):
    """Le point trouvé par la recherche doit être celui que la vue dessine réellement à cette position."""
    loc = api.get(f"{BASE}/mesh/vue/localiser", params={"q": "3", "synthetique": 30_000, "domaines": 25}, headers=H).json()
    r = _vue(api, synthetique=30_000, domaines=25, zoom=1.5, x0=loc["x"] - 200, y0=loc["y"] - 200, x1=loc["x"] + 200, y1=loc["y"] + 200)
    assert any(j["i"] == 3 for j in r.json()["jumeaux"])
