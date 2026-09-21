"""Pyramide de regroupements du Mesh — passage à l'échelle côté serveur.

Le navigateur ne doit jamais charger le graphe entier : il demande une VUE (fenêtre monde + zoom) et le
serveur répond avec un nombre borné d'éléments, quel que soit le nombre total de jumeaux :

    zoom faible   → grappes de domaines / de groupes / de communautés (avec leurs signaux) ;
    zoom moyen    → communautés et jumeaux en points ;
    zoom élevé    → jumeaux individuels et leurs vrais liens.

Hiérarchie : domaine → groupe → communauté → jumeau. Chaque grappe est nommée, a une étendue (rayon) et
PORTE SES SIGNAUX (jumeaux en écart déclaré ≠ calculé, jumeaux en situation active).

Tout est vectorisé (numpy) : index en grille (jumeaux et liens rangés par cellule), agrégats par
`bincount`. Le module ne dépend ni de FastAPI ni de Mongo : il prend des tableaux et se teste seul.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

RAYON_LISIBLE = 11.0  # rayon écran (px) minimal d'une grappe « typique » pour l'afficher
ZOOM_POINTS = 0.1  # à partir d'ici : jumeaux en points (si leur nombre reste raisonnable)
ZOOM_JUMEAUX = 0.45  # à partir d'ici : jumeaux individuels
CELLULE = 256.0  # taille (monde) des cellules de la grille fine
MAX_POINTS = 9000
MAX_JUMEAUX = 700
MAX_LIENS_JUMEAUX = 4000
MAX_GRAPPES = 700
MAX_LIENS_GRAPPES = 240
ECHANTILLON_LIENS = 20000


# ---------------------------------------------------------------------------------------------
# Communautés (Louvain) pour les jeux de taille modeste — les très gros jeux fournissent les leurs.
def louvain(n: int, ea: np.ndarray, eb: np.ndarray, niveaux_max: int = 10) -> np.ndarray:
    """Communautés par optimisation gloutonne de la modularité (graphe non orienté). Retourne un
    tableau de numéros de communauté (0 = la plus grosse). Déterministe."""
    adj: list[dict[int, float]] = [dict() for _ in range(n)]
    m2 = 0.0
    for a, b in zip(ea.tolist(), eb.tolist()):
        if a == b:
            continue
        adj[a][b] = adj[a].get(b, 0.0) + 1.0
        adj[b][a] = adj[b].get(a, 0.0) + 1.0
        m2 += 2.0
    if m2 == 0:
        return np.zeros(n, dtype=np.int32)
    membres: list[list[int]] = [[i] for i in range(n)]
    g = adj
    boucle = [0.0] * n
    for _ in range(niveaux_max):
        N = len(g)
        k = [sum(nb.values()) + boucle[i] for i, nb in enumerate(g)]
        com = list(range(N))
        tot = list(k)
        ameliore = False
        passe = True
        while passe:
            passe = False
            for i in range(N):
                ci = com[i]
                vers: dict[int, float] = {}
                for j, w in g[i].items():
                    vers[com[j]] = vers.get(com[j], 0.0) + w
                tot[ci] -= k[i]
                meilleure = ci
                gain_max = vers.get(ci, 0.0) - tot[ci] * k[i] / m2
                for c in sorted(vers):
                    gain = vers[c] - tot[c] * k[i] / m2
                    if gain > gain_max + 1e-12:
                        gain_max, meilleure = gain, c
                tot[meilleure] += k[i]
                if meilleure != ci:
                    com[i] = meilleure
                    passe = ameliore = True
        if not ameliore:
            break
        renum: dict[int, int] = {}
        for c in com:
            renum.setdefault(c, len(renum))
        M = len(renum)
        nm: list[list[int]] = [[] for _ in range(M)]
        ng: list[dict[int, float]] = [dict() for _ in range(M)]
        nb = [0.0] * M
        for i in range(N):
            ci = renum[com[i]]
            nm[ci].extend(membres[i])
            nb[ci] += boucle[i]
            for j, w in g[i].items():
                cj = renum[com[j]]
                if ci == cj:
                    nb[ci] += w
                else:
                    ng[ci][cj] = ng[ci].get(cj, 0.0) + w
        membres, g, boucle = nm, ng, nb
        if M == N:
            break
    out = np.zeros(n, dtype=np.int32)
    ordre = sorted(range(len(membres)), key=lambda i: (-len(membres[i]), min(membres[i]) if membres[i] else 0))
    for num, i in enumerate(ordre):
        out[membres[i]] = num
    return out


@dataclass
class Niveau:
    """Un niveau de grappes (1 communauté, 2 groupe, 3 domaine)."""

    nom: str
    x: np.ndarray
    y: np.ndarray
    r: np.ndarray
    taille: np.ndarray
    dom: np.ndarray
    ecarts: np.ndarray
    alertes: np.ndarray
    rang: np.ndarray  # numéro d'ordre lisible (dans son domaine / son groupe)
    r_med: float = 1.0


class Pyramide:
    """Index d'un jeu de jumeaux. Les tableaux d'entrée sont alignés par jumeau (indice 0..n-1)."""

    def __init__(self, x, y, dom, com, ea, eb, etat=None, ecart=None, alerte=None, noms_domaines=None, ids=None):
        t0 = time.perf_counter()
        self.x = np.asarray(x, dtype=np.float32)
        self.y = np.asarray(y, dtype=np.float32)
        self.n = int(self.x.shape[0])
        self.dom = np.asarray(dom, dtype=np.int16)
        self.ea = np.asarray(ea, dtype=np.int32)
        self.eb = np.asarray(eb, dtype=np.int32)
        self.m = int(self.ea.shape[0])
        self.etat = np.zeros(self.m, dtype=np.uint8) if etat is None else np.asarray(etat, dtype=np.uint8)
        self.D = int(self.dom.max()) + 1 if self.n else 0
        self.noms_domaines = list(noms_domaines) if noms_domaines is not None else [f"Domaine {i + 1}" for i in range(self.D)]
        self.ids = ids  # liste optionnelle d'identifiants (pour le vrai Mesh)
        _, self.com = np.unique(np.asarray(com), return_inverse=True)
        self.com = self.com.astype(np.int32)
        self.C = int(self.com.max()) + 1 if self.n else 0
        if self.n:
            self._niveaux(ecart, alerte)
        self._grilles()
        self.degre = (np.bincount(self.ea, minlength=self.n) + np.bincount(self.eb, minlength=self.n)).astype(np.int32)
        self.duree_construction_ms = (time.perf_counter() - t0) * 1000

    # ---- construction --------------------------------------------------------------------------
    def _niveaux(self, ecart, alerte):
        n, C, D = self.n, self.C, self.D
        com = self.com
        taille_c = np.bincount(com, minlength=C).astype(np.int32)
        cx = np.bincount(com, weights=self.x, minlength=C) / np.maximum(taille_c, 1)
        cy = np.bincount(com, weights=self.y, minlength=C) / np.maximum(taille_c, 1)
        # Rayon = 2 × écart quadratique moyen (≈ 98 % des membres pour un nuage gaussien), pas le cercle englobant
        # maximal : celui-ci est piloté par les valeurs extrêmes et fait se recouvrir des grappes pourtant distinctes.
        dist2 = (self.x - cx[com]) ** 2 + (self.y - cy[com]) ** 2
        rms2_c = np.bincount(com, weights=dist2, minlength=C) / np.maximum(taille_c, 1)
        rc = 2.0 * np.sqrt(rms2_c) + 40.0
        hist = np.bincount(com.astype(np.int64) * D + self.dom, minlength=C * D).reshape(C, D)
        dom_c = hist.argmax(axis=1).astype(np.int16)
        # écart = déclaré ≠ calculé : le domaine du jumeau diffère du domaine dominant de sa communauté
        self.ecart = (self.dom != dom_c[com]).astype(np.uint8) if ecart is None else np.asarray(ecart, dtype=np.uint8)
        self.alerte = np.zeros(n, dtype=np.uint8) if alerte is None else np.asarray(alerte, dtype=np.uint8)
        ecarts_c = np.bincount(com, weights=self.ecart, minlength=C).astype(np.int32)
        alertes_c = np.bincount(com, weights=self.alerte, minlength=C).astype(np.int32)

        # groupes : communautés d'un même domaine rassemblées par cellule spatiale (~8 communautés chacun)
        pas_c = float(np.median(2 * rc)) if C else 1.0
        cell_g = max(pas_c * 3.2, 1.0)
        cle = np.stack([dom_c.astype(np.int64), np.floor(cx / cell_g).astype(np.int64), np.floor(cy / cell_g).astype(np.int64)], axis=1)
        _, gid = np.unique(cle, axis=0, return_inverse=True)
        gid = gid.reshape(-1).astype(np.int32)
        G = int(gid.max()) + 1 if C else 0
        taille_g = np.bincount(gid, weights=taille_c, minlength=G).astype(np.int32)
        gx = np.bincount(gid, weights=cx * taille_c, minlength=G) / np.maximum(taille_g, 1)
        gy = np.bincount(gid, weights=cy * taille_c, minlength=G) / np.maximum(taille_g, 1)
        rms2_g = np.bincount(gid, weights=((cx - gx[gid]) ** 2 + (cy - gy[gid]) ** 2 + rms2_c) * taille_c, minlength=G) / np.maximum(taille_g, 1)
        rg = 1.25 * np.sqrt(rms2_g) + 30.0
        dom_g = np.zeros(G, dtype=np.int16)
        dom_g[gid] = dom_c
        ecarts_g = np.bincount(gid, weights=ecarts_c, minlength=G).astype(np.int32)
        alertes_g = np.bincount(gid, weights=alertes_c, minlength=G).astype(np.int32)

        # domaines
        taille_d = np.bincount(dom_c, weights=taille_c, minlength=D).astype(np.int32)
        dx = np.bincount(dom_c, weights=cx * taille_c, minlength=D) / np.maximum(taille_d, 1)
        dy = np.bincount(dom_c, weights=cy * taille_c, minlength=D) / np.maximum(taille_d, 1)
        rms2_d = np.bincount(dom_c, weights=((cx - dx[dom_c]) ** 2 + (cy - dy[dom_c]) ** 2 + rms2_c) * taille_c, minlength=D) / np.maximum(taille_d, 1)
        rd = 1.25 * np.sqrt(rms2_d) + 40.0
        ecarts_d = np.bincount(dom_c, weights=ecarts_c, minlength=D).astype(np.int32)
        alertes_d = np.bincount(dom_c, weights=alertes_c, minlength=D).astype(np.int32)

        def rangs(parent, taille):
            """Rang de chaque élément parmi ceux de son parent (1, 2, 3…), dans l'ordre des indices."""
            ordre = np.argsort(parent, kind="stable")
            r = np.empty(len(parent), dtype=np.int32)
            p = parent[ordre]
            debut = np.searchsorted(p, p, side="left")
            r[ordre] = np.arange(len(parent)) - debut + 1
            return r

        self.gid = gid  # groupe de chaque communauté
        self.dom_c = dom_c
        self.niv = {
            1: Niveau("Communauté", cx.astype(np.float32), cy.astype(np.float32), rc.astype(np.float32), taille_c, dom_c, ecarts_c, alertes_c, rangs(gid, taille_c)),
            2: Niveau("Groupe", gx.astype(np.float32), gy.astype(np.float32), rg.astype(np.float32), taille_g, dom_g, ecarts_g, alertes_g, rangs(dom_g, taille_g)),
            3: Niveau("Domaine", dx.astype(np.float32), dy.astype(np.float32), rd.astype(np.float32), taille_d, np.arange(D, dtype=np.int16), ecarts_d, alertes_d, np.arange(1, D + 1, dtype=np.int32)),
        }
        for v in self.niv.values():
            actifs = v.taille > 0
            v.r_med = float(np.median(v.r[actifs])) if actifs.any() else 1.0
        self.dom_g = dom_g

    def _grilles(self):
        if self.n == 0:
            self.x0 = self.y0 = 0.0
            self.gw = self.gh = 1
            self.debut = np.zeros(2, dtype=np.int64)
            self.ordre = np.zeros(0, dtype=np.int64)
            self.edebut = np.zeros(2, dtype=np.int64)
            self.eordre = np.zeros(0, dtype=np.int64)
            return
        self.x0, self.y0 = float(self.x.min()), float(self.y.min())
        self.gw = int((self.x.max() - self.x0) // CELLULE) + 2
        self.gh = int((self.y.max() - self.y0) // CELLULE) + 2
        cell = ((self.y - self.y0) // CELLULE).astype(np.int64) * self.gw + ((self.x - self.x0) // CELLULE).astype(np.int64)
        self._cell = cell
        self.ordre = np.argsort(cell, kind="stable")
        self.debut = np.concatenate([[0], np.cumsum(np.bincount(cell, minlength=self.gw * self.gh))])
        ecell = cell[self.ea] if self.m else np.zeros(0, dtype=np.int64)
        self.eordre = np.argsort(ecell, kind="stable")
        self.edebut = np.concatenate([[0], np.cumsum(np.bincount(ecell, minlength=self.gw * self.gh))]) if self.m else np.zeros(self.gw * self.gh + 1, dtype=np.int64)

    # ---- requêtes -------------------------------------------------------------------------------
    def _lignes(self, debut, ordre, x0, y0, x1, y1):
        """Éléments (jumeaux ou liens) rangés dans les cellules qui coupent la fenêtre : une tranche par ligne."""
        cx0 = max(0, int((x0 - self.x0) // CELLULE))
        cx1 = min(self.gw - 1, int((x1 - self.x0) // CELLULE))
        cy0 = max(0, int((y0 - self.y0) // CELLULE))
        cy1 = min(self.gh - 1, int((y1 - self.y0) // CELLULE))
        if cx1 < cx0 or cy1 < cy0:
            return np.zeros(0, dtype=np.int64)
        tranches = [ordre[debut[cy * self.gw + cx0]: debut[cy * self.gw + cx1 + 1]] for cy in range(cy0, cy1 + 1)]
        return np.concatenate(tranches) if tranches else np.zeros(0, dtype=np.int64)

    def jumeaux_dans(self, x0, y0, x1, y1, maximum=None):
        idx = self._lignes(self.debut, self.ordre, x0, y0, x1, y1)
        if idx.size == 0:
            return idx
        k = (self.x[idx] >= x0) & (self.x[idx] <= x1) & (self.y[idx] >= y0) & (self.y[idx] <= y1)
        idx = idx[k]
        return idx[:maximum] if maximum else idx

    def niveau_pour(self, zoom: float) -> int:
        """Niveau de grappes (1..3) : le plus fin dont la grappe typique reste lisible ; 3 sinon."""
        for niv in (1, 2, 3):
            if self.niv[niv].r_med * zoom >= RAYON_LISIBLE:
                return niv
        return 3

    def grappes_dans(self, niv: int, x0, y0, x1, y1) -> np.ndarray:
        v = self.niv[niv]
        k = (v.taille > 0) & (v.x + v.r >= x0) & (v.x - v.r <= x1) & (v.y + v.r >= y0) & (v.y - v.r <= y1)
        return np.nonzero(k)[0]

    def _vers_niveau(self, niv: int) -> np.ndarray:
        """Grappe de niveau `niv` de chaque jumeau."""
        if niv == 1:
            return self.com
        if niv == 2:
            return self.gid[self.com]
        return self.dom_c[self.com].astype(np.int32)

    def liens_grappes(self, niv: int, ids: np.ndarray, x0, y0, x1, y1):
        """Liens agrégés entre grappes visibles, par échantillonnage spatial des liens de la zone."""
        if ids.size == 0 or self.m == 0:
            return []
        el = self._lignes(self.edebut, self.eordre, x0, y0, x1, y1)
        if el.size > ECHANTILLON_LIENS:
            el = el[:: int(np.ceil(el.size / ECHANTILLON_LIENS))]
        if el.size == 0:
            return []
        vers = self._vers_niveau(niv)
        a, b = vers[self.ea[el]], vers[self.eb[el]]
        pos = np.full(int(self.niv[niv].taille.shape[0]), -1, dtype=np.int32)
        pos[ids] = np.arange(ids.size, dtype=np.int32)
        pa, pb = pos[a], pos[b]
        k = (pa >= 0) & (pb >= 0) & (pa != pb)
        if not k.any():
            return []
        lo, hi = np.minimum(pa[k], pb[k]).astype(np.int64), np.maximum(pa[k], pb[k]).astype(np.int64)
        cles, nb = np.unique(lo * 1_000_000 + hi, return_counts=True)
        ordre = np.argsort(-nb)[:MAX_LIENS_GRAPPES]
        return [{"a": int(cles[i] // 1_000_000), "b": int(cles[i] % 1_000_000), "poids": int(nb[i])} for i in ordre]

    def nom_grappe(self, niv: int, i: int) -> str:
        v = self.niv[niv]
        d = self.noms_domaines[int(v.dom[i])]
        if niv == 3:
            return d
        if niv == 2:
            return f"{d} · groupe {int(v.rang[i])}"
        g = int(self.gid[i])
        return f"{d} · groupe {int(self.niv[2].rang[g])} · communauté {int(v.rang[i])}"

    # ---- réponse d'une vue --------------------------------------------------------------------------------
    def vue(self, x0: float, y0: float, x1: float, y1: float, zoom: float) -> dict:
        """Vue bornée d'une fenêtre monde à un zoom donné. Le nombre d'éléments renvoyés ne dépend pas de n."""
        t0 = time.perf_counter()
        if self.n == 0:
            return {"mode": "vide", "niveau": 0, "grappes": [], "jumeaux": [], "liens": [], "n_total": 0, "duree_ms": 0.0}
        rep: dict = {"n_total": self.n, "zoom": zoom}
        if zoom >= ZOOM_JUMEAUX:
            idx = self.jumeaux_dans(x0, y0, x1, y1, MAX_JUMEAUX)
            rep.update(self._jumeaux(idx, x0, y0, x1, y1))
        else:
            points = None
            if zoom >= ZOOM_POINTS:
                idx = self.jumeaux_dans(x0, y0, x1, y1, MAX_POINTS + 1)
                if idx.size <= MAX_POINTS:
                    points = idx
            if points is not None:
                ids = self.grappes_dans(1, x0, y0, x1, y1)
                rep.update({"mode": "points", "niveau": 1, "grappes": self._grappes(1, ids), "liens": [], "jumeaux": [],
                            "points": {"i": points.tolist(), "x": np.round(self.x[points], 1).tolist(), "y": np.round(self.y[points], 1).tolist(),
                                       "d": self.dom[points].tolist(), "e": self.ecart[points].tolist(), "a": self.alerte[points].tolist()}})
            else:
                niv = self.niveau_pour(zoom)
                ids = self.grappes_dans(niv, x0, y0, x1, y1)
                while ids.size > MAX_GRAPPES and niv < 3:  # trop dense à l'écran : on remonte d'un niveau
                    niv += 1
                    ids = self.grappes_dans(niv, x0, y0, x1, y1)
                enfant = self.niv[niv - 1].r_med * zoom if niv > 1 else 0.0
                fondu = float(np.clip((enfant - 7.0) / (RAYON_LISIBLE - 7.0), 0.0, 1.0)) if niv > 1 else 0.0
                rep.update({"mode": "grappes", "niveau": niv, "fondu": round(fondu, 3), "grappes": self._grappes(niv, ids),
                            "liens": self.liens_grappes(niv, ids, x0, y0, x1, y1), "jumeaux": []})
                if fondu > 0.02 and niv > 1:
                    enf = self.grappes_dans(niv - 1, x0, y0, x1, y1)
                    if enf.size <= 900:
                        rep["enfants"] = self._grappes(niv - 1, enf)
        rep["duree_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return rep

    def _grappes(self, niv: int, ids: np.ndarray) -> list:
        v = self.niv[niv]
        return [{"id": int(i), "niv": niv, "nom": self.nom_grappe(niv, int(i)), "x": round(float(v.x[i]), 1), "y": round(float(v.y[i]), 1),
                 "r": round(float(v.r[i]), 1), "n": int(v.taille[i]), "dom": int(v.dom[i]), "ecarts": int(v.ecarts[i]), "alertes": int(v.alertes[i])} for i in ids]

    def _jumeaux(self, idx: np.ndarray, x0, y0, x1, y1) -> dict:
        marque = np.zeros(self.n, dtype=bool)
        marque[idx] = True
        el = self._lignes(self.edebut, self.eordre, x0, y0, x1, y1)
        liens = []
        if el.size:
            k = marque[self.ea[el]] & marque[self.eb[el]]
            sel = el[k][:MAX_LIENS_JUMEAUX]
            liens = [{"source": int(a), "cible": int(b), "etat": int(e)} for a, b, e in zip(self.ea[sel], self.eb[sel], self.etat[sel])]
        jumeaux = [{"i": int(i), "x": round(float(self.x[i]), 1), "y": round(float(self.y[i]), 1), "dom": int(self.dom[i]), "com": int(self.com[i]),
                    "degre": int(self.degre[i]), "ecart": int(self.ecart[i]), "alerte": int(self.alerte[i]),
                    **({"id": self.ids[int(i)]} if self.ids is not None else {})} for i in idx]
        return {"mode": "jumeaux", "niveau": 0, "grappes": [], "jumeaux": jumeaux, "liens": liens}


# ---------------------------------------------------------------------------------------------
# Constructeurs

def depuis_mesh(jumeaux: list[dict], relations: list[dict], en_alerte=()) -> Pyramide:
    """Pyramide du VRAI Mesh. `jumeaux` doit déjà être filtré par les droits du demandeur : rien de ce qui n'est pas
    passé ici n'apparaît, ni comme jumeau, ni dans le décompte d'une grappe, ni dans un lien (deny-by-default).

    Communautés : Louvain sur les relations visibles. Écart : le jumeau touche une relation non confirmée ou contestée
    (déclaré ≠ observé). Alerte : jumeau en situation active ou de santé dégradée."""
    ids = [j["id"] for j in jumeaux]
    pos = {i: k for k, i in enumerate(ids)}
    domaines = sorted({j.get("domaine") or "Non classé" for j in jumeaux})
    dom_pos = {d: k for k, d in enumerate(domaines)}
    px = [float((j.get("position") or {}).get("x", 0)) for j in jumeaux]
    py = [float((j.get("position") or {}).get("y", 0)) for j in jumeaux]
    dom = [dom_pos[j.get("domaine") or "Non classé"] for j in jumeaux]
    ea, eb, etat = [], [], []
    ecart = np.zeros(len(jumeaux), dtype=np.uint8)
    for r in relations:
        a, b = pos.get(r["source"]), pos.get(r["cible"])
        if a is None or b is None:
            continue  # lien vers un jumeau non autorisé : écarté ici
        ea.append(a)
        eb.append(b)
        e = r.get("etat", "confirmee")
        etat.append({"confirmee": 0, "observee": 1}.get(e, 2))
        if e not in ("confirmee", "observee"):
            ecart[a] = ecart[b] = 1
    alerte = np.array([1 if (j["id"] in set(en_alerte) or j.get("sante") == "dégradé") else 0 for j in jumeaux], dtype=np.uint8)
    ea_a, eb_a = np.array(ea, dtype=np.int32), np.array(eb, dtype=np.int32)
    com = louvain(len(jumeaux), ea_a, eb_a) if jumeaux else np.zeros(0, dtype=np.int32)
    return Pyramide(px, py, dom, com, ea_a, eb_a, etat, ecart, alerte, noms_domaines=domaines, ids=ids)


def synthetique(n: int, graine: int = 1, domaines: int = 8) -> Pyramide:
    """Jeu synthétique de n jumeaux (essais d'échelle) : communautés gaussiennes, ~6 % d'écarts, liens surtout locaux."""
    rng = np.random.default_rng(graine)
    C = max(n // 60, 4)
    cote = 900.0 * np.sqrt(C)
    # chaque domaine occupe un territoire (case d'une grille) : ses communautés s'y répartissent
    gd = int(np.ceil(np.sqrt(domaines)))
    case = cote / gd
    dc = rng.integers(0, domaines, C)
    angle, rayon = rng.uniform(0, 2 * np.pi, C), 0.40 * case * np.sqrt(rng.uniform(0, 1, C))
    cx = (dc % gd + 0.5) * case + rayon * np.cos(angle)
    cy = (dc // gd + 0.5) * case + rayon * np.sin(angle)
    com = rng.integers(0, C, n)
    x, y = cx[com] + rng.normal(0, 90, n), cy[com] + rng.normal(0, 90, n)
    dom = np.where(rng.random(n) < 0.06, rng.integers(0, domaines, n), dc[com])
    m = n * 2
    ea = rng.integers(0, n, m)
    # 80 % des liens restent dans la communauté : on tire un voisin de même communauté via un tri par communauté
    ordre = np.argsort(com, kind="stable")
    rang = np.empty(n, dtype=np.int64)
    rang[ordre] = np.arange(n)
    voisin = ordre[np.clip(rang[ea] + rng.integers(-20, 21, m), 0, n - 1)]
    eb = np.where(rng.random(m) < 0.8, voisin, rng.integers(0, n, m))
    k = ea != eb
    alerte = (rng.random(n) < 0.01).astype(np.uint8)
    etat = rng.choice(np.array([0, 1, 2], dtype=np.uint8), size=int(k.sum()), p=[0.8, 0.14, 0.06])
    return Pyramide(x, y, dom, com, ea[k], eb[k], etat, None, alerte, noms_domaines=[f"Domaine {i + 1}" for i in range(domaines)])
