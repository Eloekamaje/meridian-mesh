// Passage à l'échelle « n'importe quel nombre de nœuds » — prototype du laboratoire.
//
// Principe : le coût d'une image dépend de ce qui est À L'ÉCRAN, jamais du nombre total de jumeaux.
//   • index spatial (grille) : on ne lit que les cellules visibles ;
//   • pyramide de regroupements (comme les tuiles d'une carte) : plus on est dézoomé, plus les jumeaux
//     sont agrégés en grappes ; le nombre d'éléments dessinés reste borné (~300) quel que soit N ;
//   • liens agrégés entre grappes (échantillon) au large, vrais liens seulement au zoom élevé ;
//   • tout en tableaux typés (pas d'objet par jumeau) : 1 million de jumeaux ≈ 100 Mo.
// En production, ces regroupements seraient servis par le backend (tuiles par niveau de zoom) : le
// navigateur ne chargerait jamais le graphe entier. Ici tout est calculé côté client pour la démonstration.

import { DOMAINES_ETENDUS } from "./laboGraphe";
import { DOMAINES } from "./domaines";

export const NOMS_DOMAINES = ["Client", "Paiement", "Distribution", "Opérations", "Risque", "Support", "Conformité", "Données", "Marketing", "Finance", "Juridique", "Logistique"];
export const COULEURS_DOMAINES = NOMS_DOMAINES.map((d) => DOMAINES[d] || DOMAINES_ETENDUS[d] || "#94A3B8");
const D = NOMS_DOMAINES.length;

const alea = (graine) => {
  let s = graine >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
};

// ---------------------------------------------------------------------------------------------
// Génération (tableaux typés). Domaines inégaux sur spirales de Vogel (~110 px entre voisins),
// attachement préférentiel (hubs), ~1,2 lien par jumeau dont un tiers transverses.
export function genererGrand(n, graine = 7) {
  const t0 = performance.now();
  const rnd = alea(graine + n);
  const poids = Array.from({ length: D }, () => 0.5 + rnd());
  const somme = poids.reduce((a, b) => a + b, 0);
  const tailles = poids.map((p) => Math.max(1, Math.round((p / somme) * n)));
  let ecart = tailles.reduce((a, b) => a + b, 0) - n;
  for (let i = 0; ecart !== 0; i = (i + 1) % D) {
    if (ecart > 0 && tailles[i] > 1) { tailles[i] -= 1; ecart -= 1; }
    else if (ecart < 0) { tailles[i] += 1; ecart += 1; }
  }
  const debutDom = new Int32Array(D + 1);
  for (let d = 0; d < D; d += 1) debutDom[d + 1] = debutDom[d] + tailles[d];

  const PAS = 86;
  const rayons = tailles.map((m) => PAS * Math.sqrt(m) + 70);
  const cellule = 2 * Math.max(...rayons) + 160;
  const colonnes = Math.ceil(Math.sqrt(D));
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const dom = new Uint8Array(n);
  const cov = new Uint8Array(n);
  for (let d = 0; d < D; d += 1) {
    const cx = (d % colonnes) * cellule;
    const cy = Math.floor(d / colonnes) * cellule;
    for (let k = 0; k < tailles[d]; k += 1) {
      const i = debutDom[d] + k;
      const a = k * 2.399963 + rnd() * 0.15;
      const r = PAS * Math.sqrt(k + 0.5);
      x[i] = cx + Math.cos(a) * r;
      y[i] = cy + Math.sin(a) * r;
      dom[i] = d;
      cov[i] = 40 + Math.floor(rnd() * 58);
    }
  }

  const cap = Math.ceil(n * 1.3) + 16;
  const ea = new Int32Array(cap);
  const eb = new Int32Array(cap);
  const etat = new Uint8Array(cap);
  let m = 0;
  const ajouter = (a, b) => {
    if (a === b || m >= cap) return;
    ea[m] = a;
    eb[m] = b;
    const t = rnd();
    etat[m] = t < 0.56 ? 0 : t < 0.87 ? 1 : t < 0.94 ? 2 : t < 0.96 ? 3 : t < 0.98 ? 4 : 5;
    m += 1;
  };
  for (let d = 0; d < D; d += 1) {
    const deb = debutDom[d];
    const fin = debutDom[d + 1];
    const pool = new Int32Array(2 * (fin - deb) + 2); // chaque extrémité de lien y figure : tirage ∝ degré
    let pl = 0;
    if (fin > deb) pool[pl++] = deb;
    for (let i = deb + 1; i < fin; i += 1) {
      const j = pool[Math.floor(rnd() * pl)];
      ajouter(i, j);
      pool[pl++] = i;
      pool[pl++] = j;
    }
    const extras = Math.round((fin - deb) * 0.12);
    for (let e = 0; e < extras && pl > 0; e += 1) ajouter(pool[Math.floor(rnd() * pl)], pool[Math.floor(rnd() * pl)]);
  }
  const intra = m;
  const transverses = Math.round(n * 0.33);
  for (let t = 0; t < transverses && intra > 0; t += 1) {
    const e1 = Math.floor(rnd() * intra);
    const e2 = Math.floor(rnd() * intra);
    ajouter(rnd() < 0.5 ? ea[e1] : eb[e1], rnd() < 0.5 ? ea[e2] : eb[e2]);
  }

  const deg = new Uint16Array(n);
  for (let e = 0; e < m; e += 1) {
    if (deg[ea[e]] < 65535) deg[ea[e]] += 1;
    if (deg[eb[e]] < 65535) deg[eb[e]] += 1;
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < n; i += 1) {
    if (x[i] < x0) x0 = x[i];
    if (x[i] > x1) x1 = x[i];
    if (y[i] < y0) y0 = y[i];
    if (y[i] > y1) y1 = y[i];
  }
  return { n, m, x, y, dom, cov, deg, ea, eb, etat, debutDom, tailles, bornes: { x0, y0, x1, y1 }, tGen: performance.now() - t0 };
}

// ---------------------------------------------------------------------------------------------
// Index : grille fine (jumeaux d'une cellule), pyramide de grappes, adjacence, échantillon de liens.
export const CELLULE_FINE = 256;
export const ZOOM_NOEUDS = 0.45; // à partir de là on dessine les jumeaux individuellement
const PX_GRAPPE = 64; // taille visée d'une grappe à l'écran

export function construireIndex(g) {
  const t0 = performance.now();
  const { n, m, x, y, dom, ea, eb } = g;
  const { x0, y0, x1, y1 } = g.bornes;
  const niveaux = [];
  // niveau 1 (le plus fin) : agrégation directe des jumeaux
  let s = CELLULE_FINE;
  let gw = Math.floor((x1 - x0) / s) + 2;
  let gh = Math.floor((y1 - y0) / s) + 2;
  let cnt = new Uint32Array(gw * gh);
  let sx = new Float64Array(gw * gh);
  let sy = new Float64Array(gw * gh);
  let hist = new Uint32Array(gw * gh * D);
  const celDe = new Int32Array(n); // cellule fine de chaque jumeau
  for (let i = 0; i < n; i += 1) {
    const c = Math.floor((y[i] - y0) / s) * gw + Math.floor((x[i] - x0) / s);
    celDe[i] = c;
    cnt[c] += 1;
    sx[c] += x[i];
    sy[c] += y[i];
    hist[c * D + dom[i]] += 1;
  }
  niveaux.push({ s, gw, gh, cnt, sx, sy, hist });
  // niveaux suivants : chaque cellule fusionne 2×2 cellules du niveau précédent
  while (niveaux[niveaux.length - 1].s < Math.max(x1 - x0, y1 - y0) && niveaux.length < 14) {
    const p = niveaux[niveaux.length - 1];
    const ns = p.s * 2;
    const ngw = Math.ceil(p.gw / 2) + 1;
    const ngh = Math.ceil(p.gh / 2) + 1;
    const ncnt = new Uint32Array(ngw * ngh);
    const nsx = new Float64Array(ngw * ngh);
    const nsy = new Float64Array(ngw * ngh);
    const nh = new Uint32Array(ngw * ngh * D);
    for (let cy = 0; cy < p.gh; cy += 1) {
      for (let cx = 0; cx < p.gw; cx += 1) {
        const c = cy * p.gw + cx;
        if (!p.cnt[c]) continue;
        const nc = (cy >> 1) * ngw + (cx >> 1);
        ncnt[nc] += p.cnt[c];
        nsx[nc] += p.sx[c];
        nsy[nc] += p.sy[c];
        for (let d = 0; d < D; d += 1) nh[nc * D + d] += p.hist[c * D + d];
      }
    }
    niveaux.push({ s: ns, gw: ngw, gh: ngh, cnt: ncnt, sx: nsx, sy: nsy, hist: nh });
  }
  // grille des jumeaux (tri par cellule fine)
  const fin = niveaux[0];
  const debut = new Int32Array(fin.gw * fin.gh + 1);
  for (let c = 0; c < fin.gw * fin.gh; c += 1) debut[c + 1] = debut[c] + fin.cnt[c];
  const rempli = new Int32Array(fin.gw * fin.gh);
  const cellNoeuds = new Int32Array(n);
  for (let i = 0; i < n; i += 1) {
    const c = celDe[i];
    cellNoeuds[debut[c] + rempli[c]] = i;
    rempli[c] += 1;
  }
  // adjacence CSR
  const adjDebut = new Int32Array(n + 1);
  for (let e = 0; e < m; e += 1) { adjDebut[ea[e] + 1] += 1; adjDebut[eb[e] + 1] += 1; }
  for (let i = 0; i < n; i += 1) adjDebut[i + 1] += adjDebut[i];
  const adjA = new Int32Array(2 * m);
  const cur = adjDebut.slice(0, n);
  for (let e = 0; e < m; e += 1) { adjA[cur[ea[e]]++] = eb[e]; adjA[cur[eb[e]]++] = ea[e]; }
  // liens triés par cellule fine de leur origine : permet d'échantillonner les liens d'une zone précise
  const eDebut = new Int32Array(fin.gw * fin.gh + 1);
  for (let e = 0; e < m; e += 1) eDebut[celDe[ea[e]] + 1] += 1;
  for (let c = 0; c < fin.gw * fin.gh; c += 1) eDebut[c + 1] += eDebut[c];
  const eListe = new Int32Array(m);
  const eCur = eDebut.slice(0, fin.gw * fin.gh);
  for (let e = 0; e < m; e += 1) eListe[eCur[celDe[ea[e]]]++] = e;
  // échantillon global de liens pour les vues très larges
  const pas = Math.max(1, Math.ceil(m / 12000));
  const echantillon = [];
  for (let e = 0; e < m; e += pas) echantillon.push(e);
  const marque = new Uint8Array(n);
  const octets = [x, y, dom, g.cov, g.deg, g.ea, g.eb, g.etat, celDe, cellNoeuds, debut, adjDebut, adjA, eDebut, eListe, ...niveaux.flatMap((v) => [v.cnt, v.sx, v.sy, v.hist])].reduce((a, t) => a + t.byteLength, 0);
  return { g, niveaux, debut, cellNoeuds, adjDebut, adjA, eDebut, eListe, echantillon, marque, x0, y0, tIndex: performance.now() - t0, octets };
}

// Niveau de regroupement à utiliser pour un zoom donné (0 = jumeaux individuels).
export function niveauPour(index, zoom) {
  if (zoom >= ZOOM_NOEUDS) return 0;
  for (let l = 0; l < index.niveaux.length; l += 1) if (index.niveaux[l].s * zoom >= PX_GRAPPE) return l + 1;
  return index.niveaux.length;
}

// Grappes visibles à un niveau (1..L) dans une fenêtre monde [wx0,wx1]×[wy0,wy1].
export function grappesVisibles(index, niv, wx0, wy0, wx1, wy1) {
  const v = index.niveaux[niv - 1];
  const cx0 = Math.max(0, Math.floor((wx0 - index.x0) / v.s));
  const cx1 = Math.min(v.gw - 1, Math.floor((wx1 - index.x0) / v.s));
  const cy0 = Math.max(0, Math.floor((wy0 - index.y0) / v.s));
  const cy1 = Math.min(v.gh - 1, Math.floor((wy1 - index.y0) / v.s));
  const out = [];
  for (let cy = cy0; cy <= cy1; cy += 1) {
    for (let cx = cx0; cx <= cx1; cx += 1) {
      const c = cy * v.gw + cx;
      if (!v.cnt[c]) continue;
      let dm = 0, mx = -1;
      for (let d = 0; d < D; d += 1) { const h = v.hist[c * D + d]; if (h > mx) { mx = h; dm = d; } }
      out.push({ c, cx, cy, n: v.cnt[c], x: v.sx[c] / v.cnt[c], y: v.sy[c] / v.cnt[c], dom: dm, part: mx / v.cnt[c] });
    }
  }
  return out;
}

// Jumeaux individuels visibles (via la grille fine), bornés.
export function noeudsVisibles(index, wx0, wy0, wx1, wy1, max = 6000) {
  const f = index.niveaux[0];
  const cx0 = Math.max(0, Math.floor((wx0 - index.x0) / f.s));
  const cx1 = Math.min(f.gw - 1, Math.floor((wx1 - index.x0) / f.s));
  const cy0 = Math.max(0, Math.floor((wy0 - index.y0) / f.s));
  const cy1 = Math.min(f.gh - 1, Math.floor((wy1 - index.y0) / f.s));
  const out = [];
  for (let cy = cy0; cy <= cy1 && out.length < max; cy += 1) {
    for (let cx = cx0; cx <= cx1 && out.length < max; cx += 1) {
      const c = cy * f.gw + cx;
      for (let k = index.debut[c]; k < index.debut[c + 1]; k += 1) {
        const i = index.cellNoeuds[k];
        const { x, y } = index.g;
        if (x[i] >= wx0 && x[i] <= wx1 && y[i] >= wy0 && y[i] <= wy1) out.push(i);
      }
    }
  }
  return out;
}

// Liens agrégés entre grappes visibles : [{a, b, poids}] triés par poids. Échantillonnage SPATIAL :
// si la fenêtre couvre peu de cellules fines on échantillonne les liens de cette zone (≤ 20 000),
// sinon (vue très large) on utilise l'échantillon global. Coût borné dans les deux cas.
export function liensGrappes(index, niv, grappes, wx0, wy0, wx1, wy1, garder = 260) {
  const v = index.niveaux[niv - 1];
  const f = index.niveaux[0];
  const parCellule = new Map(grappes.map((g, i) => [g.c, i]));
  const { x, y, ea, eb } = index.g;
  const paires = new Map();
  const cellule = (i) => Math.floor((y[i] - index.y0) / v.s) * v.gw + Math.floor((x[i] - index.x0) / v.s);
  const compter = (e) => {
    const a = parCellule.get(cellule(ea[e]));
    if (a === undefined) return;
    const b = parCellule.get(cellule(eb[e]));
    if (b === undefined || b === a) return;
    const cle = a < b ? a * 100000 + b : b * 100000 + a;
    paires.set(cle, (paires.get(cle) || 0) + 1);
  };
  const cx0 = Math.max(0, Math.floor((wx0 - index.x0) / f.s));
  const cx1 = Math.min(f.gw - 1, Math.floor((wx1 - index.x0) / f.s));
  const cy0 = Math.max(0, Math.floor((wy0 - index.y0) / f.s));
  const cy1 = Math.min(f.gh - 1, Math.floor((wy1 - index.y0) / f.s));
  if ((cx1 - cx0 + 1) * (cy1 - cy0 + 1) <= 6000) {
    let total = 0;
    for (let cy = cy0; cy <= cy1; cy += 1) for (let cx = cx0; cx <= cx1; cx += 1) { const c = cy * f.gw + cx; total += index.eDebut[c + 1] - index.eDebut[c]; }
    const pas = Math.max(1, Math.ceil(total / 20000));
    for (let cy = cy0; cy <= cy1; cy += 1) {
      for (let cx = cx0; cx <= cx1; cx += 1) {
        const c = cy * f.gw + cx;
        for (let k = index.eDebut[c]; k < index.eDebut[c + 1]; k += pas) compter(index.eListe[k]);
      }
    }
  } else {
    for (const e of index.echantillon) compter(e);
  }
  return [...paires.entries()].sort((p, q) => q[1] - p[1]).slice(0, garder).map(([cle, poids]) => ({ a: Math.floor(cle / 100000), b: cle % 100000, poids }));
}

// Vrais liens entre jumeaux visibles.
export function liensNoeuds(index, visibles, max = 4000) {
  const { marque, adjDebut, adjA } = index;
  visibles.forEach((i) => { marque[i] = 1; });
  const out = [];
  for (const i of visibles) {
    for (let k = adjDebut[i]; k < adjDebut[i + 1] && out.length < max; k += 1) {
      const j = adjA[k];
      if (marque[j] && i < j) out.push([i, j]);
    }
    if (out.length >= max) break;
  }
  visibles.forEach((i) => { marque[i] = 0; });
  return out;
}

// Jumeau le plus proche d'un point monde (parmi les visibles fournis).
export function plusProche(g, visibles, wx, wy, rayon) {
  let meilleur = -1;
  let dmin = rayon * rayon;
  for (const i of visibles) {
    const dx = g.x[i] - wx;
    const dy = g.y[i] - wy;
    const d = dx * dx + dy * dy;
    if (d < dmin) { dmin = d; meilleur = i; }
  }
  return meilleur;
}
