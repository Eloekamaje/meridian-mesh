import { MarkerType } from "@xyflow/react";
import concaveman from "concaveman";
import { couleurDomaine } from "@/lib/domaines";
import { choixCotes, routeStable, routeCorridor, gonflePolygone, sortiesPolys, detecterCroisements, decalagesParalleles, ancreLabel } from "./routeur";

export const COUCHES = [
  ["operationnelle", "Opérationnelle", "#9B87F5"],
  ["connaissance", "Connaissance", "#25D0C8"],
  ["mesh", "Mesh", "#9B87F5"],
];

export const NIVEAUX_ZOOM = { 1: "Global", 2: "Domaine", 3: "Jumeau", 4: "Composants & preuves" };

// Moteur de priorité des labels (façon Google Maps) : en cas de chevauchement,
// le label le moins prioritaire disparaît. candidats = [{id, x, y, w, h, priorite}]
// (coordonnées monde, x/y = CENTRE). obstacles = rectangles déjà occupés
// (ex. robots + App ID) qu'aucun label ne peut recouvrir — sauf celui de même id
// (un jumeau ne se masque jamais lui-même). Retourne les ids visibles.
export function placerLabels(candidats, obstacles = []) {
  const places = obstacles.map((o) => ({ id: o.id, x0: o.x - o.w / 2, y0: o.y - o.h / 2, x1: o.x + o.w / 2, y1: o.y + o.h / 2 }));
  const visibles = new Set();
  const trie = [...candidats].sort((a, b) => b.priorite - a.priorite);
  for (const c of trie) {
    const r = { x0: c.x - c.w / 2, y0: c.y - c.h / 2, x1: c.x + c.w / 2, y1: c.y + c.h / 2 };
    const collision = places.some((p) => p.id !== c.id && r.x0 < p.x1 && r.x1 > p.x0 && r.y0 < p.y1 && r.y1 > p.y0);
    if (!collision) {
      places.push({ id: c.id, ...r });
      visibles.add(c.id);
    }
  }
  return visibles;
}

// Identifiant numérique court affiché au-dessus du robot (le nom reste hors de la carte)
export const idNumerique = (id) => {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 100003;
  return String(1000 + (h % 9000));
};

// --- Membrane polygonale : coque CONCAVE (alpha-shape) des avatars, angles adoucis ---
// Élastique par construction : recalculée à chaque déplacement/ajout/suppression de nœud.
// La géométrie ne dépend que des centres des avatars — jamais des labels ou infobulles.
function hullConvexe(pts) {
  const P = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
  if (P.length <= 2) return P;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const bas = [];
  const haut = [];
  for (const p of P) {
    while (bas.length >= 2 && cross(bas[bas.length - 2], bas[bas.length - 1], p) <= 0) bas.pop();
    bas.push(p);
  }
  for (let i = P.length - 1; i >= 0; i--) {
    const p = P[i];
    while (haut.length >= 2 && cross(haut[haut.length - 2], haut[haut.length - 1], p) <= 0) haut.pop();
    haut.push(p);
  }
  bas.pop();
  haut.pop();
  return bas.concat(haut);
}

// Coins adoucis (quadratiques) mais géométrie clairement polygonale
function arrondiCoins(pts, r = 12) {
  const n = pts.length;
  if (n < 3) return "";
  const seg = pts.map((p, i) => {
    const q = pts[(i + 1) % n];
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const len = Math.hypot(dx, dy) || 1;
    return { ux: dx / len, uy: dy / len, len };
  });
  let d = "";
  for (let i = 0; i < n; i++) {
    const p = pts[i];
    const sPrev = seg[(i - 1 + n) % n];
    const sNext = seg[i];
    const rc = Math.min(r, sPrev.len / 2.5, sNext.len / 2.5);
    const ax = p.x - sPrev.ux * rc;
    const ay = p.y - sPrev.uy * rc;
    const bx = p.x + sNext.ux * rc;
    const by = p.y + sNext.uy * rc;
    d += i === 0 ? `M ${ax} ${ay}` : ` L ${ax} ${ay}`;
    d += ` Q ${p.x} ${p.y} ${bx} ${by}`;
  }
  return `${d} Z`;
}

export function coqueOrganique(centres, marge = 50) {
  if (!centres.length) return null;
  // Chaque avatar est gonflé (rayon ≈ avatar + 26 px) : membrane territoriale, marge généreuse
  const gonfle = [];
  centres.forEach((p) => {
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * 2 * Math.PI;
      gonfle.push([p.x + Math.cos(a) * marge, p.y + Math.sin(a) * marge]);
    }
  });
  let poly;
  try {
    // Concavité 3.6 (vs 2.2) : baies douces — une membrane trop concave crée des
    // criques qu'une relation interne orthogonale ne peut pas longer sans sortir.
    // concaveman aussi à 2 membres : sommets polygonaux perceptibles au lieu d'une capsule lisse
    poly = centres.length === 1
      ? hullConvexe(gonfle.map(([x, y]) => ({ x, y })))
      : concaveman(gonfle, 3.6, 52).map(([x, y]) => ({ x, y }));
  } catch {
    poly = hullConvexe(gonfle.map(([x, y]) => ({ x, y })));
  }
  if (poly.length < 3) return null;
  const cx = centres.reduce((a, p) => a + p.x, 0) / centres.length;
  const cy = centres.reduce((a, p) => a + p.y, 0) / centres.length;
  const xs = poly.map((p) => p.x);
  const ys = poly.map((p) => p.y);
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  const rel = poly.map((p) => ({ x: p.x - x0, y: p.y - y0 }));
  // Titre du domaine : au centre pour un territoire étendu, décalé perpendiculairement au flux pour 2 membres
  let labelX;
  let labelY;
  if (centres.length === 1) {
    labelX = centres[0].x - x0;
    labelY = centres[0].y - y0 - 50;
  } else if (centres.length === 2) {
    const [a, b] = centres;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const L = Math.hypot(dx, dy) || 1;
    labelX = (a.x + b.x) / 2 - x0 + (-dy / L) * 32;
    labelY = (a.y + b.y) / 2 - y0 + (dx / L) * 32;
  } else {
    labelX = cx - x0;
    labelY = cy - y0;
  }
  return {
    x: x0,
    y: y0,
    w: Math.max(...xs) - x0,
    h: Math.max(...ys) - y0,
    path: arrondiCoins(rel, 14),
    points: rel,
    labelX,
    labelY,
  };
}

// Ancre sur la FRONTIÈRE d'un territoire : point de SORTIE du rayon
// capitale → capitale à travers la coque concave. Un sommet choisi par simple
// proximité peut être au fond d'une baie concave → l'arc s'enfoncerait dans le
// territoire ; le point de sortie du rayon est toujours sur le bord qui FAIT FACE
// à l'autre domaine.
function ancreFrontiere(reg, cx, cy) {
  const ox = reg.lx;
  const oy = reg.ly;
  const dx = cx - ox;
  const dy = cy - oy;
  const L = Math.hypot(dx, dy) || 1;
  const ux = dx / L;
  const uy = dy / L;
  let tMax = -1;
  const pts = reg.pts || [];
  for (let i = 0; i < pts.length; i++) {
    const ax = pts[i].x + reg.ox;
    const ay = pts[i].y + reg.oy;
    const bx = pts[(i + 1) % pts.length].x + reg.ox;
    const by = pts[(i + 1) % pts.length].y + reg.oy;
    const ex = bx - ax;
    const ey = by - ay;
    const den = ux * ey - uy * ex;
    if (Math.abs(den) < 1e-9) continue;
    const t = ((ax - ox) * ey - (ay - oy) * ex) / den;
    const s = ((ax - ox) * uy - (ay - oy) * ux) / den;
    if (t > 0 && s >= 0 && s <= 1 && t > tMax) tMax = t;
  }
  if (tMax > 0) {
    // infime retrait vers la capitale : l'arc touche la frontière sans la dépasser
    return { x: ox + ux * tMax * 0.995, y: oy + uy * tMax * 0.995 };
  }
  // Secours (capitale hors de la coque, rayon ne la croise pas) : sommet le plus proche
  let b = null;
  let dMin = Infinity;
  pts.forEach((p) => {
    const wx = reg.ox + p.x;
    const wy = reg.oy + p.y;
    const d = Math.hypot(wx - cx, wy - cy);
    if (d < dMin) { dMin = d; b = { x: wx, y: wy }; }
  });
  return b ? { x: b.x + (ox - b.x) * 0.02, y: b.y + (oy - b.y) * 0.02 } : null;
}


// `attenue` : état visuel propre à une scène pilotée — la relation reste lisible mais
// passe au second plan. Absent des relations du produit : comportement inchangé.
export const styleParEtat = (r) => {
  const base = styleDeBase(r);
  return r.attenue ? { ...base, opacity: (base.opacity ?? 1) * 0.35, strokeWidth: Math.max(1, (base.strokeWidth ?? 1) * 0.8) } : base;
};

const styleDeBase = (r) => {
  switch (r.etat) {
    // Réalité découverte : ligne turquoise continue + marqueur directionnel (dans makeEdge)
    case "observee":
      return { stroke: "#25D0C8", strokeWidth: 2 };
    // Écarts (contradictoire ou à qualifier) : pointillés orange
    case "supposee":
      return { stroke: "#F2B84B", strokeWidth: 1.7, strokeDasharray: "6 6", opacity: 0.9 };
    case "contestee":
      return { stroke: "#F2B84B", strokeWidth: 2, strokeDasharray: "6 6" };
    case "validation":
      return { stroke: "#9B87F5", strokeWidth: 1.8, strokeDasharray: "7 5" };
    case "obsolete":
      return { stroke: "rgba(148,163,184,0.65)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25 };
    // BCM déclaré : ligne gris ardoise continue
    default:
      return { stroke: r.active ? "#9B87F5" : "rgba(148,163,184,0.7)", strokeWidth: 1.3, opacity: r.active ? 0.9 : 0.6 };
  }
};

// --- Routage : routeur maison (provisoire/secours) + routeur final libavoid en Web Worker ---
// Priorité de routage (spec) : contestée > observée/validation > supposée > déclarée > obsolète
const PRIORITES = { contestee: 80, validation: 60, observee: 60, supposee: 50, confirmee: 40, obsolete: 20 };

// Nos côtés de handles (r/l/t/b) ↔ ports libavoid (e/w/n/s)
const COTE_VERS_PORT = { r: "e", l: "w", t: "n", b: "s" };

// Regroupement visuel désactivé (choix utilisateur) : tous les jumeaux restent individuels
const SEUIL_DENSITE = 5; // conservé pour référence historique, non utilisé
const RAYON_GRAPPE = 130;
const VISIBLES_PAR_DOMAINE = 2;

function clusteriser(twins, posDe, zoomNiveau) {
  return { clusters: {}, groupes: [] };
}

// Centre de l'avatar (ou de la pastille) selon la variante de nœud.
// margeBas : le port du bas se place SOUS l'étiquette App ID (jamais à travers).
function ancreJumeau(j, pos) {
  if (j?.porte) return { x: pos.x + 30, y: pos.y + 8, marge: 12 };
  if (j?.anonyme) return { x: pos.x + 30, y: pos.y + 10, marge: 12, margeBas: 46 };
  return { x: pos.x + 32, y: pos.y + 26, marge: 28, margeBas: 50 };
}

// Obstacles = rectangles des robots (avatar + App ID + dégagement), extrémités exclues — routeur maison
function obstaclesDe(ns, exclure) {
  return ns
    .filter((n) => n.type === "twin" && !n.data?.jumeau?.porte && !n.data?.jumeau?.anonyme && !exclure.has(n.id))
    .map((n) => {
      if (!n.data?.detailVisible) return { x0: n.position.x - 16, y0: n.position.y - 8, x1: n.position.x + 76, y1: n.position.y + 84 };
      return n.data.detailPosition === "haut"
        ? { x0: n.position.x + 32 - 80, y0: n.position.y - 111, x1: n.position.x + 32 + 80, y1: n.position.y + 80 }
        : { x0: n.position.x + 32 - 80, y0: n.position.y - 8, x1: n.position.x + 32 + 80, y1: n.position.y + 182 };
    });
}

// Anti-collision déterministe : écarte les jumeaux qui se chevauchent (principe du zéro chevauchement)
function separerNoeuds(twins, posOverrides = {}) {
  const pos = {};
  const pts = twins.map((j) => {
    const p = posOverrides[j.id] || j.position;
    pos[j.id] = { ...p };
    return { id: j.id, x: p.x + 30, y: p.y + 40 };
  });

  const MIN_DIST = 105; // avatar (max 56px) + étiquettes + marge de sécurité
  for (let iter = 0; iter < 20; iter++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let k = i + 1; k < pts.length; k++) {
        const dx = pts[k].x - pts[i].x;
        const dy = pts[k].y - pts[i].y;
        const dist = Math.hypot(dx, dy);
        if (dist < MIN_DIST) {
          // Angle déterministe (spirale de Fibonacci) si les nœuds sont parfaitement superposés
          const angle = dist === 0 ? (i * 137.5 * Math.PI) / 180 : Math.atan2(dy, dx);
          const push = (MIN_DIST - dist) / 2 + 2;
          pts[i].x -= Math.cos(angle) * push;
          pts[i].y -= Math.sin(angle) * push;
          pts[k].x += Math.cos(angle) * push;
          pts[k].y += Math.sin(angle) * push;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }

  pts.forEach((p) => {
    pos[p.id] = { x: p.x - 30, y: p.y - 40 };
  });
  return pos;
}

// Géométrie d'un nœud jumeau pour le routeur final : forme connectable (avatar/pastille, ports N/E/S/W)
// + obstacles non connectables (App ID, pastille de passerelle)
function geometrieNoeud(n) {
  const pos = n.position;
  const j = n.data?.jumeau || {};

  if (j.porte || j.anonyme) {
    // Anonyme = pastille 16px + App ID + "résumé" en bas (+ 4px de marge).
    // La forme englobe tout le bloc pour que les arêtes s'attachent tout en bas.
    const lw = Math.max(16, 4 * 7 + 10);
    return {
      forme: { id: n.id, x0: pos.x + 30 - lw / 2, y0: pos.y, x1: pos.x + 30 + lw / 2, y1: pos.y + 56 },
      obstacles: [],
    };
  }

  const grand = (n.data?.niveau || 2) >= 3;

  // Niveau 4 : la carte « composants & preuves » fait partie de la forme connectable,
  // en dessous OU au-dessus du robot selon l'arbitrage (detailPosition)
  if (n.data?.detailVisible) {
    const haut = n.data.detailPosition === "haut";
    return {
      forme: haut
        ? { id: n.id, x0: pos.x + 32 - 76, y0: pos.y - 107, x1: pos.x + 32 + 76, y1: pos.y + 78 }
        : { id: n.id, x0: pos.x + 32 - 76, y0: pos.y, x1: pos.x + 32 + 76, y1: pos.y + 178 },
      obstacles: [],
    };
  }

  const w = grand ? 56 : 48;
  const x0 = pos.x + (64 - w) / 2;
  const y0 = pos.y;
  const lw = 4 * 7 + 10; // largeur de l'App ID (4 chiffres)

  // La forme connectable englobe l'avatar ET l'App ID en bas (+ 4px de marge).
  // Ainsi, les arêtes venant du bas s'attachent sous l'étiquette (zéro chevauchement visuel).
  const minX = Math.min(x0, pos.x + 32 - lw / 2);
  const maxX = Math.max(x0 + w, pos.x + 32 + lw / 2);
  const forme = { id: n.id, x0: minX, y0, x1: maxX, y1: y0 + w + 22 };

  return { forme, obstacles: [] };
}

// Titre de domaine = obstacle (les relations ne traversent jamais les étiquettes)
function obstacleTitreRegion(n) {
  const d = n.data || {};
  if (!d.label) return null;
  const lx = d.labelX ?? d.w / 2;
  const ly = d.labelY ?? 30;
  const lw = d.label.length * 9 + 26;
  const h = d.macro ? 48 : 28;
  return { x0: n.position.x + lx - lw / 2, y0: n.position.y + ly - 14, x1: n.position.x + lx + lw / 2, y1: n.position.y + ly - 14 + h };
}

// Fabrique d'arêtes orthogonales : ports directionnels, routes finales (Worker libavoid) ou
// provisoires (routeur maison pendant le drag / en secours), ponts, agrégation « N flux » (> 5).
// polysParDomaine : coques des territoires — une relation INTERNE ne doit jamais quitter
// la membrane de son domaine (pénalité de sortie + repli sur le routeur maison confiné).
// Retourne aussi le snapshot géométrique à pousser vers le Worker.
function fabriqueOrtho(relations, ns, posDe, niveau, zoomFort = false, routesFin = null, provisoire = false, tactile = false, polysParDomaine = {}, domDe = {}) {
  const jumeauxParId = {};
  ns.forEach((n) => {
    if (n.data?.jumeau) jumeauxParId[n.id] = n.data.jumeau;
  });
  const rels = relations.filter((r) => posDe[r.source] && posDe[r.cible]);
  const choix = {};
  rels.forEach((r) => {
    choix[r.id] = choixCotes(ancreJumeau(jumeauxParId[r.source], posDe[r.source]), ancreJumeau(jumeauxParId[r.cible], posDe[r.cible]));
  });
  const decalages = decalagesParalleles(rels, choix);

  // Snapshot pour le Worker : toutes les formes sont des obstacles pour libavoid,
  // la membrane n'en est JAMAIS un (les relations peuvent la traverser)
  const snapshot = { shapes: [], obstacles: [], edges: [] };
  ns.forEach((n) => {
    if (n.type !== "twin") {
      const o = n.type === "region" ? obstacleTitreRegion(n) : null;
      if (o) snapshot.obstacles.push(o);
      return;
    }
    const g = geometrieNoeud(n);
    snapshot.shapes.push(g.forme);
    snapshot.obstacles.push(...g.obstacles);
  });
  snapshot.edges = rels.map((r) => ({
    id: r.id,
    source: r.source,
    target: r.cible,
    sourcePort: COTE_VERS_PORT[choix[r.id][0]],
    targetPort: COTE_VERS_PORT[choix[r.id][1]],
    priorite: PRIORITES[r.etat] ?? 40,
  }));

  const routes = [];
  const edges = [];
  rels.forEach((r) => {
    const cs = ancreJumeau(jumeauxParId[r.source], posDe[r.source]);
    const ct = ancreJumeau(jumeauxParId[r.cible], posDe[r.cible]);
    const fin = !provisoire && routesFin ? routesFin[r.id] : null;
    const valide = fin && fin.points?.length >= 2 && fin.sp === choix[r.id][0] && fin.tp === choix[r.id][1];
    // Provisoire (drag) : trajet simple sans obstacles ; final : points du Worker ; secours : routeur maison
    const obstacles = provisoire ? [] : obstaclesDe(ns, new Set([r.source, r.cible]));
    // Confinement : relation interne → la coque de son domaine est infranchissable
    const dom = domDe[r.source];
    const polysIntra = dom && dom === domDe[r.cible] && polysParDomaine[dom] ? [polysParDomaine[dom]] : [];
    const locale = routeStable(r.id, cs, ct, choix[r.id][0], choix[r.id][1], obstacles, decalages[r.id] || 0, polysIntra, 40, true);
    // La route finale du Worker ignore les coques : si elle sort de la membrane,
    // on retombe sur la route maison confinée
    const points = valide && (!polysIntra.length || sortiesPolys(fin.points, polysIntra, 40) === 0) ? fin.points : locale;
    routes.push({ id: r.id, points, priorite: PRIORITES[r.etat] ?? 40 });
    const bidi = relations.some((o) => o.source === r.cible && o.cible === r.source && o.id !== r.id);
    const label =
      r.grappeCompte > 1
        ? `${r.grappeCompte} flux`
        : r.etat === "validation"
          ? `validation A2A${r.confiance ? ` — ${r.confiance} %` : ""}`
          : r.etat === "contestee"
            ? "contestée — contradiction"
            : r.label;
    edges.push({
      id: r.id,
      source: r.source,
      target: r.cible,
      sourceHandle: `s-${choix[r.id][0]}`,
      targetHandle: `t-${choix[r.id][1]}`,
      type: "ortho",
      data: {
        etat: r.etat,
        restreinte: !!r.restreinte,
        points,
        label,
        confiance: r.confiance,
        bidi,
        niveau,
        zoomFort,
        tactile,
        couleurCible: couleurDomaine(jumeauxParId[r.cible]?.domaine),
      },
    });
  });
  const sauts = detecterCroisements(routes);
  edges.forEach((e) => {
    if (sauts[e.id]?.length) e.data.sauts = sauts[e.id];
  });

  // Agrégation : au-delà de 5 relations entre le même couple, une seule voie « N flux »
  // (le survol déploie temporairement les routes membres)
  const parPaire = {};
  rels.forEach((r) => {
    const cle = [r.source, r.cible].sort().join("::");
    (parPaire[cle] = parPaire[cle] || []).push(r.id);
  });
  Object.entries(parPaire).forEach(([cle, ids]) => {
    if (ids.length <= 5) return;
    const aggId = `agg-${cle}`;
    const membres = edges.filter((e) => ids.includes(e.id));
    membres.forEach((e) => {
      e.hidden = true;
      e.data.groupe = aggId;
    });
    const ref = membres.find((e) => e.data.etat === "contestee") || membres[0];
    edges.push({
      id: aggId,
      source: ref.source,
      target: ref.target,
      sourceHandle: ref.sourceHandle,
      targetHandle: ref.targetHandle,
      type: "ortho",
      data: {
        etat: "observee",
        points: ref.data.points,
        label: `${ids.length} flux`,
        agregat: ids,
        niveau,
        zoomFort: true,
        couleurCible: ref.data.couleurCible,
      },
    });
  });
  return { edges, snapshot };
}

// Ports directionnels : source et cible s'attachent côté gauche ou droit selon la géographie
export const makeEdge = (r, niveau, positions) => {
  const ps = positions?.[r.source];
  const pt = positions?.[r.cible];
  const cotes = ps && pt
    ? (pt.x - ps.x >= 0
      ? { sourceHandle: "s-r", targetHandle: "t-l" }
      : { sourceHandle: "s-l", targetHandle: "t-r" })
    : {};
  return {
    id: r.id,
    source: r.source,
    target: r.cible,
    ...cotes,
    type: "smoothstep",
    pathOptions: { borderRadius: 10 },
    interactionWidth: 8, // zone de clic raisonnable sans bloquer le déplacement de la carte
    animated: !!r.active || r.etat === "validation",
    // Marqueur directionnel turquoise sur les relations observées par le Mesh
    ...(r.etat === "observee" && !r.restreinte
      ? { markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#25D0C8" } }
      : {}),
    data: { etat: r.etat, restreinte: !!r.restreinte },
    style: r.restreinte ? { ...styleParEtat(r), opacity: 0.35, strokeDasharray: "3 5" } : styleParEtat(r),
    label:
      r.etat === "validation"
        ? `validation A2A${r.confiance ? ` — ${r.confiance} %` : ""}`
        : r.etat === "contestee"
          ? "contestée — contradiction"
          : niveau >= 3 && r.label
            ? r.label
            : undefined,
    labelStyle: { fill: r.etat === "validation" ? "#9B87F5" : r.etat === "contestee" ? "#F87171" : "rgba(148,163,184,0.85)", fontSize: 10, fontFamily: "IBM Plex Mono" },
    labelBgStyle: { fill: "rgba(15,29,40,0.92)" },
  };
};

// Écarte les arêtes qui partagent un même port (évite les superpositions confuses)
export function repartirOffsets(edges) {
  const groupes = {};
  const ajouter = (cle, e, role) => {
    if (!cle) return;
    groupes[cle] = groupes[cle] || [];
    groupes[cle].push({ e, role });
  };
  edges.forEach((e) => {
    ajouter(`${e.source}|${e.sourceHandle || ""}`, e, "source");
    ajouter(`${e.target}|${e.targetHandle || ""}`, e, "cible");
  });
  const decalages = {};
  Object.values(groupes).forEach((g) => {
    if (g.length < 2) return;
    g.forEach(({ e }, i) => {
      decalages[e.id] = (decalages[e.id] || 0) + (i - (g.length - 1) / 2) * 18;
    });
  });
  return edges.map((e) => {
    const off = decalages[e.id];
    if (!off) return e;
    return { ...e, pathOptions: { ...(e.pathOptions || {}), offset: Math.max(-60, Math.min(60, off)) } };
  });
}

const NOUVELLE_STYLE = { stroke: "#25D0C8", strokeWidth: 2.6, strokeDasharray: "2 4", opacity: 1 };

// Projection temporelle des relations : historique/replay masquent le futur,
// avant-après met en évidence ce qui est apparu depuis la date de référence.
export function appliquerTemps(edges, temps) {
  if (!temps?.mode) return edges;
  const { mode, dateTs, relTs } = temps;
  const tsDe = (id) => relTs?.[String(id).replace(/-porte$/, "")];
  if (mode === "avantapres") {
    return edges.map((e) => {
      const ts = tsDe(e.id);
      const nouvelle = ts && dateTs && ts > dateTs;
      if (nouvelle) {
        return {
          ...e,
          animated: true,
          data: { ...e.data, nouvelle: true },
          style: { ...NOUVELLE_STYLE },
          label: `${e.label ? `${e.label} · ` : ""}nouvelle`,
          labelStyle: { fill: "#25D0C8", fontSize: 10, fontFamily: "IBM Plex Mono" },
          labelBgStyle: { fill: "rgba(15,29,40,0.92)" },
        };
      }
      return { ...e, animated: false, style: { ...e.style, opacity: 0.15 } };
    });
  }
  return edges.filter((e) => {
    const ts = tsDe(e.id);
    return !ts || !dateTs || ts <= dateTs;
  });
}

export function statsDuDomaine(mesh, situations, domDe, label) {
  if (!mesh || !label) return null;
  const twins = mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === label);
  const couv = twins.length ? Math.round(twins.reduce((a, j) => a + (j.couverture || 0), 0) / twins.length) : 0;
  const ext = {};
  mesh.relations.forEach((r) => {
    const a = domDe[r.source] === label;
    const b = domDe[r.cible] === label;
    if (a === b) return;
    const autre = a ? domDe[r.cible] : domDe[r.source];
    if (!autre) return;
    ext[autre] = (ext[autre] || 0) + 1;
  });
  const sits = situations.filter((s) => (s.jumeaux || []).some((j) => domDe[j] === label));
  const equipes = [...new Set(twins.map((j) => j.proprietaire).filter(Boolean))];
  const reg = (mesh.regions || []).find((r) => r.label === label);
  return { twins, couv, ext, sits, equipes, reg };
}

export function construireGraphe({
  mesh, situation, focus, vueActive, perimetreTravail,
  posOverrides, compteurs, halo, selection,
  zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps, zoomFort, fonduJumeau = 0, fonduGD = 0, fonduPE = 0,
  routesFin, provisoire, tactile,
  couchesCarte = {}, situationsJumeaux, onMajClic,
  theatreSituationnel,
}) {
  if (!mesh) return { nodes: [], edges: [], snapshot: null };
  const implique = situation?.jumeaux || [];

  // Flux observés et écarts par domaine (infobulle des membranes)
  const statsRel = {};
  (mesh.relations || []).forEach((r) => {
    [r.source, r.cible].forEach((jid) => {
      const d = domDe[jid];
      if (!d) return;
      const s = (statsRel[d] = statsRel[d] || { flux: 0, ecarts: 0 });
      if (r.etat === "observee") s.flux += 1;
      if (r.etat === "supposee" || r.etat === "contestee") s.ecarts += 1;
    });
  });

  const dims = new Set();
  if (focus) {
    const deps = new Set([focus]);
    mesh.relations.forEach((r) => {
      if (r.source === focus && r.active) deps.add(r.cible);
      if (r.cible === focus && r.active) deps.add(r.source);
    });
    mesh.jumeaux.forEach((j) => { if (!deps.has(j.id)) dims.add(j.id); });
  } else if (situation && implique.length) {
    mesh.jumeaux.forEach((j) => { if (!implique.includes(j.id)) dims.add(j.id); });
  }
  if (vueActive?.type === "selection") {
    mesh.jumeaux.forEach((j) => { if (!j.anonyme && !vueActive.jumeaux.includes(j.id)) dims.add(j.id); });
  }
  if (vueActive?.type === "vigilance") {
    mesh.jumeaux.forEach((j) => { if ((j.couverture ?? 100) >= 70) dims.add(j.id); });
  }
  if (perimetreTravail) {
    mesh.jumeaux.forEach((j) => { if (!j.anonyme && j.domaine !== perimetreTravail) dims.add(j.id); });
  }

  // Focus contextuel : sélection → voisins éclairés, reste translucide
  if (selection.length > 0 && !focus) {
    const voisins = new Set(selection);
    mesh.relations.forEach((r) => {
      if (selection.includes(r.source)) voisins.add(r.cible);
      if (selection.includes(r.cible)) voisins.add(r.source);
    });
    mesh.jumeaux.forEach((j) => { if (!voisins.has(j.id)) dims.add(j.id); });
  }

  // Moteur Universel de Focus Situationnel (Chat, Incident, Travail, Scénario Polaris)
  const ciblesTheatre = new Set(theatreSituationnel?.actif ? theatreSituationnel.cibles : []);
  const phaseTheatre = theatreSituationnel?.actif ? theatreSituationnel.phase : "idle";

  const aSceneFocus = focusCarte && focusCarte.type === "scene";
  const aSituationOuTravail = !!situation?.id && implique.length > 0;
  // En phase « sanctuaire » (ou fallback si focus direct non piloté par le contrôleur) :
  // Les éléments non concernés sont 100% purgés de la scène pour un théâtre de décision limpide.
  const modeSituationnel =
    phaseTheatre === "sanctuaire" ||
    (!theatreSituationnel?.actif && (aSceneFocus || aSituationOuTravail));

  let twins = mesh.jumeaux || [];
  if (modeSituationnel) {
    if (theatreSituationnel?.actif && ciblesTheatre.size > 0) {
      twins = twins.filter((j) => ciblesTheatre.has(j.id) || j.cadastre);
    } else if (aSituationOuTravail) {
      twins = twins.filter((j) => implique.includes(j.id) || j.cadastre);
    } else if (focusCarte?.type === "scene" && focusCarte?.ids?.length) {
      twins = twins.filter((j) => focusCarte.ids.includes(j.id) || j.cadastre);
    }
  }

  const entreprise = modeSituationnel ? false : zoomNiveau === 1;
  // Bande de transition Global ↔ Domaine (z 0.5 → 0.7) : les deux mondes coexistent,
  // les corridors fondent pendant que les arêtes de domaine et les étoiles se révèlent.
  const bande = modeSituationnel ? false : fonduGD > 0 && fonduGD < 1;
  const niveauEff = modeSituationnel ? 3 : bande ? 2 : zoomNiveau;
  const fonduJumeauEff = modeSituationnel ? 1 : fonduJumeau;

  // Zéro chevauchement : calcul des positions finales avant toute construction
  const posSeparees = separerNoeuds(twins, posOverrides);

  // Niveau 4 — Composants & preuves : arbitrage façon Google Maps.
  let cartesVisibles = null;
  if (zoomNiveau >= 4 && !modeSituationnel) {
    const prioriteCarte = (j) => (selection.includes(j.id) ? 400 : 0) + (halo === j.id ? 250 : 0) + (j.couverture || 0);
    const places = twins
      .filter((j) => !dims.has(j.id))
      .map((j) => {
        const p = posSeparees[j.id] || j.position;
        return { id: j.id, x0: p.x - 1, y0: p.y, x1: p.x + 65, y1: p.y + 68 };
      });
    const candidats = twins
      .filter((j) => !j.anonyme && !dims.has(j.id))
      .sort((a, b) => prioriteCarte(b) - prioriteCarte(a));
    cartesVisibles = new Map(); // id → "bas" | "haut"
    for (const j of candidats) {
      const p = posSeparees[j.id] || j.position;
      for (const [position, y0, y1] of [["bas", p.y + 73, p.y + 176], ["haut", p.y - 105, p.y - 3]]) {
        const r = { id: j.id, x0: p.x + 32 - 76, y0, x1: p.x + 32 + 76, y1 };
        if (!places.some((q) => q.id !== j.id && r.x0 < q.x1 && r.x1 > q.x0 && r.y0 < q.y1 && r.y1 > q.y0)) {
          places.push(r);
          cartesVisibles.set(j.id, position);
          break;
        }
      }
    }
  }

  // Filtrage des régions : en mode situationnel sanctuarisé, les régions du corridor actif
  // sont pleinement mises en avant, tandis que le cadastre d'entreprise apparaît en filigrane discret.
  const ciblesPrincipales =
    theatreSituationnel?.actif && ciblesTheatre.size > 0
      ? ciblesTheatre
      : aSituationOuTravail
        ? new Set(implique)
        : aSceneFocus
          ? new Set(focusCarte.ids)
          : null;

  const domainesCorridor = new Set(
    (ciblesPrincipales
      ? (mesh.jumeaux || []).filter((j) => ciblesPrincipales.has(j.id) && !j.cadastre)
      : twins.filter((j) => !j.cadastre)
    ).map((j) => j.domaine || domDe[j.id]).filter(Boolean)
  );

  const regionsSource = modeSituationnel
    ? (mesh.regions || []).filter((r) => domainesCorridor.has(r.label) || r.cadastre)
    : (mesh.regions || []);

  let ns = regionsSource.map((r) => {
    const centres = twins.filter((j) => (j.domaine || domDe[j.id]) === r.label).map((j) => {
      const p = posSeparees[j.id] || j.position;
      return { x: p.x + 30, y: p.y + 40 };
    });
    const coque = coqueOrganique(centres) || { x: r.x, y: r.y, w: r.w, h: r.h, path: null, labelX: r.w / 2 };
    const estCadastreRegion = !!r.cadastre || (modeSituationnel && !domainesCorridor.has(r.label));
    const estDomaineCible = phaseTheatre !== "plongeon" || domainesCorridor.has(r.label);

    return {
      id: r.id, type: "region", position: { x: coque.x, y: coque.y },
      initialWidth: coque.w,
      initialHeight: coque.h,
      data: {
        ...r,
        w: coque.w, h: coque.h, path: coque.path, points: coque.points, labelX: coque.labelX,
        niveau: niveauEff,
        cadastre: estCadastreRegion,
        investigations: statsRegions[r.label]?.investigations ?? 0,
        decouvertes: statsRegions[r.label]?.decouvertes ?? 0,
        flux: statsRel[r.label]?.flux ?? 0,
        ecarts: statsRel[r.label]?.ecarts ?? 0,
        halo: !!halo && domDe[halo] === r.label,
        capacitesVisibles: !estCadastreRegion && !!couchesCarte.capacites,
        attenue: estCadastreRegion || !estDomaineCible,
        fonduPlongeon: !estDomaineCible,
        style: estCadastreRegion
          ? { opacity: 0.22, transition: "opacity 600ms ease" }
          : !estDomaineCible
            ? { opacity: 0.1, transition: "opacity 900ms ease" }
            : undefined,
      },
      draggable: false, selectable: false, zIndex: -10,
    };
  });

  // Regroupement visuel désactivé (choix utilisateur)
  const clusters = {};

  ns = ns.concat(
    twins.map((j) => {
      const position = posSeparees[j.id] || j.position;
      const estCible = ciblesTheatre.has(j.id);
      const estPlongeon = phaseTheatre === "plongeon";
      const estIllum = phaseTheatre === "illumination";
      const fonduPlongeon = estPlongeon && !estCible;
      const haloActif = (estIllum || estPlongeon) ? estCible : (halo === j.id);
      const estCadastre = !!j.cadastre;
      const estDim = estCadastre ? true : modeSituationnel ? false : fonduPlongeon ? true : dims.has(j.id);

      return {
        id: j.id,
        type: "twin",
        position,
        initialWidth: 64,
        initialHeight: 78,
        hidden: false,
        data: {
          jumeau: j,
          cadastre: estCadastre,
          dim: estDim,
          halo: !estCadastre && haloActif,
          fonduPlongeon,
          style: estCadastre
            ? { opacity: 0.18, transition: "opacity 600ms ease" }
            : fonduPlongeon
              ? { opacity: 0.12, transition: "opacity 900ms ease" }
              : undefined,
          evenements: compteurs[j.id] || 0,
          etape: null,
          niveau: estCadastre ? 1 : modeSituationnel ? 3 : zoomNiveau,
          fondu: estCadastre ? 0 : fonduJumeauEff,
          entree: bande ? fonduGD : 1,
          detailVisible: !estCadastre && zoomNiveau >= 4 && !j.anonyme && !!cartesVisibles?.has(j.id),
          detailPosition: cartesVisibles?.get(j.id) || "bas",
          dansSituation: !estCadastre && !!couchesCarte.situations && !!situationsJumeaux?.has(j.id),
          enTransformation: !estCadastre && !!couchesCarte.transformations && (j.statut === "en construction" || j.statut === "observation"),
          onMajClic,
        },
        selected: !estCadastre && ((estIllum || estPlongeon) ? estCible : selection.includes(j.id)),
      };
    })
  );
  // Nœuds « grappe » supprimés (choix utilisateur)

  let es = [];
  let snapMain = null;
  const posMain = Object.fromEntries(twins.map((j) => [j.id, posSeparees[j.id] || j.position]));

  // --- Corridor parent : désactivé en mode situationnel (les relations orthogonales réelles priment)
  const enEclatement = zoomNiveau >= 3 && fonduPE < 1;
  let corridorsParent = [];
  const rangMembre = {}; // relation inter-domaines → rang le long de son corridor parent
  const taillePaire = {};
  if (!modeSituationnel && (entreprise || bande || zoomNiveau === 2 || enEclatement)) {
    const regParDom = {};
    (mesh.regions || []).forEach((r) => { regParDom[r.label] = r.id; });
    // Ancres = « capitales » des territoires (position de l'étiquette du domaine)
    const posRegions = Object.fromEntries(
      ns.filter((n) => n.type === "region").map((n) => [
        n.id,
        { x: n.position.x + (n.data.labelX ?? n.initialWidth / 2), y: n.position.y + (n.data.labelY ?? n.initialHeight / 2) },
      ])
    );
    // Obstacles = membranes des territoires TIERS (boîte englobante + 48px de respiration)
    const regs = {};
    ns.filter((n) => n.type === "region").forEach((n) => {
      const pts = n.data.points || [];
      // Capitale = centroïde de la coque (toujours à l'intérieur) — PAS la position
      // du titre (data.labelY absent → repli haut de coque → rayons d'ancrage faussés)
      const cx = pts.length ? n.position.x + pts.reduce((s, p) => s + p.x, 0) / pts.length : n.position.x + (n.data.labelX ?? n.initialWidth / 2);
      const cy = pts.length ? n.position.y + pts.reduce((s, p) => s + p.y, 0) / pts.length : n.position.y + 30;
      regs[n.data.label] = { ox: n.position.x, oy: n.position.y, pts, lx: cx, ly: cy };
    });
    // Obstacles du routage : boîtes englobantes des coques (+16 px) pour les canaux
    // orthogonaux + coques réelles gonflées (+10 px) pour la pénalité de traversée —
    // les canaux propres restent possibles entre domaines proches, mais un trajet qui
    // traverse une membrane ne gagne JAMAIS.
    const nomsDomaines = Object.keys(regs).filter((lb) => regs[lb].pts.length >= 3);
    const obstaclesRects = nomsDomaines.map((lb) => {
      const r = regs[lb];
      const xs = r.pts.map((p) => p.x + r.ox);
      const ys = r.pts.map((p) => p.y + r.oy);
      return { nom: lb, x0: Math.min(...xs) - 16, y0: Math.min(...ys) - 16, x1: Math.max(...xs) + 16, y1: Math.max(...ys) + 16 };
    });
    const obstaclesPolys = nomsDomaines.map((lb) => {
      const r = regs[lb];
      return gonflePolygone(r.pts.map((p) => ({ x: p.x + r.ox, y: p.y + r.oy })), 10);
    });
    // Regroupement des relations inter-domaines par couple de territoires
    const paires = {};
    mesh.relations.forEach((r) => {
      const a = domDe[r.source];
      const b = domDe[r.cible];
      if (!a || !b || a === b || !regParDom[a] || !regParDom[b]) return;
      const [x, y] = [a, b].sort();
      const key = `${x}::${y}`;
      (paires[key] = paires[key] || { a: x, b: y, membres: [] }).membres.push(r);
    });
    corridorsParent = Object.values(paires).map((c) => {      const idA = regParDom[c.a];
      const idB = regParDom[c.b];
      const ra = regs[c.a];
      const rb = regs[c.b];
      const ps = posRegions[idA];
      const pt = posRegions[idB];
      // Ancres sur la FRONTIÈRE des membranes (jamais au centre)
      const pa = ra?.pts?.length && rb ? ancreFrontiere(ra, rb.lx, rb.ly) : null;
      const pb = rb?.pts?.length && ra ? ancreFrontiere(rb, ra.lx, ra.ly) : null;
      if (!pa || !pb) return null;
      // Routage orthogonal direct entre ancres frontières : canaux autour des coques
      // TIERCES (boîtes +16) + pénalité de traversée des coques réelles (toutes,
      // grâce de 24 px aux bouts pour le rasage de frontière source/cible)
      const obstaclesTiers = obstaclesRects.filter((o) => o.nom !== c.a && o.nom !== c.b);
      const points = routeCorridor(pa, pb, obstaclesTiers, obstaclesPolys);
      // Rang de chaque membre le long du corridor (éclatement échelonné)
      const dx = pb.x - pa.x;
      const dy = pb.y - pa.y;
      const L2 = dx * dx + dy * dy || 1;
      [...c.membres]
        .sort((m1, m2) => {
          const p1 = posMain[m1.source];
          const p2 = posMain[m2.source];
          const t1 = p1 ? ((p1.x - pa.x) * dx + (p1.y - pa.y) * dy) / L2 : 0;
          const t2 = p2 ? ((p2.x - pa.x) * dx + (p2.y - pa.y) * dy) / L2 : 0;
          return t1 - t2;
        })
        .forEach((m, i) => {
          rangMembre[m.id] = i;
          taillePaire[m.id] = c.membres.length;
        });
      const n = c.membres.length;
      const actif = c.membres.some((r) => r.active);
      const etatFort = c.membres.reduce((acc, r) => ((PRIORITES[r.etat] ?? 40) > (PRIORITES[acc] ?? 40) ? r.etat : acc), c.membres[0].etat);
      const droite = ps && pt ? pt.x - ps.x >= 0 : true;
      return {
        id: `corridor-${c.a}-${c.b}`,
        source: idA,
        target: idB,
        sourceHandle: droite ? "s-r" : "s-l",
        targetHandle: droite ? "t-l" : "t-r",
        type: "corridor",
        interactionWidth: 16,
        data: {
          n,
          actif,
          etat: etatFort,
          membres: c.membres.map((m) => m.id),
          couleurA: couleurDomaine(c.a),
          couleurB: couleurDomaine(c.b),
          domains: [c.a, c.b],
          corridorLabel: `${c.a} ↔ ${c.b} · ${n} relation${n > 1 ? "s" : ""}${actif ? " · activité élevée" : ""}`,
          labelFlux: `${n} flux`,
          capitales: ps && pt ? { sx: ps.x, sy: ps.y, tx: pt.x, ty: pt.y } : null,
          points,
          sens: c.a < c.b ? 1 : -1,
          // Filiation : macro → détail dans la bande Global ↔ Domaine ;
          // dissolution pendant l'éclatement au niveau Jumeau
          detail: entreprise ? (bande ? fonduGD : 0) : 1,
          sortie: enEclatement ? 1 - fonduPE : 1,
        },
      };
    }).filter(Boolean);
  }
  if (modeSituationnel || !entreprise || bande) {
    // Confinement : coques des territoires RETRÉCIES de 14 px (la membrane rendue est
    // arrondie jusqu'à ~14 px en retrait du polygone brut — sans cette marge, un arc
    // « légalement » dedans rase visuellement la frontière, voire la dépasse). Grâce
    // de 40 px aux extrémités : les ports bas (centre + 74 px) démarrent hors coque.
    const polyParDomaine = {};
    ns.filter((n) => n.type === "region" && n.data.points?.length >= 3).forEach((n) => {
      polyParDomaine[n.data.label] = gonflePolygone(n.data.points.map((p) => ({ x: p.x + n.position.x, y: p.y + n.position.y })), -14);
    });
    // Extrémités regroupées : une relation touchant un membre pointe vers sa grappe ;
    // les relations entre mêmes extrémités sont agrégées (compte) — densité maîtrisée
    const twinsIds = new Set(twins.map((j) => j.id));
    const cadastreTwinIds = new Set(twins.filter((j) => j.cadastre).map((j) => j.id));
    const relsMappees = mesh.relations
      .filter((r) => twinsIds.has(r.source) && twinsIds.has(r.cible))
      .filter((r) => (situation && implique.length ? (implique.includes(r.source) && implique.includes(r.cible)) || r.cadastre : true))
      .filter((r) => !focus || r.source === focus || r.cible === focus)
      .map((r) => ({ ...r, source: clusters[r.source] || r.source, cible: clusters[r.cible] || r.cible }))
      .filter((r) => r.source !== r.cible)
      .reduce((acc, r) => {
        const ex = acc.find((o) => o.source === r.source && o.cible === r.cible);
        if (ex) {
          ex.grappeCompte = (ex.grappeCompte || 1) + 1;
          if ((PRIORITES[r.etat] ?? 40) > (PRIORITES[ex.etat] ?? 40)) ex.etat = r.etat;
        } else {
          acc.push({ ...r });
        }
        return acc;
      }, []);
    // Niveau 2 — Domaines : les relations inter-domaines sont portées par les
    // corridors parents (bloc unifié ci-dessus) ; seules les relations internes
    // passent par le routage orthogonal. Au niveau 3 ou en mode situationnel, toutes reviennent.
    let relsPourRoutage = relsMappees;
    if (!modeSituationnel && niveauEff === 2) {
      relsPourRoutage = relsMappees.filter((r) => {
        const da = domDe[r.source];
        const db = domDe[r.cible];
        return !da || !db || da === db;
      });
    }
    const ortho = fabriqueOrtho(relsPourRoutage, ns, posMain, niveauEff, zoomFort, routesFin, provisoire, tactile, polyParDomaine, domDe);
    snapMain = ortho.snapshot;
    let aretesDomaine = ortho.edges
      .map((e) => {
        const toucheCadastre = cadastreTwinIds.has(e.source) || cadastreTwinIds.has(e.target) || e.data?.cadastre;
        return {
          ...e,
          data: {
            ...e.data,
            cadastre: toucheCadastre,
            estompee: toucheCadastre || e.data?.estompee,
            entree: bande ? fonduGD : 1,
          },
        };
      });
    // Éclatement parent → enfants : pendant la dissolution du corridor (bande
    // z 1.15 → 1.35), chaque relation membre naît à son tour, dans l'ordre le
    // long du tracé parent — la filiation est visible, rien ne « pop » d'un coup.
    if (zoomNiveau >= 3 && fonduPE < 1) {
      aretesDomaine = aretesDomaine.map((e) => {
        const rang = rangMembre[e.id];
        if (rang === undefined) return e;
        const n = taillePaire[e.id] || 1;
        const debut = rang / (n + 0.5);
        const entree = Math.max(0, Math.min(1, (fonduPE - debut) * (n + 0.5) * 1.6));
        return { ...e, data: { ...e.data, entree: Math.min(e.data.entree ?? 1, entree) } };
      });
    }
    // Moteur de labels des relations (niveau 3+) : collision → le moins prioritaire disparaît
    if (zoomNiveau >= 3 && !provisoire) {
      const candidats = aretesDomaine
        .filter((e) => e.data?.label && !e.hidden)
        .map((e) => {
          const a = ancreLabel(e.data.points);
          if (!a) return null;
          return {
            id: e.id, x: a.x, y: a.y,
            w: e.data.label.length * 6.8 + 20, h: 18,
            priorite: (e.data.agregat ? 100 : 0) + (PRIORITES[e.data.etat] ?? 40),
          };
        })
        .filter(Boolean);
      const vis = placerLabels(candidats);
      aretesDomaine = aretesDomaine.map((e) => (e.data?.label && !e.hidden && !vis.has(e.id) ? { ...e, data: { ...e.data, labelMasque: true } } : e));
    }
    if (vueActive?.type === "relations_non_confirmees") {
      aretesDomaine = aretesDomaine.map((e) =>
        e.data?.etat === "confirmee" ? { ...e, animated: false, style: { ...e.style, opacity: 0.1 } } : e
      );
    }
    if (!modeSituationnel && relFocus && selection.length > 1) {
      aretesDomaine = aretesDomaine.filter((e) => selection.includes(e.source) && selection.includes(e.target));
    }
    if (focusCarte?.type === "relations" && focusCarte.ids?.length) {
      aretesDomaine = aretesDomaine.map((e) =>
        focusCarte.ids.includes(e.id)
          ? { ...e, animated: true, style: { ...e.style, opacity: 1, strokeWidth: 2.6 } }
          : { ...e, animated: false, style: { ...e.style, opacity: 0.08 } }
      );
    }
    if (phaseTheatre === "plongeon" && ciblesTheatre.size > 0) {
      aretesDomaine = aretesDomaine.map((e) => {
        const estCible = ciblesTheatre.has(e.source) && ciblesTheatre.has(e.target);
        return estCible
          ? { ...e, animated: true, style: { ...e.style, opacity: 1, strokeWidth: 2.6 } }
          : { ...e, animated: false, data: { ...e.data, fonduPlongeon: true }, style: { ...e.style, opacity: 0.04, transition: "opacity 900ms ease" } };
      });
    }
    es = es.concat(aretesDomaine);
  }
  if (phaseTheatre === "plongeon" && corridorsParent.length > 0) {
    corridorsParent = corridorsParent.map((c) => ({
      ...c,
      style: { ...c.style, opacity: 0.04, transition: "opacity 900ms ease" },
    }));
  }
  if (!modeSituationnel && (entreprise || bande)) {
    // Lors d'une illumination ou d'un plongeon situationnel, les robots cibles doivent être
    // immédiatement visibles avec leurs halos sur le planisphère du SI sans attendre le zoom 2
    if (theatreSituationnel?.actif && (phaseTheatre === "illumination" || phaseTheatre === "plongeon")) {
      return { nodes: ns, edges: appliquerTemps(es.concat(corridorsParent), temps), snapshot: snapMain };
    }
    // Vue Global (et bande de transition) : agrégats macro sur les territoires —
    // en bande, les étoiles existent déjà (fondu d'entrée) et les agrégats fondent
    const macro = ns
      .filter((n) => n.type !== "twin" || bande)
      .map((n) => ({ ...n, data: { ...n.data, macro: true, opaciteMacro: bande ? 1 - fonduGD : 1 } }));
    return { nodes: macro, edges: repartirOffsets(appliquerTemps(es.concat(corridorsParent), temps)), snapshot: null };
  }
  return { nodes: ns, edges: appliquerTemps(es.concat(corridorsParent), temps), snapshot: snapMain };
}
