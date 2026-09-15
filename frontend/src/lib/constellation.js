// Constellation décorative d'un territoire : micro-étoiles + filaments.
// Déterministe (graine = id du domaine) — rendu stable entre les recalculs de coque.
function mulberry32(graine) {
  let a = graine;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hacher(texte) {
  let h = 2166136261;
  for (let i = 0; i < texte.length; i++) { h ^= texte.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function dansPolygone(x, y, poly) {
  let dedans = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) dedans = !dedans;
  }
  return dedans;
}

export function genererConstellation(poly, w, h, idTexte, couleur) {
  if (!poly || poly.length < 3 || w < 40 || h < 40) return { points: [], liens: [] };
  const rand = mulberry32(hacher(String(idTexte)));
  const aire = Math.abs(poly.reduce((s, p, i) => {
    const q = poly[(i + 1) % poly.length];
    return s + p.x * q.y - q.x * p.y;
  }, 0)) / 2;
  const nb = Math.max(20, Math.min(64, Math.round(aire / 11000)));
  const points = [];
  let garde = 0;
  while (points.length < nb && garde++ < nb * 40) {
    const x = 12 + rand() * (w - 24);
    const y = 12 + rand() * (h - 24);
    if (!dansPolygone(x, y, poly)) continue;
    const brillante = rand() > 0.9;
    points.push({
      x, y,
      r: brillante ? 1.6 + rand() * 0.9 : 0.5 + rand() * 0.9,
      o: brillante ? 0.85 + rand() * 0.15 : 0.3 + rand() * 0.45,
      c: rand() < 0.72 ? "#E8F4F8" : couleur,
      halo: brillante,
      scintille: rand() < 0.16,
      duree: 3.5 + rand() * 4,
      delai: -rand() * 7,
    });
  }
  const liens = [];
  const vus = new Set();
  points.forEach((p, i) => {
    const proches = points
      .map((q, j) => ({ j, d: Math.hypot(p.x - q.x, p.y - q.y) }))
      .filter((e) => e.j !== i)
      .sort((a, b) => a.d - b.d);
    const prendre = proches.slice(0, 1);
    if (proches[1] && proches[1].d < 95 && rand() < 0.45) prendre.push(proches[1]);
    prendre.forEach(({ j, d }) => {
      const cle = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!proches.length || d > 130 || vus.has(cle)) return;
      vus.add(cle);
      liens.push({ x1: p.x, y1: p.y, x2: points[j].x, y2: points[j].y, o: 0.1 + rand() * 0.12 });
    });
  });
  return { points, liens };
}
