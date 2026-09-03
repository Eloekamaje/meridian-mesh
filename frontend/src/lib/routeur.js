// Moteur de routage orthogonal (Manhattan) dédié — jamais de ligne directe centre à centre.
// Dégagement aux ports, canaux anti-obstacles, cache de stabilité, ponts aux croisements.

const DEGAGEMENT = 18; // section droite après le départ du robot (12–20 px)
export const RAYON_COIN = 6; // angles à 90° légèrement arrondis (4–8 px)

const VECTEURS = { r: [1, 0], l: [-1, 0], t: [0, -1], b: [0, 1] };

// Sélection automatique des ports selon la direction dominante de la destination
export function choixCotes(cs, ct) {
  const dx = ct.x - cs.x;
  const dy = ct.y - cs.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? ["r", "l"] : ["l", "r"];
  return dy >= 0 ? ["b", "t"] : ["t", "b"];
}

export function pointPort(c, cote, marge = 26) {
  const [vx, vy] = VECTEURS[cote];
  // Le bas demande une marge plus grande : le port doit se situer SOUS l'App ID,
  // pas au niveau de l'avatar (sinon l'arête traverse l'étiquette)
  const m = cote === "b" ? (c.margeBas ?? marge) : marge;
  return { x: c.x + vx * m, y: c.y + vy * m };
}

const avancer = (p, cote, d) => ({ x: p.x + VECTEURS[cote][0] * d, y: p.y + VECTEURS[cote][1] * d });

function segCoupeRect(a, b, r) {
  if (a.x === b.x) {
    if (a.x <= r.x0 || a.x >= r.x1) return false;
    return Math.min(a.y, b.y) < r.y1 && Math.max(a.y, b.y) > r.y0;
  }
  if (a.y === b.y) {
    if (a.y <= r.y0 || a.y >= r.y1) return false;
    return Math.min(a.x, b.x) < r.x1 && Math.max(a.x, b.x) > r.x0;
  }
  return false;
}

function heurteObstacles(pts, obstacles) {
  let n = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    for (const o of obstacles) if (segCoupeRect(pts[i], pts[i + 1], o)) n += 1;
  }
  return n;
}

function longueur(pts) {
  let L = 0;
  for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  return L;
}

// Retire doublons et points colinéaires
function epurer(pts) {
  const out = [];
  for (const p of pts) {
    const d = out[out.length - 1];
    if (d && d.x === p.x && d.y === p.y) continue;
    const d2 = out[out.length - 2];
    if (d2 && d && ((d2.x === d.x && d.x === p.x) || (d2.y === d.y && d.y === p.y))) out.pop();
    out.push(p);
  }
  return out;
}

// Route orthogonale : dégagement aux ports, puis trajet le plus simple qui évite les obstacles
export function routeOrthogonale(cs, ct, coteS, coteT, obstacles, decalage = 0) {
  const s0 = pointPort(cs, coteS, cs.marge ?? 26);
  const t0 = pointPort(ct, coteT, ct.marge ?? 26);
  const s1 = avancer(s0, coteS, DEGAGEMENT);
  const t1 = avancer(t0, coteT, DEGAGEMENT);
  const mx = (s1.x + t1.x) / 2 + decalage;
  const my = (s1.y + t1.y) / 2 + decalage;
  const candidats = [
    [s0, s1, { x: t1.x, y: s1.y }, t1, t0], // L horizontal-vertical
    [s0, s1, { x: s1.x, y: t1.y }, t1, t0], // L vertical-horizontal
    [s0, s1, { x: mx, y: s1.y }, { x: mx, y: t1.y }, t1, t0], // Z par canal vertical médian
    [s0, s1, { x: s1.x, y: my }, { x: t1.x, y: my }, t1, t0], // Z par canal horizontal médian
  ];
  // Canaux supplémentaires : espaces libres autour des obstacles (couloirs de circulation)
  for (const o of obstacles) {
    candidats.push([s0, s1, { x: o.x0 - 16, y: s1.y }, { x: o.x0 - 16, y: t1.y }, t1, t0]);
    candidats.push([s0, s1, { x: o.x1 + 16, y: s1.y }, { x: o.x1 + 16, y: t1.y }, t1, t0]);
    candidats.push([s0, s1, { x: s1.x, y: o.y0 - 16 }, { x: t1.x, y: o.y0 - 16 }, t1, t0]);
    candidats.push([s0, s1, { x: s1.x, y: o.y1 + 16 }, { x: t1.x, y: o.y1 + 16 }, t1, t0]);
  }
  let meilleur = null;
  let meilleurScore = Infinity;
  for (const c of candidats) {
    const pts = epurer(c);
    if (pts.length < 2) continue;
    // Priorité : éviter les robots, puis limiter les coudes, puis la longueur
    const sc = heurteObstacles(pts, obstacles) * 10000 + (pts.length - 2) * 8 + longueur(pts) / 50;
    if (sc < meilleurScore) {
      meilleurScore = sc;
      meilleur = pts;
    }
  }
  return meilleur;
}

// Stabilité des tracés : recalcul seulement si les extrémités ou l'environnement changent
const cache = new Map();
export function routeStable(id, cs, ct, coteS, coteT, obstacles, decalage = 0) {
  const cle = `${Math.round(cs.x)}:${Math.round(cs.y)}:${Math.round(ct.x)}:${Math.round(ct.y)}:${coteS}${coteT}:${Math.round(decalage)}:${obstacles.length}`;
  const entree = cache.get(id);
  if (entree && entree.cle === cle) return entree.points;
  const points = routeOrthogonale(cs, ct, coteS, coteT, obstacles, decalage);
  cache.set(id, { cle, points });
  return points;
}

// Croisements : la relation la moins prioritaire effectue un petit pont arrondi
export function detecterCroisements(routes) {
  const sauts = {};
  const segments = routes.map((r) => {
    const hs = [];
    const vs = [];
    for (let i = 0; i < r.points.length - 1; i++) {
      const a = r.points[i];
      const b = r.points[i + 1];
      if (a.y === b.y && a.x !== b.x) hs.push([a, b]);
      else if (a.x === b.x && a.y !== b.y) vs.push([a, b]);
    }
    return { id: r.id, priorite: r.priorite, hs, vs };
  });
  const croise = (h, v) => {
    const x = v[0].x;
    const y = h[0].y;
    return x > Math.min(h[0].x, h[1].x) && x < Math.max(h[0].x, h[1].x) && y > Math.min(v[0].y, v[1].y) && y < Math.max(v[0].y, v[1].y)
      ? { x, y }
      : null;
  };
  for (let i = 0; i < segments.length; i++) {
    for (let j = i + 1; j < segments.length; j++) {
      const A = segments[i];
      const B = segments[j];
      for (const h of A.hs) {
        for (const v of B.vs) {
          const p = croise(h, v);
          if (p) {
            const perdant = A.priorite <= B.priorite ? { id: B.id, horizontale: false } : { id: A.id, horizontale: true };
            (sauts[perdant.id] = sauts[perdant.id] || []).push({ ...p, horizontale: perdant.horizontale });
          }
        }
      }
      for (const v of A.vs) {
        for (const h of B.hs) {
          const p = croise(h, v);
          if (p) {
            const perdant = A.priorite <= B.priorite ? { id: A.id, horizontale: false } : { id: B.id, horizontale: true };
            (sauts[perdant.id] = sauts[perdant.id] || []).push({ ...p, horizontale: perdant.horizontale });
          }
        }
      }
    }
  }
  // Ponts discrets : 2 maximum par arête, espacés
  for (const id of Object.keys(sauts)) {
    sauts[id] = sauts[id]
      .filter((s, i, arr) => arr.findIndex((o) => Math.hypot(o.x - s.x, o.y - s.y) < 20) === i)
      .slice(0, 2);
  }
  return sauts;
}

const surSegment = (s, a, b) =>
  (a.y === b.y && s.y === a.y && s.x > Math.min(a.x, b.x) + 6 && s.x < Math.max(a.x, b.x) - 6) ||
  (a.x === b.x && s.x === a.x && s.y > Math.min(a.y, b.y) + 6 && s.y < Math.max(a.y, b.y) - 6);

// Construction du chemin SVG : coins arrondis + ponts aux croisements (jamais de diagonale)
export function construireD(points, sauts = [], rayon = RAYON_COIN) {
  if (!points || points.length < 2) return "";
  const cmds = [`M ${points[0].x} ${points[0].y}`];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const dirx = Math.sign(b.x - a.x);
    const diry = Math.sign(b.y - a.y);
    const horizontal = a.y === b.y;
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    const rA = i > 0 ? Math.min(rayon, len / 2.5) : 0;
    const rB = i < points.length - 2 ? Math.min(rayon, len / 2.5) : 0;
    const debut = { x: a.x + dirx * rA, y: a.y + diry * rA };
    const fin = { x: b.x - dirx * rB, y: b.y - diry * rB };
    const saut = sauts.find((s) => surSegment(s, debut, fin));
    if (i > 0) cmds.push(`L ${debut.x} ${debut.y}`);
    if (saut) {
      if (horizontal) {
        cmds.push(`L ${saut.x - dirx * 7} ${debut.y}`);
        cmds.push(`Q ${saut.x} ${debut.y - 7} ${saut.x + dirx * 7} ${debut.y}`);
      } else {
        cmds.push(`L ${debut.x} ${saut.y - diry * 7}`);
        cmds.push(`Q ${debut.x + 7} ${saut.y} ${debut.x} ${saut.y + diry * 7}`);
      }
    }
    cmds.push(`L ${fin.x} ${fin.y}`);
    if (rB > 0) {
      const suivant = points[i + 2];
      const nx = Math.sign(suivant.x - b.x);
      const ny = Math.sign(suivant.y - b.y);
      cmds.push(`Q ${b.x} ${b.y} ${b.x + nx * rB} ${b.y + ny * rB}`);
    }
  }
  return cmds.join(" ");
}

// Ancre du libellé : milieu du segment horizontal le plus long (jamais sur un angle)
export function ancreLabel(points) {
  let meilleur = null;
  let max = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const L = Math.hypot(b.x - a.x, b.y - a.y);
    const horizontal = a.y === b.y;
    const score = horizontal ? L : L * 0.4;
    if (score > max) {
      max = score;
      meilleur = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, horizontal };
    }
  }
  return meilleur;
}

// Marqueurs directionnels espacés le long du trajet (relations observées)
export function pointsMarqueurs(points, fractions = [0.38, 0.66]) {
  const total = longueur(points);
  if (total < 60) return [];
  const res = [];
  let acc = 0;
  let fi = 0;
  for (let i = 0; i < points.length - 1 && fi < fractions.length; i++) {
    const a = points[i];
    const b = points[i + 1];
    const L = Math.hypot(b.x - a.x, b.y - a.y);
    while (fi < fractions.length && acc + L >= fractions[fi] * total) {
      const t = (fractions[fi] * total - acc) / L;
      res.push({
        x: a.x + (b.x - a.x) * t,
        y: a.y + (b.y - a.y) * t,
        angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI,
      });
      fi += 1;
    }
    acc += L;
  }
  return res;
}

// Décalage des arêtes qui partagent un même port (espacement 5–8 px)
export function decalagesParalleles(relations, choix) {
  const groupes = {};
  relations.forEach((r) => {
    const c = choix[r.id];
    if (!c) return;
    const cleS = `${r.source}|${c[0]}`;
    const cleT = `${r.cible}|${c[1]}`;
    (groupes[cleS] = groupes[cleS] || []).push(r.id);
    (groupes[cleT] = groupes[cleT] || []).push(r.id);
  });
  const decal = {};
  Object.values(groupes).forEach((g) => {
    if (g.length < 2) return;
    g.forEach((id, i) => {
      decal[id] = (decal[id] || 0) + (i - (g.length - 1) / 2) * 7;
    });
  });
  return decal;
}
