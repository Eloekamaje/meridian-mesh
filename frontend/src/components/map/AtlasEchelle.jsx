import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { chargerSprites } from "@/lib/spritesRobot";
import { COULEURS_DOMAINES, NOMS_DOMAINES } from "@/lib/laboEchelle";
import { idNumerique } from "@/lib/atlasGraph";

// ============================================================================================
// ATLAS À L'ÉCHELLE — le Mesh servi par vue (GET /api/mesh/vue). Le navigateur ne charge jamais le graphe
// entier : il envoie la fenêtre visible et le zoom ; le serveur répond avec un nombre borné de grappes
// (domaine → groupe → communauté), de points ou de jumeaux, déjà filtrés par le périmètre du persona.
// Tant que la réponse arrive, la précédente est redessinée à la nouvelle échelle : le mouvement reste fluide.
// Même langage visuel que l'Atlas : robots teintés par domaine, écarts en violet, situations en orange.
// ============================================================================================

const DELAI_MS = 90;
const MARGE = 0.15;
const ORANGE = "#F59E0B";
const VIOLET = "#A78BFA";
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} k` : String(n)).replace(".", ",");
const NIVEAUX = { 0: "Jumeaux", 1: "Communautés", 2: "Groupes", 3: "Domaines" };
const hex2 = (k) => Math.round(Math.max(0, Math.min(1, k)) * 255).toString(16).padStart(2, "0");

export function cadrageInitial(n, l, h) {
  if (!n) return { cx: 700, cy: 400, zoom: Math.min(l / 1500, h / 900) };
  const cote = 900 * Math.sqrt(Math.max(n / 60, 4));
  return { cx: cote / 2, cy: cote / 2, zoom: Math.min(l, h) / (cote * 1.1) };
}

export default function AtlasEchelle({ synthetique = null, selectionId = null, onChoisir, className = "" }) {
  const cadre = useRef(null);
  const canvas = useRef(null);
  const vue = useRef({ cx: 0, cy: 0, zoom: 1 });
  const rep = useRef(null);
  const sprites = useRef([]);
  const minuteur = useRef(null);
  const envol = useRef(null);
  const vol = useRef(null);
  const survolRef = useRef(null);
  const propsRef = useRef({});
  const [stats, setStats] = useState(null);
  const [apercu, setApercu] = useState(null);
  propsRef.current = { synthetique, selectionId, onChoisir };

  const couleurs = useCallback((r) => {
    const noms = r?.domaines || [];
    return (d) => COULEURS_DOMAINES[NOMS_DOMAINES.indexOf(noms[d]) >= 0 ? NOMS_DOMAINES.indexOf(noms[d]) : d % COULEURS_DOMAINES.length];
  }, []);

  const dessiner = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const l = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(l * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(l * dpr); c.height = Math.round(h * dpr); }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, l, h);
    const r = rep.current;
    if (!r) return;
    const { cx, cy, zoom } = vue.current;
    const px = (x) => (x - cx) * zoom + l / 2;
    const py = (y) => (y - cy) * zoom + h / 2;
    const col = couleurs(r);
    const survol = survolRef.current;

    if (r.grappes?.length) {
      const parIndice = r.grappes;
      ctx.lineCap = "round";
      for (const e of r.liens || []) {
        const a = parIndice[e.a], b = parIndice[e.b];
        if (!a || !b) continue;
        ctx.strokeStyle = "rgba(148,163,184,.32)";
        ctx.lineWidth = Math.min(4, 0.6 + Math.log2(e.poids + 1) * 0.35);
        ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
      }
      const fondu = r.fondu || 0;
      if (r.enfants && fondu > 0.02) for (const g of r.enfants) {
        ctx.beginPath(); ctx.arc(px(g.x), py(g.y), Math.max(2, g.r * zoom), 0, 6.2832);
        ctx.fillStyle = `${col(g.dom)}${hex2(fondu * 0.22)}`; ctx.fill();
      }
      const pris = [];
      for (const g of [...parIndice].sort((a, b) => b.n - a.n)) {
        const rr = Math.max(3, g.r * zoom);
        const chaud = survol?.type === "grappe" && survol.id === g.id && survol.niv === g.niv;
        ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr, 0, 6.2832);
        ctx.fillStyle = `${col(g.dom)}${r.niveau === 1 ? "38" : r.niveau === 2 ? "2e" : "26"}`; ctx.fill();
        ctx.strokeStyle = `${col(g.dom)}${chaud ? "ff" : r.niveau === 3 ? "cc" : "99"}`; ctx.lineWidth = chaud ? 2.2 : 1.2; ctx.stroke();
        if (g.ecarts) { ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr + 3, 0, 6.2832); ctx.strokeStyle = VIOLET; ctx.lineWidth = 1.6; ctx.stroke(); }
        if (g.alertes) { ctx.beginPath(); ctx.arc(px(g.x), py(g.y), rr + 6, 0, 6.2832); ctx.strokeStyle = ORANGE; ctx.lineWidth = 1.6; ctx.stroke(); }
        const boite = [px(g.x) - 62, py(g.y) - 14, px(g.x) + 62, py(g.y) + 18];
        if (rr > 26 && !pris.some((q) => boite[0] < q[2] && boite[2] > q[0] && boite[1] < q[3] && boite[3] > q[1])) {
          pris.push(boite);
          ctx.textAlign = "center";
          ctx.fillStyle = "rgba(226,232,240,.95)"; ctx.font = "600 12px Inter, system-ui, sans-serif"; ctx.fillText(g.nom, px(g.x), py(g.y) - 2);
          ctx.fillStyle = "rgba(148,163,184,.95)"; ctx.font = "11px Inter, system-ui, sans-serif"; ctx.fillText(`${compact(g.n)} jumeaux`, px(g.x), py(g.y) + 13);
        }
      }
    }

    if (r.points) {
      const { x, y, d, e, a } = r.points;
      for (let i = 0; i < x.length; i++) { ctx.fillStyle = a[i] ? ORANGE : e[i] ? VIOLET : col(d[i]); ctx.fillRect(px(x[i]) - 1, py(y[i]) - 1, 2.2, 2.2); }
    }

    if (r.jumeaux?.length) {
      const pos = new Map(r.jumeaux.map((j) => [j.i, j]));
      const focus = survol?.type === "jumeau" ? survol.i : null;
      const voisins = new Set();
      if (focus != null) { voisins.add(focus); for (const e of r.liens || []) { if (e.source === focus) voisins.add(e.cible); if (e.cible === focus) voisins.add(e.source); } }
      ctx.lineWidth = 1;
      for (const e of r.liens || []) {
        const a = pos.get(e.source), b = pos.get(e.cible);
        if (!a || !b) continue;
        const incident = focus != null && (e.source === focus || e.cible === focus);
        ctx.globalAlpha = focus == null ? 1 : incident ? 1 : 0.08;
        ctx.strokeStyle = e.etat === 2 ? "rgba(167,139,250,.65)" : e.etat === 1 ? "rgba(32,213,195,.5)" : "rgba(148,163,184,.34)";
        ctx.lineWidth = incident ? 2 : 1;
        ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
      }
      ctx.globalAlpha = 1;
      const echelle = r.source === "reel" ? 34 : 11; // hauteur monde d'un robot moyen (l'espacement réel est plus grand)
      const maxDeg = Math.max(1, ...r.jumeaux.map((j) => j.degre));
      for (const j of r.jumeaux) {
        const haut = Math.max(6, echelle * 1.9 * (0.65 + 0.5 * (j.degre / maxDeg)) * zoom);
        const dim = focus != null && !voisins.has(j.i);
        ctx.globalAlpha = dim ? 0.2 : 1;
        const spr = sprites.current[NOMS_DOMAINES.indexOf(r.domaines?.[j.dom]) >= 0 ? NOMS_DOMAINES.indexOf(r.domaines[j.dom]) : j.dom % COULEURS_DOMAINES.length];
        const x = px(j.x), y = py(j.y);
        if (spr && haut >= 10) ctx.drawImage(spr, x - haut * 0.326, y - haut / 2, haut * 0.652, haut);
        else { ctx.beginPath(); ctx.arc(x, y, Math.max(2.5, haut * 0.3), 0, 6.2832); ctx.fillStyle = col(j.dom); ctx.fill(); }
        if (j.ecart || j.alerte) { ctx.beginPath(); ctx.arc(x, y, Math.max(4, haut * 0.42), 0, 6.2832); ctx.strokeStyle = j.alerte ? ORANGE : VIOLET; ctx.lineWidth = 1.5; ctx.setLineDash(j.alerte ? [] : [4, 3]); ctx.stroke(); ctx.setLineDash([]); }
        if (j.id && (haut >= 36 || j.i === focus || j.id === propsRef.current.selectionId)) {
          ctx.fillStyle = "rgba(216,226,234,.95)"; ctx.font = "600 10px 'JetBrains Mono', monospace"; ctx.textAlign = "center";
          ctx.fillText(idNumerique(j.id), x, y + haut / 2 + 11);
        }
        if (j.id && j.id === propsRef.current.selectionId) { ctx.beginPath(); ctx.arc(x, y, haut * 0.6, 0, 6.2832); ctx.strokeStyle = "#20D5C3"; ctx.lineWidth = 2; ctx.stroke(); }
        ctx.globalAlpha = 1;
      }
    }
  }, [couleurs]);

  const demander = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const { cx, cy, zoom } = vue.current;
    const l = c.clientWidth / zoom, h = c.clientHeight / zoom;
    const params = { x0: cx - (l / 2) * (1 + MARGE), y0: cy - (h / 2) * (1 + MARGE), x1: cx + (l / 2) * (1 + MARGE), y1: cy + (h / 2) * (1 + MARGE), zoom };
    if (propsRef.current.synthetique) params.synthetique = propsRef.current.synthetique;
    envol.current?.abort();
    const ctl = (envol.current = new AbortController());
    const t0 = performance.now();
    api.get("/mesh/vue", { params, signal: ctl.signal }).then((res) => {
      const d = res.data;
      rep.current = d;
      setStats({ mode: d.mode, niveau: d.niveau, total: d.n_total, serveur: d.duree_ms, allerRetour: Math.round(performance.now() - t0), perimetre: d.perimetre });
      dessiner();
    }).catch(() => {});
  }, [dessiner]);

  const planifier = useCallback(() => {
    if (survolRef.current) { survolRef.current = null; setApercu(null); } // la vue bouge : l'aperçu ne désigne plus rien
    dessiner();
    clearTimeout(minuteur.current);
    minuteur.current = setTimeout(demander, DELAI_MS);
  }, [dessiner, demander]);

  const voler = useCallback((cx, cy, zoom, ms = 550) => {
    cancelAnimationFrame(vol.current);
    const de = { ...vue.current };
    const t0 = performance.now();
    const pas = (t) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - (1 - k) ** 3;
      const z = de.zoom * (zoom / de.zoom) ** e; // interpolation géométrique du zoom : vitesse perçue constante
      vue.current = { cx: de.cx + (cx - de.cx) * e, cy: de.cy + (cy - de.cy) * e, zoom: z };
      planifier();
      if (k < 1) vol.current = requestAnimationFrame(pas);
    };
    vol.current = requestAnimationFrame(pas);
  }, [planifier]);

  // Objet le plus proche du curseur : jumeau (rayon d'un robot) ou grappe (dans son disque, la plus petite d'abord)
  const cible = useCallback((mx, my) => {
    const r = rep.current, c = canvas.current;
    if (!r || !c) return null;
    const { cx, cy, zoom } = vue.current;
    const l = c.clientWidth, h = c.clientHeight;
    const wx = (mx - l / 2) / zoom + cx, wy = (my - h / 2) / zoom + cy;
    if (r.jumeaux?.length) {
      let best = null, bd = Infinity;
      const rayon = Math.max(10, (r.source === "reel" ? 34 : 11) * 0.95 * zoom);
      for (const j of r.jumeaux) { const d = Math.hypot((j.x - wx) * zoom, (j.y - wy) * zoom); if (d < rayon && d < bd) { bd = d; best = j; } }
      return best && { type: "jumeau", ...best };
    }
    if (r.grappes?.length) {
      let best = null;
      for (const g of r.grappes) if (Math.hypot(g.x - wx, g.y - wy) <= g.r && (!best || g.r < best.r)) best = g;
      return best && { type: "grappe", ...best };
    }
    return null;
  }, []);

  useEffect(() => {
    const c = canvas.current;
    vue.current = cadrageInitial(propsRef.current.synthetique, c.clientWidth, c.clientHeight);
    rep.current = null;
    chargerSprites().then((s) => { sprites.current = s; dessiner(); });
    planifier();

    const onRoue = (e) => {
      e.preventDefault();
      cancelAnimationFrame(vol.current);
      const b = c.getBoundingClientRect(), v = vue.current;
      const z = Math.min(64, Math.max(0.0005, v.zoom * Math.exp(-e.deltaY * 0.0016)));
      const mx = e.clientX - b.left - c.clientWidth / 2, my = e.clientY - b.top - c.clientHeight / 2;
      vue.current = { cx: v.cx + mx / v.zoom - mx / z, cy: v.cy + my / v.zoom - my / z, zoom: z };
      survolRef.current = null; setApercu(null);
      planifier();
    };
    let prise = null, deplace = false;
    const bas = (e) => { prise = { x: e.clientX, y: e.clientY }; deplace = false; cancelAnimationFrame(vol.current); c.setPointerCapture(e.pointerId); };
    const bouge = (e) => {
      const b = c.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
      if (prise) {
        const dx = e.clientX - prise.x, dy = e.clientY - prise.y;
        if (Math.abs(dx) + Math.abs(dy) > 2) deplace = true;
        vue.current.cx -= dx / vue.current.zoom; vue.current.cy -= dy / vue.current.zoom;
        prise = { x: e.clientX, y: e.clientY };
        survolRef.current = null; setApercu(null);
        planifier();
        return;
      }
      const t = cible(mx, my);
      const avant = survolRef.current;
      const meme = avant && t && avant.type === t.type && (t.type === "jumeau" ? avant.i === t.i : avant.id === t.id && avant.niv === t.niv);
      if (!meme) { survolRef.current = t; dessiner(); }
      c.style.cursor = t ? "pointer" : "grab";
      setApercu(t ? { ...t, left: Math.min(mx + 16, c.clientWidth - 250), top: Math.max(8, Math.min(my + 12, c.clientHeight - 130)) } : null);
    };
    const haut = (e) => {
      const etaitPris = prise; prise = null;
      if (!etaitPris || deplace) return;
      const b = c.getBoundingClientRect();
      const t = cible(e.clientX - b.left, e.clientY - b.top);
      if (!t) return;
      if (t.type === "grappe") {
        // La grappe s'ouvre : on plonge dessus jusqu'à ce que ses enfants deviennent lisibles
        voler(t.x, t.y, Math.min(64, Math.max(vue.current.zoom * 2.2, (Math.min(c.clientWidth, c.clientHeight) * 0.42) / t.r)));
      } else propsRef.current.onChoisir?.(t);
    };
    const quitte = () => { survolRef.current = null; setApercu(null); dessiner(); };
    const ro = new ResizeObserver(() => planifier());
    ro.observe(cadre.current);
    c.addEventListener("wheel", onRoue, { passive: false });
    c.addEventListener("pointerdown", bas); c.addEventListener("pointermove", bouge); c.addEventListener("pointerup", haut); c.addEventListener("pointerleave", quitte);
    window.__atlasEchelle = { vue: () => vue.current, aller: (cx, cy, zoom) => { vue.current = { cx, cy, zoom }; planifier(); }, rep: () => rep.current };
    return () => {
      c.removeEventListener("wheel", onRoue); c.removeEventListener("pointerdown", bas); c.removeEventListener("pointermove", bouge); c.removeEventListener("pointerup", haut); c.removeEventListener("pointerleave", quitte);
      ro.disconnect(); clearTimeout(minuteur.current); cancelAnimationFrame(vol.current); envol.current?.abort(); delete window.__atlasEchelle;
    };
  }, [synthetique, cible, dessiner, planifier, voler]);

  useEffect(() => { dessiner(); }, [selectionId, dessiner]);

  return (
    <div ref={cadre} className={`relative h-full w-full ${className}`} data-testid="atlas-echelle" style={{ backgroundImage: "radial-gradient(rgba(148,163,184,0.13) 1px, transparent 1px)", backgroundSize: "26px 26px" }}>
      <canvas ref={canvas} className="absolute inset-0 h-full w-full cursor-grab touch-none" />
      {stats && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] leading-5 text-[#7C93A8]" data-testid="atlas-echelle-hud">
          {compact(stats.total)} jumeaux · vue {NIVEAUX[stats.niveau] || "Jumeaux"}{stats.mode === "points" ? " (points)" : ""}
          <span className="ml-2 text-[#526578]">{stats.serveur} ms serveur · {stats.allerRetour} ms</span>
        </div>
      )}
      {apercu && (
        <div className="pointer-events-none absolute z-20 w-[230px] space-y-1 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3 shadow-2xl backdrop-blur-xl" style={{ left: apercu.left, top: apercu.top }} data-testid="atlas-echelle-apercu">
          {apercu.type === "grappe" ? (
            <>
              <div className="text-xs font-semibold text-[#F2F6F8]">{apercu.nom}</div>
              <div className="font-code text-[10px] text-[#94A3B8]">{NIVEAUX[apercu.niv]} · {compact(apercu.n)} jumeaux</div>
              {apercu.ecarts > 0 && <div className="font-code text-[10px]" style={{ color: VIOLET }}>{compact(apercu.ecarts)} en écart (déclaré ≠ observé)</div>}
              {apercu.alertes > 0 && <div className="font-code text-[10px]" style={{ color: ORANGE }}>{compact(apercu.alertes)} en situation active</div>}
              <div className="pt-0.5 font-code text-[9px] text-[#25D0C8]">Clic : s'approcher →</div>
            </>
          ) : (
            <>
              <div className="text-xs font-semibold text-[#F2F6F8]">{apercu.id ? `${idNumerique(apercu.id)} · ${apercu.id}` : `Jumeau ${apercu.i}`}</div>
              <div className="font-code text-[10px] text-[#94A3B8]">{rep.current?.domaines?.[apercu.dom]} · {apercu.degre} relation{apercu.degre > 1 ? "s" : ""}</div>
              {apercu.ecart > 0 && <div className="font-code text-[10px]" style={{ color: VIOLET }}>Écart : couplé surtout à un autre domaine</div>}
              {apercu.alerte > 0 && <div className="font-code text-[10px]" style={{ color: ORANGE }}>Situation active</div>}
              {apercu.id && <div className="pt-0.5 font-code text-[9px] text-[#25D0C8]">Clic : ouvrir le jumeau →</div>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
