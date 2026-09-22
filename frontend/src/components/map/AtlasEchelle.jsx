import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { ecouterSprites, spriteRobot } from "@/lib/spritesRobot";
import { COULEURS_DOMAINES, NOMS_DOMAINES } from "@/lib/laboEchelle";
import { idNumerique } from "@/lib/atlasGraph";

// ============================================================================================
// ATLAS À L'ÉCHELLE — le Mesh servi par vue (GET /api/mesh/vue). Le navigateur ne charge jamais le graphe
// entier : il envoie la fenêtre visible et le zoom ; le serveur répond avec un nombre borné de VRAIS jumeaux
// (jamais une forme qui en tient lieu — pyramide.py, « il n'y a qu'un seul mode de réponse »), les mieux
// connectés d'abord quand il y en a plus que le budget. Tant que la réponse arrive, la précédente est
// redessinée à la nouvelle échelle : le mouvement reste fluide.
//
// UN SEUL langage de rendu, continu avec le zoom — jamais un « saut » d'un type de forme à un autre : chaque
// jumeau est un point qui grandit à mesure qu'on s'approche (un pixel loin, un robot reconnaissable près). La
// densité de points EST l'information — pas une bulle qui prétend la résumer.
// ============================================================================================

const DELAI_MS = 90;
const MARGE = 0.15;
const ORANGE = "#F59E0B";
const VIOLET = "#60A5FA";
const SEUIL_SPRITE = 10; // hauteur écran (px) en dessous de laquelle un robot n'est plus lisible : simple point
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} k` : String(n)).replace(".", ",");

export function cadrageInitial(n, l, h) {
  if (!n) return { cx: 700, cy: 400, zoom: Math.min(l / 1500, h / 900) };
  const cote = 900 * Math.sqrt(Math.max(n / 60, 4));
  return { cx: cote / 2, cy: cote / 2, zoom: Math.min(l, h) / (cote * 1.1) };
}

export default function AtlasEchelle({ synthetique = null, domaines = null, selectionId = null, onChoisir, className = "" }) {
  const cadre = useRef(null);
  const canvas = useRef(null);
  const vue = useRef({ cx: 0, cy: 0, zoom: 1 });
  const rep = useRef(null);
  const minuteur = useRef(null);
  const envol = useRef(null);
  const vol = useRef(null);
  const survolRef = useRef(null);
  const propsRef = useRef({});
  const [stats, setStats] = useState(null);
  const [apercu, setApercu] = useState(null);
  propsRef.current = { synthetique, domaines, selectionId, onChoisir };

  // Une couleur par domaine : celle que le serveur fournit (essai d'échelle à des centaines de domaines — voir
  // pyramide.palette_domaines) si elle est là, sinon la palette fixe historique du Mesh réel (repli).
  const couleurs = useCallback((r) => {
    const fournies = r?.domaines_couleur;
    const noms = r?.domaines || [];
    return (d) => fournies?.[d] || COULEURS_DOMAINES[NOMS_DOMAINES.indexOf(noms[d]) >= 0 ? NOMS_DOMAINES.indexOf(noms[d]) : d % COULEURS_DOMAINES.length];
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
    if (!r?.jumeaux?.length) return;
    const { cx, cy, zoom } = vue.current;
    const px = (x) => (x - cx) * zoom + l / 2;
    const py = (y) => (y - cy) * zoom + h / 2;
    const col = couleurs(r);
    const survol = survolRef.current;

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
      ctx.strokeStyle = e.etat === 2 ? "rgba(96,165,250,.65)" : e.etat === 1 ? "rgba(96,165,250,.5)" : "rgba(148,163,184,.34)";
      ctx.lineWidth = incident ? 2 : 1;
      ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // Un point qui GRANDIT en continu avec le zoom, jusqu'à devenir un robot reconnaissable — jamais un type
    // de forme différent : la même donnée (un jumeau), juste plus ou moins de détail visible dessus.
    const echelle = r.source === "reel" ? 34 : 11; // hauteur monde d'un robot moyen (l'espacement réel est plus grand)
    const maxDeg = Math.max(1, ...r.jumeaux.map((j) => j.degre));
    for (const j of r.jumeaux) {
      const haut = Math.max(1.4, echelle * 1.9 * (0.65 + 0.5 * (j.degre / maxDeg)) * zoom);
      const dim = focus != null && !voisins.has(j.i);
      ctx.globalAlpha = dim ? 0.2 : 1;
      const x = px(j.x), y = py(j.y);
      if (haut < SEUIL_SPRITE) {
        // Loin : un point minuscule (fillRect, le moins cher possible — des dizaines de milliers par image).
        ctx.fillStyle = j.alerte ? ORANGE : j.ecart ? VIOLET : col(j.dom);
        const d = Math.max(1.2, haut * 0.55);
        ctx.fillRect(x - d / 2, y - d / 2, d, d);
      } else {
        const spr = spriteRobot(col(j.dom));
        if (spr) ctx.drawImage(spr, x - haut * 0.326, y - haut / 2, haut * 0.652, haut);
        else { ctx.beginPath(); ctx.arc(x, y, haut * 0.3, 0, 6.2832); ctx.fillStyle = col(j.dom); ctx.fill(); }
        if (j.ecart || j.alerte) { ctx.beginPath(); ctx.arc(x, y, Math.max(4, haut * 0.42), 0, 6.2832); ctx.strokeStyle = j.alerte ? ORANGE : VIOLET; ctx.lineWidth = 1.5; ctx.setLineDash(j.alerte ? [] : [4, 3]); ctx.stroke(); ctx.setLineDash([]); }
        if (j.id && (haut >= 36 || j.i === focus || j.id === propsRef.current.selectionId)) {
          ctx.fillStyle = "rgba(216,226,234,.95)"; ctx.font = "600 10px 'JetBrains Mono', monospace"; ctx.textAlign = "center";
          ctx.fillText(idNumerique(j.id), x, y + haut / 2 + 11);
        }
      }
      if (j.id && j.id === propsRef.current.selectionId) { ctx.beginPath(); ctx.arc(x, y, Math.max(8, haut * 0.6), 0, 6.2832); ctx.strokeStyle = "#60A5FA"; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
  }, [couleurs]);

  const demander = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const { cx, cy, zoom } = vue.current;
    const l = c.clientWidth / zoom, h = c.clientHeight / zoom;
    const params = { x0: cx - (l / 2) * (1 + MARGE), y0: cy - (h / 2) * (1 + MARGE), x1: cx + (l / 2) * (1 + MARGE), y1: cy + (h / 2) * (1 + MARGE), zoom };
    if (propsRef.current.synthetique) { params.synthetique = propsRef.current.synthetique; params.domaines = propsRef.current.domaines || 8; }
    envol.current?.abort();
    const ctl = (envol.current = new AbortController());
    const t0 = performance.now();
    api.get("/mesh/vue", { params, signal: ctl.signal }).then((res) => {
      const d = res.data;
      rep.current = d;
      setStats({ rendus: d.jumeaux?.length || 0, total: d.n_total, serveur: d.duree_ms, allerRetour: Math.round(performance.now() - t0), perimetre: d.perimetre });
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

  // Jumeau le plus proche du curseur, dans le rayon d'un robot à ce zoom (même loin : le point reste cliquable).
  const cible = useCallback((mx, my) => {
    const r = rep.current, c = canvas.current;
    if (!r?.jumeaux?.length || !c) return null;
    const { cx, cy, zoom } = vue.current;
    const l = c.clientWidth, h = c.clientHeight;
    const wx = (mx - l / 2) / zoom + cx, wy = (my - h / 2) / zoom + cy;
    let best = null, bd = Infinity;
    const rayon = Math.max(9, (r.source === "reel" ? 34 : 11) * 0.95 * zoom);
    for (const j of r.jumeaux) { const d = Math.hypot((j.x - wx) * zoom, (j.y - wy) * zoom); if (d < rayon && d < bd) { bd = d; best = j; } }
    return best && { type: "jumeau", ...best };
  }, []);

  useEffect(() => {
    const c = canvas.current;
    vue.current = cadrageInitial(propsRef.current.synthetique, c.clientWidth, c.clientHeight);
    rep.current = null;
    const finEcoute = ecouterSprites(dessiner); // un sprite tardif (couleur inédite) redessine dès qu'il est prêt
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
      const meme = avant && t && avant.i === t.i;
      if (!meme) { survolRef.current = t; dessiner(); }
      c.style.cursor = t ? "pointer" : "grab";
      setApercu(t ? { ...t, left: Math.min(mx + 16, c.clientWidth - 250), top: Math.max(8, Math.min(my + 12, c.clientHeight - 130)) } : null);
    };
    const haut = (e) => {
      const etaitPris = prise; prise = null;
      if (!etaitPris || deplace) return;
      const b = c.getBoundingClientRect();
      const t = cible(e.clientX - b.left, e.clientY - b.top);
      if (t) propsRef.current.onChoisir?.(t);
    };
    // Double-clic : zoom continu sur le point visé (même geste de vol que la recherche — jamais un « saut »).
    const dbl = (e) => {
      const b = c.getBoundingClientRect(), v = vue.current;
      const l = c.clientWidth, h = c.clientHeight;
      const wx = (e.clientX - b.left - l / 2) / v.zoom + v.cx, wy = (e.clientY - b.top - h / 2) / v.zoom + v.cy;
      voler(wx, wy, Math.min(64, v.zoom * 2.4));
    };
    const quitte = () => { survolRef.current = null; setApercu(null); dessiner(); };
    const ro = new ResizeObserver(() => planifier());
    ro.observe(cadre.current);
    c.addEventListener("wheel", onRoue, { passive: false });
    c.addEventListener("pointerdown", bas); c.addEventListener("pointermove", bouge); c.addEventListener("pointerup", haut); c.addEventListener("pointerleave", quitte); c.addEventListener("dblclick", dbl);
    window.__atlasEchelle = { vue: () => vue.current, aller: (cx, cy, zoom) => { vue.current = { cx, cy, zoom }; planifier(); }, voler, rep: () => rep.current };
    return () => {
      c.removeEventListener("wheel", onRoue); c.removeEventListener("pointerdown", bas); c.removeEventListener("pointermove", bouge); c.removeEventListener("pointerup", haut); c.removeEventListener("pointerleave", quitte); c.removeEventListener("dblclick", dbl);
      ro.disconnect(); clearTimeout(minuteur.current); cancelAnimationFrame(vol.current); envol.current?.abort(); finEcoute(); delete window.__atlasEchelle;
    };
  }, [synthetique, domaines, cible, dessiner, planifier, voler]);

  useEffect(() => { dessiner(); }, [selectionId, dessiner]);

  return (
    <div ref={cadre} className={`relative h-full w-full ${className}`} data-testid="atlas-echelle" style={{ backgroundColor: "#071019", backgroundImage: "radial-gradient(rgba(148,163,184,0.13) 1px, transparent 1px)", backgroundSize: "26px 26px" }}>
      <canvas ref={canvas} className="absolute inset-0 h-full w-full cursor-grab touch-none" />
      {stats && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] leading-5 text-[#7C93A8]" data-testid="atlas-echelle-hud">
          {compact(stats.rendus)} / {compact(stats.total)} jumeaux affichés
          <span className="ml-2 text-[#526578]">{stats.serveur} ms serveur · {stats.allerRetour} ms</span>
        </div>
      )}
      {apercu && (
        <div className="glass pointer-events-none absolute z-20 w-[230px] space-y-1 rounded-xl p-3" style={{ left: apercu.left, top: apercu.top }} data-testid="atlas-echelle-apercu">
          <div className="text-xs font-semibold text-[#F2F6F8]">{apercu.id ? `${idNumerique(apercu.id)} · ${apercu.id}` : `Jumeau ${apercu.i}`}</div>
          <div className="font-code text-[10px] text-[#94A3B8]">{rep.current?.domaines?.[apercu.dom]} · {apercu.degre} relation{apercu.degre > 1 ? "s" : ""}</div>
          {apercu.ecart > 0 && <div className="font-code text-[10px]" style={{ color: VIOLET }}>Écart : couplé surtout à un autre domaine</div>}
          {apercu.alerte > 0 && <div className="font-code text-[10px]" style={{ color: ORANGE }}>Situation active</div>}
          {apercu.id && <div className="pt-0.5 font-code text-[9px] text-[#60A5FA]">Clic : ouvrir le jumeau →</div>}
        </div>
      )}
    </div>
  );
}
