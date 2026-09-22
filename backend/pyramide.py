"""Pyramide de regroupements du Mesh — passage à l'échelle côté serveur.

Le navigateur ne doit jamais charger le graphe entier : il demande une VUE (fenêtre monde + zoom) et le
serveur répond avec un nombre borné d'éléments, quel que soit le nombre total de jumeaux — mais ce sont
TOUJOURS de VRAIS jumeaux (position réelle, degré réel), jamais une forme qui prétend en résumer un groupe.
Il n'y a qu'UN SEUL mode de réponse : `jumeaux` + `liens`, à tout zoom. Ce qui change avec le zoom, c'est
seulement COMBIEN on en montre (le budget) et LEQUEL on choisit quand il y en a plus que le budget :

    trop de jumeaux dans la fenêtre → on garde les mieux connectés d'abord (rang de priorité GLOBAL et stable :
    un jumeau une fois affiché ne redevient jamais invisible en zoomant — le maillage se remplit, il ne
    « saute » jamais d'une image à l'autre) ;
    assez peu → on les montre tous, avec leurs vrais liens.

Le dessin (points minuscules loin, robots proches) est une décision du CLIENT, continue avec le zoom — le
serveur ne change jamais de « mode » de rendu.

Hiérarchie interne domaine → groupe → communauté (Louvain) : sert au RÉSUMÉ (légende des domaines, effectifs,
écarts déclaré ≠ calculé) — plus jamais à dessiner une bulle à la place des jumeaux qu'elle contient.

Tout est vectorisé (numpy) : index en grille (jumeaux et liens rangés par cellule), agrégats par
`bincount`. Le module ne dépend ni de FastAPI ni de Mongo : il prend des tableaux et se teste seul.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

CELLULE = 256.0  # taille (monde) des cellules de la grille fine
# Budget de jumeaux RENDUS dans une vue — toujours des positions réelles, jamais une bulle qui en tient lieu.
# Un canvas 2D dessine des dizaines de milliers de points minuscules en quelques millisecondes ; le budget n'a
# donc pas besoin d'être petit, seulement borné (la réponse ne grandit jamais avec n).
MAX_JUMEAUX = 20_000
MAX_LIENS_JUMEAUX = 6000
SCRUTIN_PRIORITE = 400_000  # au-delà de ce nombre de candidats scrutés par priorité, on s'arrête — borne le pire cas

# Liens AGRÉGÉS entre grappes (communauté/groupe/domaine) : des milliers de liens individuels, dessinés un par
# un, loin, ne sont qu'un fouillis illisible (une « pelote ») — ils ne disent rien de plus qu'un trait épais,
# pondéré par leur VRAI nombre, entre les deux zones qu'ils relient. Ce n'est PAS une seconde vérité qui
# remplacerait les jumeaux (ceux-ci restent toujours réels, voir plus haut) : seuls les LIENS se résument, aux
# zooms où les montrer un par un n'apprendrait rien. Le niveau se resserre avec le zoom (domaine → groupe →
# communauté) jusqu'à disparaître : dès que les vrais liens (toujours renvoyés, entre les jumeaux affichés)
# suffisent à se lire seuls, l'agrégat s'efface — `fondu` transitionne l'un vers l'autre en douceur, jamais un
# saut.
MAX_LIENS_AGREGES = 260
ECHANTILLON_LIENS_AGREGES = 30_000
SEUILS_LIENS_AGREGES = ((0.045, 3), (0.16, 2), (0.5, 1))  # (zoom sous lequel ce niveau s'applique, niveau)


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
        # Rang de priorité STABLE (0 = montré en premier) : les mieux connectés d'abord, un hachage déterministe
        # de l'indice pour départager les ex-æquo (jamais le hasard — sinon la sélection changerait d'une requête
        # à l'autre). `ordre_priorite[k]` = le k-ième jumeau par importance : scruter ce tableau dans l'ordre,
        # en ne gardant que ceux tombés dans la fenêtre, donne les plus importants de la fenêtre SANS avoir à
        # trier tous ses candidats — le coût ne dépend que du budget demandé, jamais de n.
        depart = (np.arange(self.n, dtype=np.uint32) * np.uint32(2654435761)) % np.uint32(10_000)
        cle_priorite = -self.degre.astype(np.int64) * 10_000 - depart.astype(np.int64)
        self.ordre_priorite = np.argsort(cle_priorite, kind="stable").astype(np.int64)
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
        self.x1, self.y1 = float(self.x.max()), float(self.y.max())
        self.gw = int((self.x1 - self.x0) // CELLULE) + 2
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

    def selection_prioritaire(self, x0, y0, x1, y1, budget: int) -> np.ndarray:
        """Jusqu'à `budget` jumeaux de la fenêtre — TOUS s'ils tiennent, sinon les mieux connectés d'abord
        (`ordre_priorite`, stable). Coût borné par le budget, jamais par n : à grande fenêtre archi-dense, on
        s'arrête d'ABORD à `jumeaux_dans` (elle-même bornée par la grille) pour savoir si ça tient large ;
        si non, on scrute l'ordre de priorité global (borné par `SCRUTIN_PRIORITE`) plutôt que de trier tout
        ce qui tombe dans la fenêtre — qui pourrait être le Mesh entier."""
        # Fenêtre qui couvre déjà tout le monde connu : inutile de balayer la grille pour SAVOIR qu'il y a plus
        # de jumeaux que le budget (ce serait, à elle seule, un parcours de tout n) — on le sait déjà.
        englobe_tout = self.n > budget and x0 <= self.x0 and y0 <= self.y0 and x1 >= self.x1 and y1 >= self.y1
        if not englobe_tout:
            idx = self.jumeaux_dans(x0, y0, x1, y1, budget + 1)
            if idx.size <= budget:
                return idx
        else:
            idx = np.zeros(0, dtype=np.int64)
        candidats = self.ordre_priorite[:SCRUTIN_PRIORITE]
        xc, yc = self.x[candidats], self.y[candidats]
        k = (xc >= x0) & (xc <= x1) & (yc >= y0) & (yc <= y1)
        choisis = candidats[k][:budget]
        if choisis.size >= budget:
            return choisis
        # la fenêtre est assez fournie (> budget par la grille) mais ses membres sont surtout de faible priorité,
        # hors du scrutin global : on complète avec ce que la grille avait déjà trouvé, sans dépasser le budget
        reste = idx[~np.isin(idx, choisis, assume_unique=False)]
        return np.concatenate([choisis, reste])[:budget]

    # ---- réponse d'une vue --------------------------------------------------------------------------------
    def vue(self, x0: float, y0: float, x1: float, y1: float, zoom: float) -> dict:
        """Vue bornée d'une fenêtre monde à un zoom donné : toujours de VRAIS jumeaux, jamais une grappe qui en
        tient lieu. Le nombre renvoyé ne dépend pas de n ; ce qui varie avec le zoom, c'est seulement combien on
        en montre — et un jumeau une fois montré le reste tant qu'il est dans la fenêtre (rang stable : on ne
        « saute » jamais d'un rendu à l'autre, on se remplit). Les LIENS, eux, se résument tant que les montrer
        un par un serait un fouillis illisible (`liens_agreges` : voir la constante `SEUILS_LIENS_AGREGES`) —
        un trait épais et pondéré plutôt que des milliers de traits fins ; l'agrégat s'efface en douceur
        (`fondu`) à mesure que les vrais liens, déjà renvoyés dans `liens`, deviennent lisibles seuls."""
        t0 = time.perf_counter()
        if self.n == 0:
            return {"mode": "vide", "jumeaux": [], "liens": [], "n_total": 0, "duree_ms": 0.0}
        idx = self.selection_prioritaire(x0, y0, x1, y1, MAX_JUMEAUX)
        rep: dict = {"n_total": self.n, "zoom": zoom}
        rep.update(self._jumeaux(idx, x0, y0, x1, y1))
        niveau, fondu = self._niveau_liens_agreges(zoom)
        if niveau:
            rep["liens_agreges"] = self._liens_agreges(niveau, x0, y0, x1, y1)
            rep["fondu_agreges"] = fondu
        rep["duree_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return rep

    @staticmethod
    def _niveau_liens_agreges(zoom: float) -> tuple[int, float]:
        """Niveau d'agrégation des LIENS pour ce zoom (0 = aucun, les vrais liens suffisent), et un `fondu`
        (1 → agrégat pleinement visible, 0 → transparent) qui s'annule progressivement juste avant le seuil
        suivant : l'agrégat ne disparaît jamais d'un coup, il cède la place aux vrais liens en s'effaçant."""
        for seuil, niveau in SEUILS_LIENS_AGREGES:
            if zoom < seuil:
                return niveau, 1.0
        dernier_seuil = SEUILS_LIENS_AGREGES[-1][0]
        largeur = dernier_seuil * 0.9
        if zoom < dernier_seuil + largeur:
            return SEUILS_LIENS_AGREGES[-1][1], max(0.0, 1.0 - (zoom - dernier_seuil) / largeur)
        return 0, 0.0

    def _liens_agreges(self, niveau: int, x0, y0, x1, y1) -> list:
        """Traits agrégés entre grappes (niveau 1 = communauté, 2 = groupe, 3 = domaine) dont le territoire
        touche la fenêtre : un trait par paire, pondéré par le nombre RÉEL de liens qui les relient — jamais
        inventé, un vrai décompte, seulement résumé. Toujours calculé sur les liens de la fenêtre, indépendamment
        du nombre de jumeaux réellement affichés (`selection_prioritaire` choisit les NŒUDS, ceci résume les
        ARCS — les deux budgets sont séparés)."""
        v = self.niv[niveau]
        dans_fenetre = (v.taille > 0) & (v.x + v.r >= x0) & (v.x - v.r <= x1) & (v.y + v.r >= y0) & (v.y - v.r <= y1)
        ids = np.nonzero(dans_fenetre)[0]
        if ids.size == 0 or self.m == 0:
            return []
        el = self._lignes(self.edebut, self.eordre, x0, y0, x1, y1)
        if el.size > ECHANTILLON_LIENS_AGREGES:
            el = el[:: int(np.ceil(el.size / ECHANTILLON_LIENS_AGREGES))]
        if el.size == 0:
            return []
        vers = self.com if niveau == 1 else (self.gid[self.com] if niveau == 2 else self.dom_c[self.com])
        a, b = vers[self.ea[el]], vers[self.eb[el]]
        pos = np.full(int(v.taille.shape[0]), -1, dtype=np.int32)
        pos[ids] = np.arange(ids.size, dtype=np.int32)
        pa, pb = pos[a], pos[b]
        k = (pa >= 0) & (pb >= 0) & (pa != pb)
        if not k.any():
            return []
        lo, hi = np.minimum(pa[k], pb[k]).astype(np.int64), np.maximum(pa[k], pb[k]).astype(np.int64)
        cles, nb = np.unique(lo * 1_000_000 + hi, return_counts=True)
        ordre = np.argsort(-nb)[:MAX_LIENS_AGREGES]
        out = []
        for i in ordre:
            pl, ph = int(cles[i] // 1_000_000), int(cles[i] % 1_000_000)
            ca, cb = int(ids[pl]), int(ids[ph])
            out.append({"ax": round(float(v.x[ca]), 1), "ay": round(float(v.y[ca]), 1),
                        "bx": round(float(v.x[cb]), 1), "by": round(float(v.y[cb]), 1), "poids": int(nb[i])})
        return out

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
        return {"mode": "jumeaux", "jumeaux": jumeaux, "liens": liens}


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


def _hex_hsl(h: float, s: float, l: float) -> str:
    """HSL (0-360, 0-1, 0-1) → « #RRGGBB »."""
    h = h % 360.0
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = l - c / 2.0
    r, g, b = ((c, x, 0.0), (x, c, 0.0), (0.0, c, x), (0.0, x, c), (x, 0.0, c), (c, 0.0, x))[int(h // 60) % 6]
    return "#{:02X}{:02X}{:02X}".format(round((r + m) * 255), round((g + m) * 255), round((b + m) * 255))


def palette_domaines(D: int) -> tuple[list[str], list[int]]:
    """Une couleur par domaine, groupée par FAMILLE : la famille se reconnaît d'un coup d'œil (même teinte,
    posée sur ~√D emplacements également espacés sur le cercle), chaque domaine s'en distingue par une nuance
    (luminosité, saturation). Déterministe — ne dépend que de D, jamais de la graine ni de n."""
    if D <= 0:
        return [], []
    nfam = max(1, round(D ** 0.5))
    fam = [i % nfam for i in range(D)]  # entrelacé : deux domaines de la même famille ne sont pas des voisins numériques
    couleurs = []
    for i in range(D):
        f = fam[i]
        rang = i // nfam  # position de ce domaine au sein de sa famille
        teinte = 360.0 * f / nfam
        nuance = (rang * 0.6180339887) % 1.0  # suite additive au nombre d'or : les nuances d'une famille ne s'alignent jamais
        sat = 0.52 + 0.24 * nuance
        lum = 0.40 + 0.26 * ((rang * 0.3819660113) % 1.0)
        couleurs.append(_hex_hsl(teinte, sat, lum))
    return couleurs, fam


def _disposer_domaines(fam: np.ndarray, rayon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Centres des domaines par une DOUBLE SPIRALE DE VOGEL (tournesol) : angle d'or, rayon en racine carrée du
    rang — la même technique qui place déjà les jumeaux au sein d'un domaine (`frontend/src/lib/laboEchelle.js`,
    « spirales de Vogel »), appliquée ici au niveau des DOMAINES pour ne jamais retomber sur une grille de
    territoires. Chaque FAMILLE occupe d'abord un bras de la spirale grossière (elle reste reconnaissable, un
    amas cohérent) ; à l'intérieur, ses domaines se placent sur une petite spirale locale autour du centre de la
    famille. Purement déterministe (aucune graine) et bornée : l'étendue totale croît avec la RACINE du nombre
    de domaines, jamais en pointe isolée comme peut le faire une simulation de forces mal amortie."""
    D = fam.shape[0]
    if D <= 1:
        return np.zeros(D, dtype=np.float32), np.zeros(D, dtype=np.float32)
    ANGLE_OR = 2.399963  # angle d'or (rad) : deux rangs consécutifs ne s'alignent jamais
    nfam = int(fam.max()) + 1
    masse_fam = np.bincount(fam, weights=rayon ** 2, minlength=nfam)  # une famille à beaucoup de gros domaines pèse plus
    rayon_fam = np.sqrt(masse_fam / np.pi) * 1.7 + 40.0
    pas_fam = 2.6 * float(np.median(rayon_fam))
    kf = np.arange(nfam)
    cx_fam = pas_fam * np.sqrt(kf + 0.5) * np.cos(kf * ANGLE_OR)
    cy_fam = pas_fam * np.sqrt(kf + 0.5) * np.sin(kf * ANGLE_OR)
    x, y = np.zeros(D, dtype=np.float64), np.zeros(D, dtype=np.float64)
    ordre = np.argsort(fam, kind="stable")
    fam_o, rayon_o = fam[ordre], rayon[ordre]
    debut = np.searchsorted(fam_o, np.arange(nfam), side="left")
    fin = np.searchsorted(fam_o, np.arange(nfam), side="right")
    for f in range(nfam):
        i0, i1 = int(debut[f]), int(fin[f])
        if i1 <= i0:
            continue
        rl = rayon_o[i0:i1]
        pas_local = 2.3 * float(np.median(rl))
        k = np.arange(i1 - i0)
        rr = pas_local * np.sqrt(k + 0.5)
        aa = k * ANGLE_OR
        x[i0:i1] = cx_fam[f] + rr * np.cos(aa)
        y[i0:i1] = cy_fam[f] + rr * np.sin(aa)
    out_x, out_y = np.zeros(D, dtype=np.float32), np.zeros(D, dtype=np.float32)
    out_x[ordre], out_y[ordre] = x.astype(np.float32), y.astype(np.float32)
    return out_x, out_y


def synthetique(n: int, graine: int = 1, domaines: int = 8) -> Pyramide:
    """Jeu synthétique de n jumeaux (essais d'échelle, y compris des CENTAINES de domaines) : quelques domaines
    « hub » et beaucoup de petits (loi de puissance, comme une vraie entreprise), disposés en amas organique
    (`_disposer_domaines`) plutôt qu'en grille ; communautés gaussiennes STRUCTURELLES (la position vient de la
    communauté, jamais du domaine déclaré seul) ; ~20 % des communautés partagées entre deux domaines déclarés
    (écarts de GROUPE, pas seulement individuels) ; liens surtout locaux à une communauté."""
    rng = np.random.default_rng(graine)
    C = max(n // 60, domaines * 2, 4)  # au moins 2 communautés par domaine : aucun domaine n'en reste sans, même à des centaines
    couleurs, fam = palette_domaines(domaines)
    # Loi de puissance MAIS bornée : sans plafond, une poignée de domaines (Pareto a la queue très lourde)
    # peut avaler la moitié du Mesh — réaliste à 8 domaines, dégénéré à des centaines (plus de « galaxie »,
    # un seul astre géant et de la poussière). Le plafond absolu laisse quelques domaines hubs nettement plus
    # gros que la moyenne sans qu'aucun n'écrase visuellement tous les autres, quel que soit leur nombre.
    poids_dom = np.clip(rng.pareto(1.2, domaines) + 0.5, 0.1, 6.0)
    # chaque domaine reçoit au moins une communauté garantie (sinon, à des centaines de domaines, une bonne
    # partie resterait à 0 jumeau par pur tirage) ; le reste se répartit selon le poids (quelques domaines hubs)
    dc = np.concatenate([np.arange(domaines), rng.choice(domaines, size=C - domaines, p=poids_dom / poids_dom.sum())])
    # la communauté qui GARANTIT un domaine (les `domaines` premières valeurs ci-dessus, avant mélange) ne sera
    # jamais scindée : un domaine reste toujours représenté par au moins une communauté qui lui appartient
    # pleinement, même à des centaines de domaines où le hasard, sinon, en laisserait parfois sans aucun membre
    garantie = np.concatenate([np.ones(domaines, dtype=bool), np.zeros(C - domaines, dtype=bool)])
    permutation = rng.permutation(C)
    dc, garantie = dc[permutation], garantie[permutation]
    comptes_dom = np.bincount(dc, minlength=domaines).astype(np.float64)
    rayon_dom = 210.0 * np.sqrt(np.maximum(comptes_dom, 1.0))
    ax, ay = _disposer_domaines(np.array(fam, dtype=np.int32), rayon_dom)
    # décalage en quadrant positif : l'amas est centré sur lui-même (recentrage interne à `_disposer_domaines`),
    # mais le reste (cadrage initial du client, fenêtres historiques) suppose un monde synthétique qui commence
    # près de l'origine et s'étend vers les positifs — même repère qu'avant l'amas organique
    decalage = 450.0 * np.sqrt(max(n // 60, 4))
    ax, ay = ax + decalage, ay + decalage
    angle, rayon = rng.uniform(0, 2 * np.pi, C), rayon_dom[dc] * np.sqrt(rng.uniform(0, 1, C))
    cx = ax[dc] + rayon * np.cos(angle)
    cy = ay[dc] + rayon * np.sin(angle)
    com = rng.integers(0, C, n)
    x, y = cx[com] + rng.normal(0, 90, n), cy[com] + rng.normal(0, 90, n)
    # Domaine DÉCLARÉ (BCM) vs communauté STRUCTURELLE (calculée sur les liens réels, ci-dessous) : la position
    # d'un jumeau vient de sa communauté ; son domaine déclaré n'en est pas forcément le reflet exact. Environ
    # un cinquième des communautés sont partagées entre DEUX domaines déclarés (une équipe technique organisée
    # autrement que l'organigramme officiel) — un vrai désaccord de groupe, pas seulement le bruit individuel
    # de quelques jumeaux isolés. C'est cet écart (déclaré ≠ dominant calculé) que l'Atlas signale déjà.
    scindee = (rng.random(C) < 0.2) & ~garantie
    dc2 = rng.integers(0, domaines, C)
    part_secondaire = rng.uniform(0.25, 0.5, C)
    vers_secondaire = scindee[com] & (rng.random(n) < part_secondaire[com])
    dom = np.where(vers_secondaire, dc2[com], dc[com])
    dom = np.where((~scindee[com]) & (rng.random(n) < 0.02), rng.integers(0, domaines, n), dom)  # bruit individuel résiduel
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
    p = Pyramide(x, y, dom, com, ea[k], eb[k], etat, None, alerte, noms_domaines=[f"Domaine {i + 1}" for i in range(domaines)])
    p.couleurs_domaines = couleurs
    p.familles_domaines = fam
    return p
