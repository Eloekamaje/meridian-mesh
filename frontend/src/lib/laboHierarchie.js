// Agrégation SÉMANTIQUE pour le passage à l'échelle — prototype du laboratoire.
//
// Différence avec lib/laboEchelle.js : les regroupements ne viennent plus d'une grille arbitraire mais de la
// hiérarchie métier — domaine → groupe → communauté → jumeau. Chaque grappe :
//   • est nommée et STABLE (elle ne change pas quand on déplace la caméra ni quand les données bougent) ;
//   • a une vraie étendue (rayon), donc ne chevauche pas ses voisines ;
//   • PORTE SES SIGNAUX : nombre de jumeaux en écart (déclaré ≠ calculé) et en situation active — un jumeau
//     en alerte au milieu de 10 000 ne disparaît donc pas quand on dézoome.
// Tableaux typés partout ; les jumeaux sont numérotés de façon contiguë par communauté, groupe et domaine.

import { NOMS_DOMAINES } from "./laboEchelle";

const D = NOMS_DOMAINES.length;
const alea = (graine) => {
  let s = graine >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
};
const mediane = (t) => {
  const c = Float32Array.from(t).sort();
  return c.length ? c[Math.floor(c.length / 2)] : 1;
};

export const PAS_NOEUD = 86;

export function genererHierarchie(n, graine = 11) {
  const t0 = performance.now();
  const rnd = alea(graine + n);

  // ---- 1. Tailles : domaines inégaux, découpés en communautés, regroupées en groupes ---------------------
  const poids = Array.from({ length: D }, () => 0.5 + rnd());
  const somme = poids.reduce((a, b) => a + b, 0);
  const tailles = poids.map((p) => Math.max(3, Math.round((p / somme) * n)));
  let ecart = tailles.reduce((a, b) => a + b, 0) - n;
  for (let i = 0; ecart !== 0; i = (i + 1) % D) {
    if (ecart > 0 && tailles[i] > 3) { tailles[i] -= 1; ecart -= 1; }
    else if (ecart < 0) { tailles[i] += 1; ecart += 1; }
  }
  const S = Math.max(8, Math.min(160, Math.round(n / (D * 7)))); // taille moyenne d'une communauté
  const comDom = [], comTaille = [], comGrp = [];
  const grpDom = [], grpC0 = [], grpC1 = [];
  const domG0 = new Int32Array(D + 1);
  for (let d = 0; d < D; d += 1) {
    let reste = tailles[d];
    const tab = [];
    while (reste > 0) {
      let s = Math.min(reste, Math.max(3, Math.round(S * (0.5 + rnd()))));
      if (reste - s < 3) s = reste;
      tab.push(s);
      reste -= s;
    }
    domG0[d] = grpDom.length;
    for (let i = 0; i < tab.length;) {
      const gs = Math.min(tab.length - i, 6 + Math.floor(rnd() * 5));
      grpDom.push(d);
      grpC0.push(comDom.length);
      for (let k = 0; k < gs; k += 1) { comDom.push(d); comTaille.push(tab[i + k]); comGrp.push(grpDom.length - 1); }
      grpC1.push(comDom.length);
      i += gs;
    }
  }
  domG0[D] = grpDom.length;
  const C = comDom.length;
  const G = grpDom.length;

  // ---- 2. Géométrie : spirales imbriquées (domaine ⊃ groupe ⊃ communauté ⊃ jumeau) ------------------------
  const rcMax = PAS_NOEUD * Math.sqrt(Math.max(...comTaille)) + 60;
  const cCoef = (2 * rcMax * 1.05) / 1.6;
  const gsMax = Math.max(...grpC0.map((c0, g) => grpC1[g] - c0));
  const rgMax = cCoef * Math.sqrt(gsMax) + rcMax;
  const gCoef = (2 * rgMax * 1.05) / 1.6;
  const ngMax = Math.max(...Array.from({ length: D }, (_, d) => domG0[d + 1] - domG0[d]));
  const rdMax = gCoef * Math.sqrt(ngMax) + rgMax;
  const cellule = 2 * rdMax + 220;
  const colonnes = Math.ceil(Math.sqrt(D));

  const x = new Float32Array(n), y = new Float32Array(n);
  const dom = new Uint8Array(n), cov = new Uint8Array(n), ecartN = new Uint8Array(n), alerteN = new Uint8Array(n);
  const com = new Int32Array(n);
  const comDebut = new Int32Array(C + 1);
  const cx = new Float32Array(C), cy = new Float32Array(C), cr = new Float32Array(C);
  const gx = new Float32Array(G), gy = new Float32Array(G), gr = new Float32Array(G);
  const dx = new Float32Array(D), dy = new Float32Array(D), dr = new Float32Array(D);
  const debutDom = new Int32Array(D + 1);
  let idn = 0;
  for (let d = 0; d < D; d += 1) {
    dx[d] = (d % colonnes) * cellule;
    dy[d] = Math.floor(d / colonnes) * cellule;
    debutDom[d] = idn;
    for (let g = domG0[d]; g < domG0[d + 1]; g += 1) {
      const kg = g - domG0[d];
      const ag = kg * 2.399963;
      gx[g] = dx[d] + Math.cos(ag) * gCoef * Math.sqrt(kg + 0.5);
      gy[g] = dy[d] + Math.sin(ag) * gCoef * Math.sqrt(kg + 0.5);
      for (let c = grpC0[g]; c < grpC1[g]; c += 1) {
        const kc = c - grpC0[g];
        const ac = kc * 2.399963 + 0.4;
        cx[c] = gx[g] + Math.cos(ac) * cCoef * Math.sqrt(kc + 0.5);
        cy[c] = gy[g] + Math.sin(ac) * cCoef * Math.sqrt(kc + 0.5);
        cr[c] = PAS_NOEUD * Math.sqrt(comTaille[c]) + 40;
        comDebut[c] = idn;
        for (let k = 0; k < comTaille[c]; k += 1) {
          const a = k * 2.399963 + rnd() * 0.15;
          const r = PAS_NOEUD * Math.sqrt(k + 0.5);
          x[idn] = cx[c] + Math.cos(a) * r;
          y[idn] = cy[c] + Math.sin(a) * r;
          dom[idn] = d;
          com[idn] = c;
          cov[idn] = 40 + Math.floor(rnd() * 58);
          idn += 1;
        }
      }
    }
  }
  debutDom[D] = idn;
  comDebut[C] = idn;
  // étendues : chaque niveau englobe ses enfants
  for (let g = 0; g < G; g += 1) {
    let r = 0;
    for (let c = grpC0[g]; c < grpC1[g]; c += 1) r = Math.max(r, Math.hypot(cx[c] - gx[g], cy[c] - gy[g]) + cr[c]);
    gr[g] = r + 30;
  }
  for (let d = 0; d < D; d += 1) {
    let r = 0;
    for (let g = domG0[d]; g < domG0[d + 1]; g += 1) r = Math.max(r, Math.hypot(gx[g] - dx[d], gy[g] - dy[d]) + gr[g]);
    dr[d] = r + 40;
  }

  // ---- 3. Signaux : écarts (déclaré ≠ calculé) et situations actives (foyers dans quelques communautés) ------
  for (let i = 0; i < n; i += 1) if (rnd() < 0.04) ecartN[i] = 1;
  for (let c = 0; c < C; c += 1) {
    const foyer = rnd() < 0.012;
    for (let i = comDebut[c]; i < comDebut[c + 1]; i += 1) if ((foyer && rnd() < 0.4) || rnd() < 0.002) alerteN[i] = 1;
  }
  const comEcarts = new Int32Array(C), comAlertes = new Int32Array(C);
  for (let c = 0; c < C; c += 1) for (let i = comDebut[c]; i < comDebut[c + 1]; i += 1) { comEcarts[c] += ecartN[i]; comAlertes[c] += alerteN[i]; }
  const grpN = new Int32Array(G), grpEcarts = new Int32Array(G), grpAlertes = new Int32Array(G);
  const domN = new Int32Array(D), domEcarts = new Int32Array(D), domAlertes = new Int32Array(D);
  for (let c = 0; c < C; c += 1) {
    const g = comGrp[c];
    grpN[g] += comTaille[c]; grpEcarts[g] += comEcarts[c]; grpAlertes[g] += comAlertes[c];
    domN[comDom[c]] += comTaille[c]; domEcarts[comDom[c]] += comEcarts[c]; domAlertes[comDom[c]] += comAlertes[c];
  }

  // ---- 4. Liens : denses dans la communauté, puis entre communautés d'un groupe, entre groupes, entre domaines ----
  const cap = Math.ceil(n * 1.35) + 16;
  const ea = new Int32Array(cap), eb = new Int32Array(cap), etat = new Uint8Array(cap);
  let m = 0;
  const ajouter = (a, b) => {
    if (a === b || m >= cap) return;
    ea[m] = a; eb[m] = b;
    const t = rnd();
    etat[m] = t < 0.56 ? 0 : t < 0.87 ? 1 : t < 0.94 ? 2 : t < 0.96 ? 3 : t < 0.98 ? 4 : 5;
    m += 1;
  };
  for (let c = 0; c < C; c += 1) {
    const a = comDebut[c], b = comDebut[c + 1];
    const pool = new Int32Array(2 * (b - a) + 2);
    let pl = 0;
    pool[pl++] = a;
    for (let i = a + 1; i < b; i += 1) {
      const j = pool[Math.floor(rnd() * pl)];
      ajouter(i, j);
      pool[pl++] = i; pool[pl++] = j;
    }
    const extras = Math.round((b - a) * 0.15);
    for (let e = 0; e < extras; e += 1) ajouter(pool[Math.floor(rnd() * pl)], pool[Math.floor(rnd() * pl)]);
  }
  const noeudDe = (c) => comDebut[c] + Math.floor(rnd() * comTaille[c]);
  for (let e = 0, N1 = Math.round(n * 0.1); e < N1; e += 1) { // entre communautés d'un même groupe
    const c1 = Math.floor(rnd() * C), g = comGrp[c1];
    const c2 = grpC0[g] + Math.floor(rnd() * (grpC1[g] - grpC0[g]));
    if (c1 !== c2) ajouter(noeudDe(c1), noeudDe(c2));
  }
  for (let e = 0, N2 = Math.round(n * 0.06); e < N2; e += 1) { // entre groupes d'un même domaine
    const c1 = Math.floor(rnd() * C), d = comDom[c1];
    const g2 = domG0[d] + Math.floor(rnd() * (domG0[d + 1] - domG0[d]));
    const c2 = grpC0[g2] + Math.floor(rnd() * (grpC1[g2] - grpC0[g2]));
    if (c1 !== c2) ajouter(noeudDe(c1), noeudDe(c2));
  }
  for (let e = 0, N3 = Math.round(n * 0.08); e < N3; e += 1) ajouter(Math.floor(rnd() * n), Math.floor(rnd() * n)); // entre domaines
  const deg = new Uint16Array(n);
  for (let e = 0; e < m; e += 1) { if (deg[ea[e]] < 65535) deg[ea[e]] += 1; if (deg[eb[e]] < 65535) deg[eb[e]] += 1; }

  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < n; i += 1) { if (x[i] < x0) x0 = x[i]; if (x[i] > x1) x1 = x[i]; if (y[i] < y0) y0 = y[i]; if (y[i] > y1) y1 = y[i]; }

  // Les trois niveaux de grappes, dans une structure commune
  const niveaux = {
    1: { nom: "Communauté", n: C, x: cx, y: cy, r: cr, taille: Int32Array.from(comTaille), dom: Uint8Array.from(comDom), ecarts: comEcarts, alertes: comAlertes, parent: Int32Array.from(comGrp) },
    2: { nom: "Groupe", n: G, x: gx, y: gy, r: gr, taille: grpN, dom: Uint8Array.from(grpDom), ecarts: grpEcarts, alertes: grpAlertes, parent: Int32Array.from(grpDom) },
    3: { nom: "Domaine", n: D, x: dx, y: dy, r: dr, taille: domN, dom: Uint8Array.from({ length: D }, (_, i) => i), ecarts: domEcarts, alertes: domAlertes, parent: null },
  };
  Object.values(niveaux).forEach((v) => { v.rMed = mediane(v.r); });
  return { n, m, x, y, dom, com, cov, deg, ea, eb, etat, ecartN, alerteN, debutDom, comDebut, grpC0, grpC1, comGrp, domG0, tailles, niveaux, bornes: { x0, y0, x1, y1 }, tGen: performance.now() - t0 };
}

// Rang d'un jumeau au sein de son domaine (pour son nom) et libellés de la hiérarchie.
export const rangDansDomaine = (g, i) => i - g.debutDom[g.dom[i]] + 1;
export const nomBulle = (g, niv, id) => {
  const v = g.niveaux[niv];
  if (niv === 3) return NOMS_DOMAINES[id];
  if (niv === 2) return `${NOMS_DOMAINES[v.dom[id]]} · groupe ${id - g.domG0[v.dom[id]] + 1}`;
  const grp = g.comGrp[id];
  return `${NOMS_DOMAINES[v.dom[id]]} · groupe ${grp - g.domG0[v.dom[id]] + 1} · communauté ${id - g.grpC0[grp] + 1}`;
};

// ---------------------------------------------------------------------------------------------
// Index : grille fine des jumeaux, adjacence, liens par cellule, grilles de grappes (niveaux 1 et 2).
// Compatible avec noeudsVisibles / liensNoeuds / plusProche de laboEchelle.js.
export function construireIndexHier(g) {
  const t0 = performance.now();
  const { n, m, x, y, ea, eb } = g;
  const { x0, y0, x1, y1 } = g.bornes;
  const s = 256;
  const gw = Math.floor((x1 - x0) / s) + 2;
  const gh = Math.floor((y1 - y0) / s) + 2;
  const cells = gw * gh;
  const celDe = new Int32Array(n);
  const debut = new Int32Array(cells + 1);
  for (let i = 0; i < n; i += 1) {
    const c = Math.floor((y[i] - y0) / s) * gw + Math.floor((x[i] - x0) / s);
    celDe[i] = c;
    debut[c + 1] += 1;
  }
  for (let c = 0; c < cells; c += 1) debut[c + 1] += debut[c];
  const cellNoeuds = new Int32Array(n);
  const rempli = new Int32Array(cells);
  for (let i = 0; i < n; i += 1) { const c = celDe[i]; cellNoeuds[debut[c] + rempli[c]] = i; rempli[c] += 1; }

  const adjDebut = new Int32Array(n + 1);
  for (let e = 0; e < m; e += 1) { adjDebut[ea[e] + 1] += 1; adjDebut[eb[e] + 1] += 1; }
  for (let i = 0; i < n; i += 1) adjDebut[i + 1] += adjDebut[i];
  const adjA = new Int32Array(2 * m);
  const cur = adjDebut.slice(0, n);
  for (let e = 0; e < m; e += 1) { adjA[cur[ea[e]]++] = eb[e]; adjA[cur[eb[e]]++] = ea[e]; }

  const eDebut = new Int32Array(cells + 1);
  for (let e = 0; e < m; e += 1) eDebut[celDe[ea[e]] + 1] += 1;
  for (let c = 0; c < cells; c += 1) eDebut[c + 1] += eDebut[c];
  const eListe = new Int32Array(m);
  const eCur = eDebut.slice(0, cells);
  for (let e = 0; e < m; e += 1) eListe[eCur[celDe[ea[e]]]++] = e;
  const pas = Math.max(1, Math.ceil(m / 12000));
  const echantillon = [];
  for (let e = 0; e < m; e += pas) echantillon.push(e);

  // grilles de grappes : chaque grappe est rangée dans la cellule de son centre (rayon ≤ demi-cellule)
  const grilles = {};
  [1, 2].forEach((niv) => {
    const v = g.niveaux[niv];
    let rmax = 0;
    for (let i = 0; i < v.n; i += 1) rmax = Math.max(rmax, v.r[i]);
    const cs = Math.max(256, 2 * rmax);
    const bw = Math.floor((x1 - x0) / cs) + 3;
    const bh = Math.floor((y1 - y0) / cs) + 3;
    const bd = new Int32Array(bw * bh + 1);
    const cle = new Int32Array(v.n);
    for (let i = 0; i < v.n; i += 1) { cle[i] = (Math.floor((v.y[i] - y0) / cs) + 1) * bw + Math.floor((v.x[i] - x0) / cs) + 1; bd[cle[i] + 1] += 1; }
    for (let c = 0; c < bw * bh; c += 1) bd[c + 1] += bd[c];
    const ids = new Int32Array(v.n);
    const rp = new Int32Array(bw * bh);
    for (let i = 0; i < v.n; i += 1) { ids[bd[cle[i]] + rp[cle[i]]] = i; rp[cle[i]] += 1; }
    grilles[niv] = { cs, bw, bh, bd, ids };
  });
  const marque = new Uint8Array(n);
  const octets = [x, y, g.dom, g.com, g.cov, g.deg, g.ea, g.eb, g.etat, g.ecartN, g.alerteN, celDe, debut, cellNoeuds, adjDebut, adjA, eDebut, eListe].reduce((a, t) => a + t.byteLength, 0);
  return { g, niveaux: [{ s, gw, gh }], debut, cellNoeuds, adjDebut, adjA, eDebut, eListe, echantillon, marque, x0, y0, grilles, tIndex: performance.now() - t0, octets };
}

// Grappes d'un niveau qui coupent la fenêtre monde.
export function bullesVisibles(index, niv, w0, h0, w1, h1) {
  const v = index.g.niveaux[niv];
  if (niv === 3) {
    const out = [];
    for (let i = 0; i < v.n; i += 1) if (v.x[i] + v.r[i] >= w0 && v.x[i] - v.r[i] <= w1 && v.y[i] + v.r[i] >= h0 && v.y[i] - v.r[i] <= h1) out.push(i);
    return out;
  }
  const gr = index.grilles[niv];
  const cx0 = Math.max(0, Math.floor((w0 - index.x0) / gr.cs));
  const cx1 = Math.min(gr.bw - 1, Math.floor((w1 - index.x0) / gr.cs) + 2);
  const cy0 = Math.max(0, Math.floor((h0 - index.y0) / gr.cs));
  const cy1 = Math.min(gr.bh - 1, Math.floor((h1 - index.y0) / gr.cs) + 2);
  const out = [];
  for (let cy = cy0; cy <= cy1; cy += 1) {
    for (let cx = cx0; cx <= cx1; cx += 1) {
      const c = cy * gr.bw + cx;
      for (let k = gr.bd[c]; k < gr.bd[c + 1]; k += 1) {
        const i = gr.ids[k];
        if (v.x[i] + v.r[i] >= w0 && v.x[i] - v.r[i] <= w1 && v.y[i] + v.r[i] >= h0 && v.y[i] - v.r[i] <= h1) out.push(i);
      }
    }
  }
  return out;
}

// Liens agrégés entre grappes visibles : échantillonnage spatial des liens de la zone.
export function liensBulles(index, niv, ids, w0, h0, w1, h1, garder = 240) {
  const g = index.g;
  const f = index.niveaux[0];
  const parId = new Map(ids.map((id, k) => [id, k]));
  const de = niv === 1 ? (i) => g.com[i] : niv === 2 ? (i) => g.comGrp[g.com[i]] : (i) => g.dom[i];
  const paires = new Map();
  const compter = (e) => {
    const a = parId.get(de(g.ea[e]));
    if (a === undefined) return;
    const b = parId.get(de(g.eb[e]));
    if (b === undefined || b === a) return;
    const cle = a < b ? a * 100000 + b : b * 100000 + a;
    paires.set(cle, (paires.get(cle) || 0) + 1);
  };
  const cx0 = Math.max(0, Math.floor((w0 - index.x0) / f.s)), cx1 = Math.min(f.gw - 1, Math.floor((w1 - index.x0) / f.s));
  const cy0 = Math.max(0, Math.floor((h0 - index.y0) / f.s)), cy1 = Math.min(f.gh - 1, Math.floor((h1 - index.y0) / f.s));
  if ((cx1 - cx0 + 1) * (cy1 - cy0 + 1) <= 6000) {
    let total = 0;
    for (let cy = cy0; cy <= cy1; cy += 1) for (let cx = cx0; cx <= cx1; cx += 1) { const c = cy * f.gw + cx; total += index.eDebut[c + 1] - index.eDebut[c]; }
    const pas = Math.max(1, Math.ceil(total / 20000));
    for (let cy = cy0; cy <= cy1; cy += 1) for (let cx = cx0; cx <= cx1; cx += 1) { const c = cy * f.gw + cx; for (let k = index.eDebut[c]; k < index.eDebut[c + 1]; k += pas) compter(index.eListe[k]); }
  } else {
    for (const e of index.echantillon) compter(e);
  }
  return [...paires.entries()].sort((p, q) => q[1] - p[1]).slice(0, garder).map(([cle, poids]) => ({ a: Math.floor(cle / 100000), b: cle % 100000, poids }));
}

// Niveau de grappes à afficher pour un zoom donné : le plus fin dont la grappe typique reste lisible (≥ 11 px de rayon).
// `fondu` : opacité (0..1) de l'ouverture vers le niveau inférieur — les enfants apparaissent progressivement.
export const RAYON_LISIBLE = 11;
export function niveauSemantique(g, zoom) {
  for (const niv of [1, 2, 3]) {
    if (g.niveaux[niv].rMed * zoom >= RAYON_LISIBLE) {
      const enfant = niv > 1 ? g.niveaux[niv - 1].rMed * zoom : 0;
      // Les enfants ne commencent à apparaître que lorsqu'ils font ~7 px de rayon : la vue d'ensemble reste nette
      const t = niv > 1 ? Math.max(0, Math.min(1, (enfant - 7) / (RAYON_LISIBLE - 7))) : 0;
      return { niv, fondu: t };
    }
  }
  return { niv: 3, fondu: 0 };
}
