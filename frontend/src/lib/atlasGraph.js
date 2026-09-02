import { MarkerType } from "@xyflow/react";
import concaveman from "concaveman";
import { couleurDomaine } from "@/lib/domaines";
import { choixCotes, routeStable, detecterCroisements, decalagesParalleles } from "./routeur";

export const COUCHES = [
  ["operationnelle", "Opérationnelle", "#3730A3"],
  ["connaissance", "Connaissance", "#0E7490"],
  ["mesh", "Mesh", "#6D28D9"],
];

export const NIVEAUX_ZOOM = { 1: "Capacités", 2: "Domaines", 3: "Applications & flux" };

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
    // concaveman aussi à 2 membres : sommets polygonaux perceptibles au lieu d'une capsule lisse
    poly = centres.length === 1
      ? hullConvexe(gonfle.map(([x, y]) => ({ x, y })))
      : concaveman(gonfle, 2.2, 52).map(([x, y]) => ({ x, y }));
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

export const styleParEtat = (r) => {
  switch (r.etat) {
    // Réalité découverte : ligne turquoise continue + marqueur directionnel (dans makeEdge)
    case "observee":
      return { stroke: "#0E7490", strokeWidth: 2 };
    // Écarts (contradictoire ou à qualifier) : pointillés orange
    case "supposee":
      return { stroke: "#D97706", strokeWidth: 1.7, strokeDasharray: "6 6", opacity: 0.9 };
    case "contestee":
      return { stroke: "#D97706", strokeWidth: 2, strokeDasharray: "6 6" };
    case "validation":
      return { stroke: "#6D28D9", strokeWidth: 1.8, strokeDasharray: "7 5" };
    case "obsolete":
      return { stroke: "rgba(17,17,16,0.4)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25 };
    // BCM déclaré : ligne gris ardoise continue
    default:
      return { stroke: r.active ? "#3730A3" : "rgba(17,17,16,0.45)", strokeWidth: 1.3, opacity: r.active ? 0.9 : 0.6 };
  }
};

// --- Routage : routeur maison (provisoire/secours) + routeur final libavoid en Web Worker ---
// Priorité de routage (spec) : contestée > observée/validation > supposée > déclarée > obsolète
const PRIORITES = { contestee: 80, validation: 60, observee: 60, supposee: 50, confirmee: 40, obsolete: 20 };

// Nos côtés de handles (r/l/t/b) ↔ ports libavoid (e/w/n/s)
const COTE_VERS_PORT = { r: "e", l: "w", t: "n", b: "s" };

// Centre de l'avatar (ou de la pastille) selon la variante de nœud
function ancreJumeau(j, pos) {
  if (j?.porte) return { x: pos.x + 30, y: pos.y + 8, marge: 12 };
  if (j?.anonyme) return { x: pos.x + 30, y: pos.y + 10, marge: 12 };
  return { x: pos.x + 30, y: pos.y + 40, marge: 26 };
}

// Obstacles = rectangles des robots (avatar + App ID + dégagement), extrémités exclues — routeur maison
function obstaclesDe(ns, exclure) {
  return ns
    .filter((n) => n.type === "twin" && !n.data?.jumeau?.porte && !n.data?.jumeau?.anonyme && !exclure.has(n.id))
    .map((n) => ({ x0: n.position.x - 16, y0: n.position.y - 8, x1: n.position.x + 76, y1: n.position.y + 84 }));
}

// Géométrie d'un nœud jumeau pour le routeur final : forme connectable (avatar/pastille, ports N/E/S/W)
// + obstacles non connectables (App ID, badge +N, nom, pastille de passerelle)
function geometrieNoeud(n) {
  const pos = n.position;
  const j = n.data?.jumeau || {};
  if (j.porte || j.anonyme) {
    const nom = n.data?.apercuPorte?.domaine || j.nom || "";
    const lw = nom.length * 6.5 + 34;
    return {
      forme: { id: n.id, x0: pos.x + 22, y0: pos.y, x1: pos.x + 38, y1: pos.y + 16 },
      obstacles: [{ x0: pos.x + 30 - lw / 2, y0: pos.y + 18, x1: pos.x + 30 + lw / 2, y1: pos.y + 36 }],
    };
  }
  const grand = (n.data?.niveau || 2) >= 3;
  const w = grand ? 56 : 48;
  const x0 = pos.x + (64 - w) / 2;
  const y0 = pos.y + 16;
  const obstacles = [{ x0: pos.x + 8, y0: pos.y - 2, x1: pos.x + 58, y1: pos.y + 14 }]; // App ID + badge +N
  if (grand && j.nom) {
    const lw = j.nom.length * 7 + 10;
    obstacles.push({ x0: pos.x + 32 - lw / 2, y0: y0 + w + 2, x1: pos.x + 32 + lw / 2, y1: y0 + w + 18 }); // nom
  }
  return { forme: { id: n.id, x0, y0, x1: x0 + w, y1: y0 + w }, obstacles };
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
// Retourne aussi le snapshot géométrique à pousser vers le Worker.
function fabriqueOrtho(relations, ns, posDe, niveau, zoomFort = false, routesFin = null, provisoire = false) {
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
    const points = valide ? fin.points : routeStable(r.id, cs, ct, choix[r.id][0], choix[r.id][1], obstacles, decalages[r.id] || 0);
    routes.push({ id: r.id, points, priorite: PRIORITES[r.etat] ?? 40 });
    const bidi = relations.some((o) => o.source === r.cible && o.cible === r.source && o.id !== r.id);
    const label =
      r.etat === "validation"
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
      ? { markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#0E7490" } }
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
    labelStyle: { fill: r.etat === "validation" ? "#6D28D9" : r.etat === "contestee" ? "#B91C1C" : "rgba(17,17,16,0.6)", fontSize: 10, fontFamily: "IBM Plex Mono" },
    labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
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

const NOUVELLE_STYLE = { stroke: "#0E7490", strokeWidth: 2.6, strokeDasharray: "2 4", opacity: 1 };

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
          labelStyle: { fill: "#0E7490", fontSize: 10, fontFamily: "IBM Plex Mono" },
          labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
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
  jumeauFocus, domaineInterne, posOverrides, compteurs, halo, selection,
  zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps, zoomFort,
  routesFin, provisoire, propulsion,
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

  // Focus jumeau : le jumeau au centre, ses voisins en portes périphériques
  if (jumeauFocus) {
    const jf = mesh.jumeaux.find((j) => j.id === jumeauFocus);
    if (!jf) return { nodes: [], edges: [] };
    const posF = posOverrides[jf.id] || jf.position;
    const cFx = posF.x + 95;
    const cFy = posF.y + 32;
    const relsV = (mesh.relations || []).filter((r) => r.source === jf.id || r.cible === jf.id);
    const voisins = [...new Set(relsV.map((r) => (r.source === jf.id ? r.cible : r.source)))]
      .map((id) => mesh.jumeaux.find((j) => j.id === id))
      .filter(Boolean);
    const rayF = Math.max(300, 150 + voisins.length * 26);
    const nsF = [{
      id: jf.id, type: "twin", position: posF, initialWidth: 64, initialHeight: 78,
      data: { jumeau: jf, focusCentral: true, evenements: compteurs[jf.id] || 0, halo: halo === jf.id },
      draggable: false, selectable: false, zIndex: 5,
    }];
    voisins.forEach((v, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / voisins.length;
      const rel = relsV.find((r) => r.source === v.id || r.cible === v.id);
      nsF.push({
        id: `voisin-${v.id}`, type: "twin",
        position: { x: cFx + Math.cos(ang) * rayF - 95, y: cFy + Math.sin(ang) * rayF - 35 },
        initialWidth: 64, initialHeight: 78,
        data: { jumeau: v, voisinRel: rel },
        draggable: false, selectable: false, zIndex: 4,
      });
    });
    const posFocus = Object.fromEntries(nsF.map((n) => [n.id, n.position]));
    const relsF = relsV.map((r) => ({
      ...r,
      source: r.source === jf.id ? jf.id : `voisin-${r.source}`,
      cible: r.cible === jf.id ? jf.id : `voisin-${r.cible}`,
    }));
    const esF = fabriqueOrtho(relsF, nsF, posFocus, 3, true, routesFin, provisoire);
    return {
      nodes: nsF,
      edges: appliquerTemps(esF.edges.map((e) => ({ ...e, data: { ...e.data, focus: true } })), temps),
      snapshot: esF.snapshot,
    };
  }

  // Vue interne d'un domaine : jumeaux du domaine + portes externes
  if (domaineInterne) {
    const internes = mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === domaineInterne);
    const reg = (mesh.regions || []).find((r) => r.label === domaineInterne);
    const cx = reg ? reg.x + reg.w / 2 : 600;
    const cy = reg ? reg.y + reg.h / 2 : 350;
    const ray = reg ? Math.max(reg.w, reg.h) / 2 + 130 : 260;
    const extCount = {};
    mesh.relations.forEach((r) => {
      const a = domDe[r.source] === domaineInterne;
      const b = domDe[r.cible] === domaineInterne;
      if (a === b) return;
      const ext = a ? domDe[r.cible] : domDe[r.source];
      if (!ext) return;
      if (!extCount[ext]) extCount[ext] = { n: 0 };
      extCount[ext].n += 1;
    });
    const porteIds = {};
    const portes = Object.keys(extCount);
    let nsInt = [];
    if (reg) {
      const centres = internes.map((j) => {
        const p = posOverrides[j.id] || j.position;
        return { x: p.x + 30, y: p.y + 40 };
      });
      const coque = coqueOrganique(centres) || { x: reg.x, y: reg.y, w: reg.w, h: reg.h, path: null, labelX: reg.w / 2 };
      nsInt = [{ id: reg.id, type: "region", position: { x: coque.x, y: coque.y }, initialWidth: coque.w, initialHeight: coque.h, data: { ...reg, w: coque.w, h: coque.h, path: coque.path, points: coque.points, labelX: coque.labelX, investigations: statsRegions[reg.label]?.investigations ?? 0, decouvertes: statsRegions[reg.label]?.decouvertes ?? 0, flux: statsRel[reg.label]?.flux ?? 0, ecarts: statsRel[reg.label]?.ecarts ?? 0, halo: false }, draggable: false, selectable: false, zIndex: -10 }];
    }
    portes.forEach((dom, i) => {
      const regExt = (mesh.regions || []).find((r) => r.label === dom);
      const ang = regExt
        ? Math.atan2(regExt.y + regExt.h / 2 - cy, regExt.x + regExt.w / 2 - cx)
        : (i / portes.length) * 2 * Math.PI;
      const pid = `porte-${dom}`;
      porteIds[dom] = pid;
      nsInt.push({
        id: pid,
        type: "twin",
        position: { x: cx + Math.cos(ang) * ray - 90, y: cy + Math.sin(ang) * ray },
        initialWidth: 64,
        initialHeight: 78,
        data: {
          jumeau: { id: pid, nom: `Vers ${dom} · ${extCount[dom].n} relation${extCount[dom].n > 1 ? "s" : ""}`, domaine: dom, porte: true, statut: "porte" },
          porte: dom,
          apercuPorte: {
            domaine: dom,
            domaineFocus: domaineInterne,
            jumeaux: mesh.jumeaux.filter((t) => !t.anonyme && t.domaine === dom).length,
            restreint: mesh.jumeaux.filter((t) => !t.anonyme && t.domaine === dom).length === 0,
            relations: extCount[dom].n,
            decouvertes: statsRegions[dom]?.decouvertes ?? 0,
          },
          propulsion: propulsion?.label === dom ? propulsion.progress : undefined,
        },
        draggable: false,
        selectable: false,
      });
    });
    nsInt = nsInt.concat(
      internes.map((j) => ({
        id: j.id,
        type: "twin",
        position: posOverrides[j.id] || j.position,
        initialWidth: 64,
        initialHeight: 78,
        data: { jumeau: j, dim: false, halo: halo === j.id, evenements: compteurs[j.id] || 0, etape: null },
        selected: selection.includes(j.id),
      }))
    );
    const posInt = Object.fromEntries(nsInt.filter((n) => n.type === "twin").map((n) => [n.id, n.position]));
    const relsInt = [];
    mesh.relations.forEach((r) => {
      const a = domDe[r.source] === domaineInterne;
      const b = domDe[r.cible] === domaineInterne;
      if (a && b) {
        relsInt.push(r);
      } else if (a !== b) {
        const ext = a ? domDe[r.cible] : domDe[r.source];
        const pid = porteIds[ext];
        if (!pid) return;
        relsInt.push({ ...r, id: `${r.id}-porte`, source: a ? r.source : r.cible, cible: pid });
      }
    });
    const esInt = fabriqueOrtho(relsInt, nsInt, posInt, 2, false, routesFin, provisoire);
    return { nodes: nsInt, edges: appliquerTemps(esInt.edges, temps), snapshot: esInt.snapshot };
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

  const twins = mesh.jumeaux;
  const entreprise = zoomNiveau === 1;

  let ns = (mesh.regions || []).map((r) => {
    const centres = twins.filter((j) => domDe[j.id] === r.label).map((j) => {
      const p = posOverrides[j.id] || j.position;
      return { x: p.x + 30, y: p.y + 40 };
    });
    const coque = coqueOrganique(centres) || { x: r.x, y: r.y, w: r.w, h: r.h, path: null, labelX: r.w / 2 };
    return {
      id: r.id, type: "region", position: { x: coque.x, y: coque.y },
      initialWidth: coque.w,
      initialHeight: coque.h,
      data: { ...r, w: coque.w, h: coque.h, path: coque.path, points: coque.points, labelX: coque.labelX, investigations: statsRegions[r.label]?.investigations ?? 0, decouvertes: statsRegions[r.label]?.decouvertes ?? 0, flux: statsRel[r.label]?.flux ?? 0, ecarts: statsRel[r.label]?.ecarts ?? 0, halo: !!halo && domDe[halo] === r.label, propulsion: propulsion?.label === r.label ? propulsion.progress : undefined },
      draggable: false, selectable: false, zIndex: -10,
    };
  });

  ns = ns.concat(
    twins.map((j) => {
      const position = posOverrides[j.id] || j.position;
      return {
        id: j.id,
        type: "twin",
        position,
        initialWidth: 64,
        initialHeight: 78,
        hidden: entreprise && !j.anonyme ? true : entreprise,
        data: { jumeau: j, dim: dims.has(j.id), halo: halo === j.id, evenements: compteurs[j.id] || 0, etape: null, niveau: zoomNiveau, propulsion: propulsion && domDe[j.id] === propulsion.label ? propulsion.progress : undefined },
        selected: selection.includes(j.id),
      };
    })
  );

  let es = [];
  let snapMain = null;
  const posMain = Object.fromEntries(twins.map((j) => [j.id, posOverrides[j.id] || j.position]));
  if (entreprise) {
    // Zoom Entreprise : corridors agrégés inter-domaines
    const regParDom = {};
    (mesh.regions || []).forEach((r) => { regParDom[r.label] = r.id; });
    const posRegions = Object.fromEntries(ns.filter((n) => n.type === "region").map((n) => [n.id, { x: n.position.x + n.initialWidth / 2, y: n.position.y + n.initialHeight / 2 }]));
    const corridors = {};
    mesh.relations.forEach((r) => {
      const a = domDe[r.source];
      const b = domDe[r.cible];
      if (!a || !b || a === b || !regParDom[a] || !regParDom[b]) return;
      const [x, y] = [a, b].sort();
      const key = `${x}::${y}`;
      if (!corridors[key]) corridors[key] = { a: x, b: y, n: 0, actif: false };
      corridors[key].n += 1;
      if (r.active) corridors[key].actif = true;
    });
    es = Object.values(corridors).map((c) => {
      const ps = posRegions[regParDom[c.a]];
      const pt = posRegions[regParDom[c.b]];
      const droite = ps && pt ? pt.x - ps.x >= 0 : true;
      return {
        id: `corridor-${c.a}-${c.b}`,
        source: regParDom[c.a],
        target: regParDom[c.b],
        sourceHandle: droite ? "s-r" : "s-l",
        targetHandle: droite ? "t-l" : "t-r",
        type: "smoothstep",
        pathOptions: { borderRadius: 10 },
        interactionWidth: 8,
        animated: c.actif,
        style: { stroke: "rgba(17,17,16,0.3)", strokeWidth: 2.5, opacity: 0.8 },
        label: `${c.a} ↔ ${c.b} · ${c.n} relation${c.n > 1 ? "s" : ""}${c.actif ? " · activité élevée" : ""}`,
        labelStyle: { fill: "rgba(17,17,16,0.7)", fontSize: 10, fontFamily: "IBM Plex Mono" },
        labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
      };
    });
  } else {
    es = fabriqueOrtho(
      mesh.relations
        .filter((r) => (situation && implique.length ? implique.includes(r.source) && implique.includes(r.cible) : true))
        .filter((r) => !focus || r.source === focus || r.cible === focus),
      ns,
      posMain,
      zoomNiveau,
      zoomFort,
      routesFin,
      provisoire
    );
    snapMain = es.snapshot;
    es = es.edges;
    if (vueActive?.type === "relations_non_confirmees") {
      es = es.map((e) =>
        e.data?.etat === "confirmee" ? { ...e, animated: false, style: { ...e.style, opacity: 0.1 } } : e
      );
    }
    if (relFocus && selection.length > 1) {
      es = es.filter((e) => selection.includes(e.source) && selection.includes(e.target));
    }
    if (focusCarte?.type === "relations" && focusCarte.ids?.length) {
      es = es.map((e) =>
        focusCarte.ids.includes(e.id)
          ? { ...e, animated: true, style: { ...e.style, opacity: 1, strokeWidth: 2.6 } }
          : { ...e, animated: false, style: { ...e.style, opacity: 0.08 } }
      );
    }
  }
  if (entreprise) {
    // Niveau 1 — Capacités et macro-territoires : agrégats par territoire, robots masqués
    const macro = ns
      .filter((n) => n.type !== "twin")
      .map((n) => ({ ...n, data: { ...n.data, macro: true } }));
    return { nodes: macro, edges: repartirOffsets(appliquerTemps(es, temps)), snapshot: null };
  }
  return { nodes: ns, edges: appliquerTemps(es, temps), snapshot: snapMain };
}
