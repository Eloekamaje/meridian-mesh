import { useCallback, useEffect, useRef, useState } from "react";

// Pont Atlas ↔ Web Worker libavoid : le calcul final des arêtes est asynchrone,
// les anciens trajets sont interpolés vers les nouveaux en 240 ms (jamais de saut visuel).
// Si le Worker/WASM est indisponible, l'Atlas conserve le routeur maison synchrone (secours).
let workerSingleton;
function obtenirWorker() {
  if (workerSingleton !== undefined) return workerSingleton;
  try {
    workerSingleton = new Worker(new URL("./routageWorker.js", import.meta.url), { type: "module" });
  } catch {
    workerSingleton = null;
  }
  return workerSingleton;
}

const r2 = (v) => Math.round(v / 2);
function signatureDe(snap) {
  return JSON.stringify({
    s: snap.shapes.map((s) => [s.id, r2(s.x0), r2(s.y0), r2(s.x1), r2(s.y1)]),
    o: snap.obstacles.map((o) => [r2(o.x0), r2(o.y0), r2(o.x1), r2(o.y1)]),
    e: snap.edges.map((e) => [e.id, e.source, e.target, e.sourcePort, e.targetPort]),
  });
}

// Ports worker (n/e/s/w) → nos côtés de handles (t/b/l/r)
const PORT_VERS_COTE = { n: "t", s: "b", e: "r", w: "l" };

// Interpolation point à point (les tableaux sont égalisés en répétant les extrémités)
function combiner(a, b, e) {
  const n = Math.max(a.length, b.length);
  const pa = a.length === n ? a : [...a, ...Array(n - a.length).fill(a[a.length - 1])];
  const pb = b.length === n ? b : [...b, ...Array(n - b.length).fill(b[b.length - 1])];
  return pa.map((p, i) => ({ x: p.x + (pb[i].x - p.x) * e, y: p.y + (pb[i].y - p.y) * e }));
}

export function useRoutageFinal() {
  const [routesFin, setRoutesFin] = useState({});
  const routesRef = useRef({});
  const anim = useRef(null);
  const seqEnvoye = useRef(0);
  const signatureRef = useRef("");
  const snapshotRef = useRef(null);

  const animer = useCallback((nouvelles) => {
    cancelAnimationFrame(anim.current);
    const anciennes = routesRef.current;
    const t0 = performance.now();
    const DUREE = 240;
    const pas = (t) => {
      const k = Math.min(1, (t - t0) / DUREE);
      const e = 1 - Math.pow(1 - k, 3); // easing out
      const inter = {};
      for (const id of Object.keys(nouvelles)) {
        const n = nouvelles[id];
        const a = anciennes[id];
        inter[id] =
          a?.points && a.sp === n.sp && a.tp === n.tp && k < 1
            ? { ...n, points: combiner(a.points, n.points, e) }
            : n;
      }
      routesRef.current = inter;
      setRoutesFin(inter);
      if (k < 1) anim.current = requestAnimationFrame(pas);
    };
    anim.current = requestAnimationFrame(pas);
  }, []);

  useEffect(() => {
    const w = obtenirWorker();
    if (!w) return undefined;
    const surMessage = (ev) => {
      const { seq, routes, error } = ev.data || {};
      if (error) {
        console.warn("[routage] Worker libavoid en échec, routeur maison conservé :", error);
        return;
      }
      if (seq !== seqEnvoye.current || !routes) return; // réponse obsolète
      const ports = {};
      (snapshotRef.current?.edges || []).forEach((ed) => {
        ports[ed.id] = { sp: PORT_VERS_COTE[ed.sourcePort], tp: PORT_VERS_COTE[ed.targetPort] };
      });
      const nouvelles = {};
      Object.entries(routes).forEach(([id, points]) => {
        if (points?.length >= 2) nouvelles[id] = { points, ...(ports[id] || {}) };
      });
      animer(nouvelles);
    };
    w.addEventListener("message", surMessage);
    return () => w.removeEventListener("message", surMessage);
  }, [animer]);

  // Nouveau snapshot géométrique → calcul final (dédupliqué par signature arrondie)
  const pousser = useCallback((snapshot) => {
    const w = obtenirWorker();
    if (!snapshot || !w) return;
    const sig = signatureDe(snapshot);
    if (sig === signatureRef.current) return;
    signatureRef.current = sig;
    snapshotRef.current = snapshot;
    seqEnvoye.current += 1;
    w.postMessage({ seq: seqEnvoye.current, shapes: snapshot.shapes, obstacles: snapshot.obstacles, edges: snapshot.edges });
  }, []);

  useEffect(() => () => cancelAnimationFrame(anim.current), []);

  return { routesFin, pousser };
}
