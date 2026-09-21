// Laboratoire de rendu du graphe — calculs purs (aucune dépendance React), inspirés de graphify :
//   • degré des nœuds (taille / importance des étiquettes)
//   • communautés calculées (Louvain) pour les comparer aux domaines déclarés
//   • disposition par forces, déterministe — pour PROPOSER un placement, jamais pour remplacer
//     les coordonnées stables de l'Atlas
// Tout est déterministe : mêmes données → mêmes résultats.

export const PALETTE_COMMUNAUTES = [
  "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
  "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
];

// ---------------------------------------------------------------------------------------------
// Degré
export function degres(ids, aretes) {
  const d = new Map(ids.map((id) => [id, 0]));
  aretes.forEach(({ source, cible }) => {
    if (d.has(source) && d.has(cible) && source !== cible) {
      d.set(source, d.get(source) + 1);
      d.set(cible, d.get(cible) + 1);
    }
  });
  return d;
}

// ---------------------------------------------------------------------------------------------
// Louvain (optimisation gloutonne de la modularité, agrégation itérée), graphe non orienté.
// Retourne { comm: Map(id → numéro de communauté, 0 = la plus grosse), modularite }.
export function louvain(ids, aretes) {
  const n = ids.length;
  const idx = new Map(ids.map((id, i) => [id, i]));
  const adj = Array.from({ length: n }, () => new Map());
  let m2 = 0; // 2 × poids total des liens
  aretes.forEach(({ source, cible }) => {
    const a = idx.get(source);
    const b = idx.get(cible);
    if (a == null || b == null || a === b) return;
    adj[a].set(b, (adj[a].get(b) || 0) + 1);
    adj[b].set(a, (adj[b].get(a) || 0) + 1);
    m2 += 2;
  });
  if (m2 === 0) return { comm: new Map(ids.map((id) => [id, 0])), modularite: 0 };

  let membres = ids.map((_, i) => [i]); // nœuds d'origine de chaque super-nœud
  let g = adj;
  let boucle = new Array(n).fill(0); // poids interne (compté des deux côtés)

  for (let niveau = 0; niveau < 10; niveau += 1) {
    const N = g.length;
    const k = g.map((nb, i) => [...nb.values()].reduce((s, w) => s + w, 0) + boucle[i]);
    const com = Array.from({ length: N }, (_, i) => i);
    const tot = k.slice();
    let ameliore = false;
    let passe = true;
    while (passe) {
      passe = false;
      for (let i = 0; i < N; i += 1) {
        const ci = com[i];
        const vers = new Map();
        g[i].forEach((w, j) => vers.set(com[j], (vers.get(com[j]) || 0) + w));
        tot[ci] -= k[i];
        let meilleure = ci;
        let gainMax = (vers.get(ci) || 0) - (tot[ci] * k[i]) / m2;
        [...vers.keys()].sort((a, b) => a - b).forEach((c) => {
          const gain = vers.get(c) - (tot[c] * k[i]) / m2;
          if (gain > gainMax + 1e-12) {
            gainMax = gain;
            meilleure = c;
          }
        });
        tot[meilleure] += k[i];
        if (meilleure !== ci) {
          com[i] = meilleure;
          passe = true;
          ameliore = true;
        }
      }
    }
    if (!ameliore) break;
    // agrégation : chaque communauté devient un super-nœud
    const renum = new Map();
    com.forEach((c) => {
      if (!renum.has(c)) renum.set(c, renum.size);
    });
    const M = renum.size;
    const nm = Array.from({ length: M }, () => []);
    const ng = Array.from({ length: M }, () => new Map());
    const nb = new Array(M).fill(0);
    for (let i = 0; i < N; i += 1) {
      const ci = renum.get(com[i]);
      nm[ci].push(...membres[i]);
      nb[ci] += boucle[i];
      g[i].forEach((w, j) => {
        const cj = renum.get(com[j]);
        if (ci === cj) nb[ci] += w;
        else ng[ci].set(cj, (ng[ci].get(cj) || 0) + w);
      });
    }
    membres = nm;
    g = ng;
    boucle = nb;
    if (M === N) break;
  }

  // numérotation stable : la plus grosse communauté d'abord
  const ordre = membres
    .map((mb, i) => ({ mb, i }))
    .sort((a, b) => b.mb.length - a.mb.length || Math.min(...a.mb) - Math.min(...b.mb));
  const comm = new Map();
  ordre.forEach(({ mb }, num) => mb.forEach((i) => comm.set(ids[i], num)));

  // modularité de la partition finale, sur le graphe d'origine
  const tot = new Map();
  const interne = new Map();
  for (let i = 0; i < n; i += 1) {
    const c = comm.get(ids[i]);
    const ki = [...adj[i].values()].reduce((s, w) => s + w, 0);
    tot.set(c, (tot.get(c) || 0) + ki);
    adj[i].forEach((w, j) => {
      if (comm.get(ids[j]) === c) interne.set(c, (interne.get(c) || 0) + w);
    });
  }
  let Q = 0;
  tot.forEach((t, c) => {
    Q += (interne.get(c) || 0) / m2 - (t / m2) ** 2;
  });
  return { comm, modularite: Q };
}

// Communautés nommées d'après leur domaine dominant — et écarts avec le domaine déclaré.
// Un jumeau est « en écart » quand sa communauté réelle est dominée par un AUTRE domaine que le sien.
export function decrireCommunautes(jumeaux, comm) {
  const parCom = new Map();
  jumeaux.forEach((j) => {
    const c = comm.get(j.id);
    if (!parCom.has(c)) parCom.set(c, []);
    parCom.get(c).push(j);
  });
  const communautes = [...parCom.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([cid, membres]) => {
      const compte = new Map();
      membres.forEach((j) => compte.set(j.domaine, (compte.get(j.domaine) || 0) + 1));
      const [dominant, nb] = [...compte.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))[0];
      return { cid, membres: membres.map((j) => j.id), domaineDominant: dominant, part: nb / membres.length };
    });
  // deux communautés dominées par le même domaine : suffixe pour les distinguer
  const vus = new Map();
  communautes.forEach((c) => {
    const n = (vus.get(c.domaineDominant) || 0) + 1;
    vus.set(c.domaineDominant, n);
    c.nom = n > 1 ? `${c.domaineDominant} ${n}` : c.domaineDominant;
  });
  const parId = new Map(communautes.map((c) => [c.cid, c]));
  const ecarts = new Set(jumeaux.filter((j) => parId.get(comm.get(j.id))?.domaineDominant !== j.domaine).map((j) => j.id));
  return { communautes, ecarts };
}

// ---------------------------------------------------------------------------------------------
// Disposition par forces (répulsion + ressorts + gravité douce), déterministe, refroidie.
// `depart` : Map(id → {x, y}). Retourne Map(id → {x, y}).
// Sert à PROPOSER un placement : les jumeaux fortement liés se rapprochent, l'espace se réorganise
// par couplage réel. Une distance minimale garantit l'absence de chevauchement.
export function dispositionForce(depart, aretes, { iterations = 320, distMin = 105, longueur = 130 } = {}) {
  const ids = [...depart.keys()];
  const P = new Map(ids.map((id) => [id, { ...depart.get(id), vx: 0, vy: 0 }]));
  const liens = aretes.filter((a) => P.has(a.source) && P.has(a.cible) && a.source !== a.cible);
  let cx = 0;
  let cy = 0;
  ids.forEach((id) => {
    cx += P.get(id).x / ids.length;
    cy += P.get(id).y / ids.length;
  });

  const liste = ids.map((id) => P.get(id));
  const repulsion = (i, j) => {
    const a = liste[i];
    const b = liste[j];
    let dx = b.x - a.x;
    let dy = b.y - a.y;
    // jumeaux confondus : direction déterministe
    if (dx === 0 && dy === 0) {
      dx = ((i * 7 + j * 3) % 5) - 2 || 1;
      dy = ((i * 3 + j * 5) % 5) - 2 || 1;
    }
    const d2 = dx * dx + dy * dy + 0.01;
    const d = Math.sqrt(d2);
    const f = 26000 / d2;
    a.vx -= (dx / d) * f;
    a.vy -= (dy / d) * f;
    b.vx += (dx / d) * f;
    b.vy += (dy / d) * f;
  };
  // Au-delà de 200 jumeaux la répulsion exacte (quadratique) devient prohibitive : on ne repousse que les
  // voisins proches, via une grille spatiale (portée = 3 cellules de CELLULE px) — coût ~ linéaire.
  const GRAND = ids.length > 200;
  const CELLULE = 220;

  for (let it = 0; it < iterations; it += 1) {
    const T = 1 - it / iterations; // température : les déplacements se calment
    if (!GRAND) {
      for (let i = 0; i < liste.length; i += 1) for (let j = i + 1; j < liste.length; j += 1) repulsion(i, j);
    } else {
      const grille = new Map();
      liste.forEach((p, i) => {
        const cle = Math.floor(p.x / CELLULE) * 100003 + Math.floor(p.y / CELLULE);
        if (!grille.has(cle)) grille.set(cle, []);
        grille.get(cle).push(i);
      });
      liste.forEach((p, i) => {
        const gx = Math.floor(p.x / CELLULE);
        const gy = Math.floor(p.y / CELLULE);
        for (let ox = -1; ox <= 1; ox += 1) {
          for (let oy = -1; oy <= 1; oy += 1) {
            const cell = grille.get((gx + ox) * 100003 + (gy + oy));
            if (cell) cell.forEach((j) => { if (j > i) repulsion(i, j); });
          }
        }
      });
    }
    liens.forEach(({ source, cible }) => {
      const a = P.get(source);
      const b = P.get(cible);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1;
      const f = 0.07 * (d - longueur);
      a.vx += (dx / d) * f;
      a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f;
      b.vy -= (dy / d) * f;
    });
    ids.forEach((id) => {
      const p = P.get(id);
      p.vx += (cx - p.x) * 0.004; // gravité douce vers le centre
      p.vy += (cy - p.y) * 0.004;
      const v = Math.hypot(p.vx, p.vy) || 1;
      const borne = 26 * T + 1.5;
      const k = v > borne ? borne / v : 1;
      p.x += p.vx * k;
      p.y += p.vy * k;
      p.vx *= 0.55;
      p.vy *= 0.55;
    });
  }

  // séparation finale : jamais deux jumeaux à moins de distMin
  for (let passe = 0; passe < 40; passe += 1) {
    let bouge = false;
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = P.get(ids[i]);
        const b = P.get(ids[j]);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 0.01;
        if (d < distMin) {
          const ecart = (distMin - d) / 2;
          const ux = d < 0.02 ? 1 : dx / d;
          const uy = d < 0.02 ? 0 : dy / d;
          a.x -= ux * ecart;
          a.y -= uy * ecart;
          b.x += ux * ecart;
          b.y += uy * ecart;
          bouge = true;
        }
      }
    }
    if (!bouge) break;
  }
  return new Map(ids.map((id) => [id, { x: P.get(id).x, y: P.get(id).y }]));
}

// ---------------------------------------------------------------------------------------------
// Mesh SYNTHÉTIQUE pour tester le passage à l'échelle (100, 500, 1 000 jumeaux…).
// Même structure que le vrai Mesh : domaines de tailles inégales, hubs (attachement préférentiel),
// liens surtout internes + liens transverses, mêmes états de relation, ~1,2 lien par jumeau.
// Déterministe (graine fixe). La densité reste constante : plus il y a de jumeaux, plus la carte
// s'étend (≥ 105 px entre jumeaux), comme dans l'Atlas.
export const DOMAINES_ETENDUS = {
  "Conformité": "#A3E635", "Données": "#22D3EE", "Marketing": "#F472B6", "Finance": "#FBBF24", "Juridique": "#C084FC", "Logistique": "#2DD4BF",
};
const NOMS_DOMAINES = ["Client", "Paiement", "Distribution", "Opérations", "Risque", "Support", ...Object.keys(DOMAINES_ETENDUS)];
const ETATS = [["confirmee", 0.56], ["observee", 0.31], ["supposee", 0.07], ["validation", 0.02], ["contestee", 0.02], ["obsolete", 0.02]];

function alea(graine) {
  let s = graine >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

export function genererMesh(n, graine = 7) {
  const rnd = alea(graine + n);
  const D = n <= 120 ? 6 : n <= 600 ? 10 : 12;
  const domaines = NOMS_DOMAINES.slice(0, D);
  // tailles de domaines inégales (poids aléatoires), somme = n
  const poids = domaines.map(() => 0.5 + rnd());
  const somme = poids.reduce((a, b) => a + b, 0);
  const tailles = poids.map((p) => Math.max(2, Math.round((p / somme) * n)));
  while (tailles.reduce((a, b) => a + b, 0) > n) tailles[tailles.indexOf(Math.max(...tailles))] -= 1;
  while (tailles.reduce((a, b) => a + b, 0) < n) tailles[tailles.indexOf(Math.min(...tailles))] += 1;

  // disposition : chaque domaine sur une spirale de Vogel (≈ 120 px entre voisins), domaines sur une grille
  const PAS = 86; // ≈ 110 px entre voisins sur la spirale : la règle des 105 px de l'Atlas tient
  const rayons = tailles.map((m) => PAS * Math.sqrt(m) + 70);
  const cellule = 2 * Math.max(...rayons) + 160;
  const colonnes = Math.ceil(Math.sqrt(D));
  const jumeaux = [];
  const parDomaine = domaines.map(() => []);
  let idx = 0;
  domaines.forEach((d, di) => {
    const cx = (di % colonnes) * cellule;
    const cy = Math.floor(di / colonnes) * cellule;
    for (let k = 0; k < tailles[di]; k += 1) {
      const angle = k * 2.399963 + rnd() * 0.15;
      const r = PAS * Math.sqrt(k + 0.5);
      const id = `s${idx}`;
      jumeaux.push({
        id,
        nom: `${d} ${k + 1}`,
        domaine: d,
        position: { x: Math.round(cx + Math.cos(angle) * r), y: Math.round(cy + Math.sin(angle) * r) },
        couverture: 40 + Math.floor(rnd() * 58),
        fraicheur: `il y a ${1 + Math.floor(rnd() * 59)} min`,
        mission: `Application synthétique ${idx} du domaine ${d}.`,
      });
      parDomaine[di].push(id);
      idx += 1;
    }
  });

  // liens : attachement préférentiel dans le domaine, puis liens transverses vers les hubs
  const degre = new Map(jumeaux.map((j) => [j.id, 0]));
  const vus = new Set();
  const relations = [];
  const choisirEtat = () => {
    let t = rnd();
    for (const [e, p] of ETATS) {
      t -= p;
      if (t <= 0) return e;
    }
    return "confirmee";
  };
  const lier = (a, b) => {
    if (a === b) return;
    const cle = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (vus.has(cle)) return;
    vus.add(cle);
    relations.push({ id: `r${relations.length}`, source: a, cible: b, etat: choisirEtat() });
    degre.set(a, degre.get(a) + 1);
    degre.set(b, degre.get(b) + 1);
  };
  const piocher = (ids) => {
    // tirage proportionnel à (degré + 1) : les hubs se forment
    let total = 0;
    ids.forEach((i) => { total += degre.get(i) + 1; });
    let t = rnd() * total;
    for (const i of ids) {
      t -= degre.get(i) + 1;
      if (t <= 0) return i;
    }
    return ids[ids.length - 1];
  };
  parDomaine.forEach((ids) => {
    for (let k = 1; k < ids.length; k += 1) lier(ids[k], piocher(ids.slice(0, k)));
    const extras = Math.round(ids.length * 0.12);
    for (let e = 0; e < extras; e += 1) lier(piocher(ids), piocher(ids));
  });
  const tous = jumeaux.map((j) => j.id);
  const transverses = Math.round(n * 0.33);
  for (let t = 0; t < transverses; t += 1) lier(piocher(tous), piocher(tous));

  // situations : petits groupes de jumeaux de domaines différents
  const situations = Array.from({ length: Math.max(4, Math.round(n / 12)) }, (_, i) => ({
    id: `sit-${i}`,
    titre: `Situation synthétique ${i + 1}`,
    jumeaux: Array.from({ length: 2 + Math.floor(rnd() * 3) }, () => tous[Math.floor(rnd() * tous.length)]),
  }));
  return { mesh: { jumeaux, relations, regions: [] }, situations };
}
