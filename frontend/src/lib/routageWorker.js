// Web Worker — routage final des arêtes par libavoid (WASM).
// Reçoit un snapshot géométrique (formes connectables + obstacles + arêtes avec ports),
// calcule les routes orthogonales avec évitement d'obstacles, renvoie les points.
import { AvoidLib } from "libavoid-js";

let chargement = null;
function ensure() {
  if (!chargement) chargement = AvoidLib.load("/libavoid.wasm").then(() => AvoidLib.getInstance());
  return chargement;
}

// Ports N/E/S/W : classIds stables par forme
const PINS = { n: [1, 0.5, 0], e: [2, 1, 0.5], s: [3, 0.5, 1], w: [4, 0, 0.5] };
const CONN_DIR_ALL = 15;

// Retire doublons et points colinéaires du trajet renvoyé par libavoid
function epurer(pts) {
  const out = [];
  for (const p of pts) {
    const d = out[out.length - 1];
    if (d && Math.abs(d.x - p.x) < 0.5 && Math.abs(d.y - p.y) < 0.5) continue;
    const d2 = out[out.length - 2];
    if (d2 && d) {
      const h = Math.abs(d2.y - d.y) < 0.5 && Math.abs(d.y - p.y) < 0.5;
      const v = Math.abs(d2.x - d.x) < 0.5 && Math.abs(d.x - p.x) < 0.5;
      if (h || v) out.pop();
    }
    out.push({ x: Math.round(p.x * 10) / 10, y: Math.round(p.y * 10) / 10 });
  }
  return out;
}

self.onmessage = async (e) => {
  const { seq, shapes, obstacles, edges } = e.data || {};
  try {
    const Avoid = await ensure();
    const orthogonal = Avoid.RouterFlag.OrthogonalRouting;
    const router = new Avoid.Router(typeof orthogonal === "object" ? orthogonal.value : orthogonal);
    // Fonction de coût — hiérarchie de la spec :
    // croisement (140) >> voie partagée (80) > proximité obstacle (marge 16) > coude (24) > longueur
    router.setRoutingParameter(Avoid.RoutingParameter.crossingPenalty, 140);
    router.setRoutingParameter(Avoid.RoutingParameter.fixedSharedPathPenalty, 80);
    // Buffer réduit (6 px) : un buffer trop large ferme les corridors entre rangées de
    // jumeaux (séparation 105 px) et force des détours rectangulaires autour des grappes
    router.setRoutingParameter(Avoid.RoutingParameter.shapeBufferDistance, 6);
    router.setRoutingParameter(Avoid.RoutingParameter.anglePenalty, 24);
    router.setRoutingParameter(Avoid.RoutingParameter.segmentPenalty, 10);
    router.setRoutingParameter(Avoid.RoutingParameter.idealNudgingDistance, 6);
    router.setRoutingOption(Avoid.RoutingOption.nudgeOrthogonalSegmentsConnectedToShapes, true);
    router.setRoutingOption(Avoid.RoutingOption.nudgeSharedPathsWithCommonEndPoint, true);

    const refs = {};
    for (const s of [...shapes, ...obstacles]) {
      const rect = new Avoid.Rectangle(new Avoid.Point(s.x0, s.y0), new Avoid.Point(s.x1, s.y1));
      const ref = new Avoid.ShapeRef(router, rect);
      refs[s.id] = ref;
      if (s.pins !== false) {
        for (const [classId, px, py] of Object.values(PINS)) {
          new Avoid.ShapeConnectionPin(ref, classId, px, py, true, 0, CONN_DIR_ALL);
        }
      }
    }

    // Routage par priorité décroissante : les relations importantes reçoivent les corridors directs
    const conns = {};
    const triees = [...edges].sort((a, b) => (b.priorite || 0) - (a.priorite || 0));
    for (const ed of triees) {
      const rs = refs[ed.source];
      const rt = refs[ed.target];
      if (!rs || !rt || !PINS[ed.sourcePort] || !PINS[ed.targetPort]) continue;
      const src = new Avoid.ConnEnd(rs, PINS[ed.sourcePort][0]);
      const dst = new Avoid.ConnEnd(rt, PINS[ed.targetPort][0]);
      conns[ed.id] = new Avoid.ConnRef(router, src, dst);
    }

    router.processTransaction();

    const routes = {};
    for (const ed of edges) {
      const c = conns[ed.id];
      if (!c) continue;
      const r = c.displayRoute();
      const pts = [];
      for (let i = 0; i < r.size(); i++) pts.push(r.at(i));
      const epures = epurer(pts);
      if (epures.length >= 2) routes[ed.id] = epures;
    }
    router.delete();
    if (!self.__routagePret) { self.__routagePret = true; console.info("[routage] libavoid actif —", Object.keys(routes).length, "routes finales"); }
    self.postMessage({ seq, routes });
  } catch (err) {
    self.postMessage({ seq, error: String((err && err.message) || err) });
  }
};
