import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Flask } from "@phosphor-icons/react";
import api from "@/lib/api";
import { COULEURS_DOMAINES } from "@/lib/laboEchelle";

// ============================================================================================
// LABORATOIRE — le Mesh servi PAR VUE : le navigateur ne charge jamais le graphe entier. Il envoie la
// fenêtre (monde) et le zoom à GET /api/mesh/vue ; le serveur répond avec un nombre borné de grappes,
// de points ou de jumeaux, respectant le périmètre du persona. Tant que la réponse arrive, on redessine
// l'ancienne à la nouvelle échelle : le déplacement reste fluide.
// ============================================================================================

const SOURCES = [["reel", "Mesh réel"], [10000, "10 000"], [100000, "100 000"], [1000000, "1 000 000"], [5000000, "5 000 000"]];
const DELAI_MS = 90;
const MARGE = 0.15;
const ORANGE = "#F59E0B";
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} k` : String(n)).replace(".", ",");
const couleur = (d) => COULEURS_DOMAINES[d % COULEURS_DOMAINES.length];

function cadrageInitial(source, l, h) {
  if (source === "reel") return { cx: 700, cy: 400, zoom: Math.min(l / 1500, h / 900) };
  const cote = 900 * Math.sqrt(Math.max(source / 60, 4));
  return { cx: cote / 2, cy: cote / 2, zoom: Math.min(l, h) / (cote * 1.1) };
}

export default function LaboServeur() {
  const cadre = useRef(null);
  const canvas = useRef(null);
  const vue = useRef({ cx: 0, cy: 0, zoom: 1 });
  const rep = useRef(null);
  const source = useRef("reel");
  const minuteur = useRef(null);
  const envol = useRef(null);
  const [src, setSrc] = useState("reel");
  const [stats, setStats] = useState(null);

  const dessiner = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const l = c.clientWidth, h = c.clientHeight;
    if (c.width !== l * dpr || c.height !== h * dpr) { c.width = l * dpr; c.height = h * dpr; }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, l, h);
    const { cx, cy, zoom } = vue.current;
    const px = (x) => (x - cx) * zoom + l / 2;
    const py = (y) => (y - cy) * zoom + h / 2;
    const r = rep.current;
    if (!r) return;
    if (r.grappes?.length) {
      const pos = new Map(r.grappes.map((g, i) => [i, g]));
      ctx.lineCap = "round";
      for (const e of r.liens || []) {
        const a = pos.get(e.a), b = pos.get(e.b);
        if (!a || !b) continue;
        ctx.strokeStyle = "rgba(148,163,184,.35)";
        ctx.lineWidth = Math.min(4, 0.6 + Math.log2(e.poids + 1) * 0.35);
        ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
      }
      const fondu = r.fondu || 0;
      if (r.enfants) for (const g of r.enfants) {
        ctx.beginPath(); ctx.arc(px(g.x), py(g.y), Math.max(2, g.r * zoom), 0, 6.2832);
        ctx.fillStyle = `${couleur(g.dom)}${Math.round(fondu * 56).toString(16).padStart(2, "0")}`; ctx.fill();
      }
      const pris = [];  // libellés déjà posés : on n'en superpose pas
      for (const g of [...r.grappes].sort((a, b) => b.n - a.n)) {
        const rr = Math.max(3, g.r * zoom);
        ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr, 0, 6.2832);
        ctx.fillStyle = `${couleur(g.dom)}${r.niveau === 1 ? "38" : r.niveau === 2 ? "2e" : "26"}`; ctx.fill();
        ctx.strokeStyle = `${couleur(g.dom)}${r.niveau === 3 ? "cc" : "99"}`; ctx.lineWidth = 1.2; ctx.stroke();
        if (g.ecarts) { ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr + 3, 0, 6.2832); ctx.strokeStyle = "#A78BFA"; ctx.lineWidth = 1.6; ctx.stroke(); }
        if (g.alertes) { ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr + 6, 0, 6.2832); ctx.strokeStyle = ORANGE; ctx.lineWidth = 1.6; ctx.stroke(); }
        const boite = [px(g.x) - 62, py(g.y) - 14, px(g.x) + 62, py(g.y) + 18];
        if (rr > 26 && !pris.some((q) => boite[0] < q[2] && boite[2] > q[0] && boite[1] < q[3] && boite[3] > q[1])) {
          pris.push(boite);
          ctx.fillStyle = "rgba(226,232,240,.95)"; ctx.font = "600 12px Inter, system-ui, sans-serif"; ctx.textAlign = "center";
          ctx.fillText(g.nom, px(g.x), py(g.y) - 2);
          ctx.fillStyle = "rgba(148,163,184,.95)"; ctx.font = "11px Inter, system-ui, sans-serif";
          ctx.fillText(`${compact(g.n)} jumeaux`, px(g.x), py(g.y) + 13);
        }
      }
    }
    if (r.points) {
      const { x, y, d, e, a } = r.points;
      for (let i = 0; i < x.length; i++) { ctx.fillStyle = a[i] ? ORANGE : e[i] ? "#A78BFA" : couleur(d[i]); ctx.fillRect(px(x[i]) - 1, py(y[i]) - 1, 2.2, 2.2); }
    }
    if (r.jumeaux?.length) {
      const pos = new Map(r.jumeaux.map((j) => [j.i, j]));
      ctx.lineWidth = 1;
      for (const e of r.liens || []) {
        const a = pos.get(e.source), b = pos.get(e.cible);
        if (!a || !b) continue;
        ctx.strokeStyle = e.etat === 2 ? "rgba(167,139,250,.6)" : "rgba(148,163,184,.3)";
        ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
      }
      const rr = Math.max(4, (r.source === "reel" ? 34 : 9) * zoom);
      for (const j of r.jumeaux) {
        ctx.beginPath(); ctx.arc(px(j.x), py(j.y), rr, 0, 6.2832);
        ctx.fillStyle = `${couleur(j.dom)}55`; ctx.fill();
        ctx.strokeStyle = j.alerte ? ORANGE : j.ecart ? "#A78BFA" : couleur(j.dom); ctx.lineWidth = 1.5; ctx.stroke();
        if (rr > 12 && j.id) { ctx.fillStyle = "rgba(226,232,240,.95)"; ctx.font = "11px Inter, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText(j.id, px(j.x), py(j.y) + rr + 13); }
      }
    }
  }, []);

  const demander = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const { cx, cy, zoom } = vue.current;
    const l = c.clientWidth / zoom, h = c.clientHeight / zoom;
    const params = { x0: cx - l / 2 * (1 + MARGE), y0: cy - h / 2 * (1 + MARGE), x1: cx + l / 2 * (1 + MARGE), y1: cy + h / 2 * (1 + MARGE), zoom };
    if (source.current !== "reel") params.synthetique = source.current;
    envol.current?.abort();
    const ctl = (envol.current = new AbortController());
    const t0 = performance.now();
    api.get("/mesh/vue", { params, signal: ctl.signal }).then((res) => {
      rep.current = res.data;
      const d = res.data;
      setStats({
        mode: d.mode, niveau: d.niveau, total: d.n_total, serveur: d.duree_ms, aller_retour: Math.round(performance.now() - t0),
        octets: JSON.stringify(d).length, elements: (d.grappes?.length || 0) + (d.jumeaux?.length || 0) + (d.points?.i?.length || 0), liens: d.liens?.length || 0,
      });
      dessiner();
    }).catch(() => {});
  }, [dessiner]);

  const planifier = useCallback(() => {
    dessiner();
    clearTimeout(minuteur.current);
    minuteur.current = setTimeout(demander, DELAI_MS);
  }, [dessiner, demander]);

  const changerSource = useCallback((s) => {
    source.current = s; setSrc(s); rep.current = null;
    const c = canvas.current;
    vue.current = cadrageInitial(s, c.clientWidth, c.clientHeight);
    planifier();
  }, [planifier]);

  useEffect(() => {
    changerSource("reel");
    const c = canvas.current;
    const onRoue = (e) => {
      e.preventDefault();
      const b = c.getBoundingClientRect(), v = vue.current;
      const f = Math.exp(-e.deltaY * 0.0016), z = Math.min(64, Math.max(0.0005, v.zoom * f));
      const mx = e.clientX - b.left - c.clientWidth / 2, my = e.clientY - b.top - c.clientHeight / 2;
      v.cx += mx / v.zoom - mx / z; v.cy += my / v.zoom - my / z; v.zoom = z;
      planifier();
    };
    let prise = null;
    const bas = (e) => { prise = { x: e.clientX, y: e.clientY }; c.setPointerCapture(e.pointerId); };
    const bouge = (e) => {
      if (!prise) return;
      vue.current.cx -= (e.clientX - prise.x) / vue.current.zoom; vue.current.cy -= (e.clientY - prise.y) / vue.current.zoom;
      prise = { x: e.clientX, y: e.clientY }; planifier();
    };
    const haut = () => { prise = null; };
    c.addEventListener("wheel", onRoue, { passive: false });
    c.addEventListener("pointerdown", bas); c.addEventListener("pointermove", bouge); c.addEventListener("pointerup", haut);
    const ro = new ResizeObserver(() => planifier());
    ro.observe(cadre.current);
    window.__serveur = { vue: vue.current, aller: (cx, cy, zoom) => { Object.assign(vue.current, { cx, cy, zoom }); planifier(); }, source: changerSource, rep: () => rep.current };
    return () => {
      c.removeEventListener("wheel", onRoue); c.removeEventListener("pointerdown", bas); c.removeEventListener("pointermove", bouge); c.removeEventListener("pointerup", haut);
      ro.disconnect(); clearTimeout(minuteur.current); envol.current?.abort(); delete window.__serveur;
    };
  }, [changerSource, planifier]);

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="labo-serveur">
      <div className="flex items-center gap-3 border-b border-white/10 px-5 py-3">
        <Flask size={18} className="text-violet-300" />
        <h1 className="text-sm font-semibold text-slate-100">Laboratoire · le Mesh servi par vue</h1>
        <div className="ml-auto flex items-center gap-1">
          {SOURCES.map(([v, label]) => (
            <button key={String(v)} onClick={() => changerSource(v)} data-testid={`source-${v}`}
              className={`rounded-md px-2.5 py-1 text-xs ${src === v ? "bg-violet-500/25 text-violet-100" : "text-slate-400 hover:bg-white/5"}`}>{label}</button>
          ))}
          <Link to="/labo/semantique" className="ml-2 text-xs text-slate-400 hover:text-slate-200">Prototype local</Link>
        </div>
      </div>
      <div ref={cadre} className="relative min-h-0 flex-1">
        <canvas ref={canvas} className="absolute inset-0 h-full w-full cursor-grab touch-none active:cursor-grabbing" />
        {stats && (
          <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg border border-white/10 bg-slate-950/80 px-3 py-2 text-[11px] leading-5 text-slate-300" data-testid="stats-serveur">
            <div><span className="text-slate-500">Mesh</span> {compact(stats.total)} jumeaux · <span className="text-slate-500">mode</span> {stats.mode}{stats.niveau ? ` (niveau ${stats.niveau})` : ""}</div>
            <div><span className="text-slate-500">Reçu</span> {stats.elements} éléments, {stats.liens} liens · {(stats.octets / 1024).toFixed(0)} Ko</div>
            <div><span className="text-slate-500">Serveur</span> {stats.serveur} ms · <span className="text-slate-500">aller-retour</span> {stats.aller_retour} ms</div>
          </div>
        )}
      </div>
    </div>
  );
}
