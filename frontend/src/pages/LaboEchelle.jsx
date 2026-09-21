import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Flask, MagnifyingGlass, Play } from "@phosphor-icons/react";
import { ETATS_RELATION } from "@/lib/domaines";
import {
  COULEURS_DOMAINES, NOMS_DOMAINES, ZOOM_NOEUDS, construireIndex, genererGrand, grappesVisibles,
  liensGrappes, liensNoeuds, niveauPour, noeudsVisibles, plusProche,
} from "@/lib/laboEchelle";

// ============================================================================================
// LABORATOIRE — « n'importe quel nombre de nœuds ».
// Rendu canvas 2D + index spatial + pyramide de grappes (voir lib/laboEchelle.js). Le coût d'une image
// ne dépend que de ce qui est à l'écran : de 1 000 à 1 000 000 de jumeaux, on dessine ~300 éléments.
// Aucun lien avec l'Atlas ni avec les données : tout est synthétique.
// ============================================================================================

const TAILLES = [[1000, "1 000"], [10000, "10 000"], [100000, "100 000"], [1000000, "1 000 000"]];
const COULEURS_ETAT = ["confirmee", "observee", "supposee", "validation", "contestee", "obsolete"].map((k) => ETATS_RELATION[k].couleur);
const HAUTEUR_ROBOT_UNITE = 65; // hauteur d'un robot (px) à zoom 1
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)} k` : String(n)).replace(".", ",");
const numero = (i) => String(1000 + ((i * 7919) % 9000));

// --- Sprite du robot-jumeau (même dessin que RobotJumeauSvg), un par couleur de domaine ------------
const svgRobot = (c) => `<svg xmlns="http://www.w3.org/2000/svg" width="124" height="190" viewBox="-62 -88 124 190">
<defs><linearGradient id="k" x1="0" y1="0" x2="0.35" y2="1"><stop offset="0" stop-color="#f2f8ff"/><stop offset=".55" stop-color="#cfe3f7"/><stop offset="1" stop-color="#8fb0cf"/></linearGradient>
<linearGradient id="v" x1="0" y1="0" x2="0.2" y2="1"><stop offset="0" stop-color="#123651"/><stop offset="1" stop-color="#05141f"/></linearGradient>
<radialGradient id="o"><stop offset="0" stop-color="#fff"/><stop offset=".45" stop-color="${c}"/><stop offset="1" stop-color="${c}"/></radialGradient></defs>
<ellipse cx="0" cy="8" rx="56" ry="74" fill="${c}" opacity=".3"/><ellipse cx="0" cy="8" rx="56" ry="74" fill="none" stroke="${c}" stroke-width="2.4" opacity=".75"/>
<path d="M -30 34 C -30 18, -16 10, 0 10 C 16 10, 30 18, 30 34 L 30 52 C 30 66, 16 74, 0 74 C -16 74, -30 66, -30 52 Z" fill="url(#k)"/>
<ellipse cx="0" cy="46" rx="13" ry="13" fill="rgba(20,70,110,.5)"/><ellipse cx="0" cy="46" rx="6.5" ry="6.5" fill="url(#o)"/>
<ellipse cx="-38" cy="40" rx="9" ry="14" fill="url(#k)" transform="rotate(-12 -38 40)"/><ellipse cx="38" cy="40" rx="9" ry="14" fill="url(#k)" transform="rotate(12 38 40)"/>
<rect x="-48" y="-52" width="96" height="76" rx="34" fill="url(#k)"/><rect x="-38" y="-42" width="76" height="52" rx="25" fill="url(#v)"/>
<ellipse cx="-15" cy="-16" rx="9.5" ry="9.5" fill="url(#o)"/><ellipse cx="15" cy="-16" rx="9.5" ry="9.5" fill="url(#o)"/>
<ellipse cx="-17.5" cy="-19" rx="3" ry="3" fill="#fff" opacity=".95"/><ellipse cx="12.5" cy="-19" rx="3" ry="3" fill="#fff" opacity=".95"/>
<line x1="0" y1="-52" x2="0" y2="-70" stroke="#cfe3f7" stroke-width="3.5" stroke-linecap="round"/><circle cx="0" cy="-74" r="6" fill="url(#o)"/>
<ellipse cx="-50" cy="-16" rx="8" ry="13" fill="url(#k)"/><ellipse cx="50" cy="-16" rx="8" ry="13" fill="url(#k)"/>
<ellipse cx="0" cy="92" rx="36" ry="6.5" fill="${c}" opacity=".75"/></svg>`;

function chargerSprites() {
  return Promise.all(
    COULEURS_DOMAINES.map(
      (c) =>
        new Promise((resolve) => {
          const img = new Image();
          img.onload = () => {
            const cv = document.createElement("canvas");
            cv.width = 124;
            cv.height = 190;
            cv.getContext("2d").drawImage(img, 0, 0);
            resolve(cv);
          };
          img.onerror = () => resolve(null);
          img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgRobot(c))}`;
        })
    )
  );
}

export default function LaboEchelle() {
  const cadre = useRef(null);
  const canvas = useRef(null);
  const idx = useRef(null); // index courant (tableaux typés : jamais dans l'état React)
  const vue = useRef({ cx: 0, cy: 0, zoom: 1 });
  const taille = useRef({ W: 800, H: 600, dpr: 1 });
  const sprites = useRef([]);
  const sale = useRef(true);
  const dernier = useRef({ niv: 0, grappes: [], vis: [], liens: 0 });
  const chronos = useRef([]);
  const anim = useRef(null);
  const drag = useRef(null);
  const zMin = useRef(0.01);

  const [n, setN] = useState(null);
  const [etat, setEtat] = useState("Choisissez un nombre de jumeaux.");
  const [mesures, setMesures] = useState({});
  const [stats, setStats] = useState({});
  const [survol, setSurvol] = useState(null); // { type, ... , x, y }
  const [selection, setSelection] = useState(null);
  const [recherche, setRecherche] = useState("");
  const [test, setTest] = useState(null);

  const marquer = () => { sale.current = true; };

  // ---- Dessin -----------------------------------------------------------------------------------
  const dessiner = useCallback(() => {
    const cv = canvas.current;
    const index = idx.current;
    if (!cv) return;
    const t0 = performance.now();
    const { W, H, dpr } = taille.current;
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#071019";
    ctx.fillRect(0, 0, W, H);
    if (!index) return;
    const v = vue.current;
    const z = v.zoom;
    const sx = (wx) => (wx - v.cx) * z + W / 2;
    const sy = (wy) => (wy - v.cy) * z + H / 2;
    const m = 120 / z;
    const w0 = v.cx - W / 2 / z - m, w1 = v.cx + W / 2 / z + m, h0 = v.cy - H / 2 / z - m, h1 = v.cy + H / 2 / z + m;
    const niv = niveauPour(index, z);
    const g = index.g;

    if (niv > 0) {
      const gr = grappesVisibles(index, niv, w0, h0, w1, h1);
      const liens = liensGrappes(index, niv, gr, w0, h0, w1, h1);
      ctx.lineCap = "round";
      liens.forEach(({ a, b, poids }) => {
        const A = gr[a], B = gr[b];
        ctx.strokeStyle = `rgba(148,163,184,${Math.min(0.55, 0.14 + Math.log10(poids + 1) * 0.16)})`;
        ctx.lineWidth = 0.6 + Math.log10(poids + 1) * 1.1;
        ctx.beginPath();
        ctx.moveTo(sx(A.x), sy(A.y));
        ctx.lineTo(sx(B.x), sy(B.y));
        ctx.stroke();
      });
      const cellPx = index.niveaux[niv - 1].s * z;
      const dessines = gr.map((c) => {
        const r = Math.min(cellPx * 0.46, 5 + 3.4 * Math.log2(c.n + 1));
        return { ...c, px: sx(c.x), py: sy(c.y), r };
      });
      dessines.forEach((c) => {
        ctx.beginPath();
        ctx.arc(c.px, c.py, c.r, 0, 6.2832);
        ctx.fillStyle = `${COULEURS_DOMAINES[c.dom]}cc`;
        ctx.fill();
        ctx.lineWidth = 1.4;
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.stroke();
        if (c.r >= 12) {
          ctx.fillStyle = "#071019";
          ctx.font = `600 ${Math.min(13, c.r * 0.7)}px ui-monospace, monospace`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(compact(c.n), c.px, c.py);
        }
      });
      dernier.current = { niv, grappes: dessines, vis: [], liens: liens.length };
    } else {
      const vis = noeudsVisibles(index, w0, h0, w1, h1);
      const liens = liensNoeuds(index, vis);
      ctx.lineWidth = Math.max(0.8, Math.min(2.2, z * 1.4));
      ctx.globalAlpha = 0.6;
      liens.forEach(([i, j]) => {
        ctx.strokeStyle = "rgba(148,163,184,0.75)";
        ctx.beginPath();
        ctx.moveTo(sx(g.x[i]), sy(g.y[i]));
        ctx.lineTo(sx(g.x[j]), sy(g.y[j]));
        ctx.stroke();
      });
      ctx.globalAlpha = 1;
      const h = Math.max(16, Math.min(200, HAUTEUR_ROBOT_UNITE * z));
      const w = h * (124 / 190);
      const surv = survolRef.current;
      vis.forEach((i) => {
        const px = sx(g.x[i]), py = sy(g.y[i]);
        const sp = sprites.current[g.dom[i]];
        if (sp) ctx.drawImage(sp, px - w / 2, py - h / 2, w, h);
        else { ctx.beginPath(); ctx.arc(px, py, h * 0.25, 0, 6.2832); ctx.fillStyle = COULEURS_DOMAINES[g.dom[i]]; ctx.fill(); }
        if (i === surv || i === selRef.current) {
          ctx.beginPath();
          ctx.arc(px, py, h * 0.5, 0, 6.2832);
          ctx.strokeStyle = i === selRef.current ? "#C4B5FD" : "rgba(255,255,255,0.7)";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });
      if (z >= 0.9) {
        ctx.font = "10px ui-monospace, monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        vis.forEach((i) => {
          const nom = z >= 0.7 && g.deg[i] >= 8 ? `${NOMS_DOMAINES[g.dom[i]]} ${i - g.debutDom[g.dom[i]] + 1}` : numero(i);
          ctx.fillStyle = "rgba(220,230,238,0.9)";
          ctx.fillText(nom, sx(g.x[i]), sy(g.y[i]) + h / 2 - 2);
        });
      }
      dernier.current = { niv: 0, grappes: [], vis, liens: liens.length };
    }
    const ms = performance.now() - t0;
    chronos.current.push(ms);
    if (chronos.current.length > 40) chronos.current.shift();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const survolRef = useRef(-1);
  const selRef = useRef(-1);
  selRef.current = selection ?? -1;

  // boucle de rendu : on ne redessine que si la vue a changé
  useEffect(() => {
    let raf;
    const boucle = () => {
      if (sale.current) { sale.current = false; dessiner(); }
      raf = requestAnimationFrame(boucle);
    };
    raf = requestAnimationFrame(boucle);
    return () => cancelAnimationFrame(raf);
  }, [dessiner]);

  // statistiques affichées (4 fois par seconde)
  useEffect(() => {
    const t = setInterval(() => {
      const c = chronos.current;
      const d = dernier.current;
      setStats({ niv: d.niv, grappes: d.grappes.length, noeuds: d.vis.length, liens: d.liens, ms: c.length ? c.reduce((a, b) => a + b, 0) / c.length : 0, zoom: vue.current.zoom });
    }, 250);
    return () => clearInterval(t);
  }, []);

  // taille du canvas (haute densité)
  useEffect(() => {
    const el = cadre.current;
    const ajuster = () => {
      const r = el.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      taille.current = { W: r.width, H: r.height, dpr };
      canvas.current.width = Math.round(r.width * dpr);
      canvas.current.height = Math.round(r.height * dpr);
      marquer();
    };
    ajuster();
    const ro = new ResizeObserver(ajuster);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { chargerSprites().then((s) => { sprites.current = s; marquer(); }); }, []);

  // ---- Caméra -----------------------------------------------------------------------------------
  const toutVoir = useCallback((instant = false) => {
    const index = idx.current;
    if (!index) return;
    const { x0, y0, x1, y1 } = index.g.bornes;
    const { W, H } = taille.current;
    const z = Math.min(W / (x1 - x0), H / (y1 - y0)) * 0.9;
    zMin.current = z * 0.8;
    voler({ cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, zoom: z }, instant ? 0 : 500);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function effacerSurvol() {
    if (survolCle.current === null) return;
    survolCle.current = null;
    survolRef.current = -1;
    setSurvol(null);
  }

  function voler(cible, ms = 550) {
    cancelAnimationFrame(anim.current);
    effacerSurvol();
    const de = { ...vue.current };
    if (!ms) { vue.current = { ...cible }; marquer(); return Promise.resolve(); }
    const t0 = performance.now();
    return new Promise((resolve) => {
      const pas = (t) => {
        const k = Math.min(1, (t - t0) / ms);
        const e = 1 - (1 - k) ** 3;
        // zoom interpolé en échelle logarithmique : la vitesse perçue reste constante
        const z = de.zoom * (cible.zoom / de.zoom) ** e;
        vue.current = { cx: de.cx + (cible.cx - de.cx) * e, cy: de.cy + (cible.cy - de.cy) * e, zoom: z };
        marquer();
        if (k < 1) anim.current = requestAnimationFrame(pas);
        else resolve();
      };
      anim.current = requestAnimationFrame(pas);
    });
  }

  // ---- Chargement d'un jeu de données ----------------------------------------------------------------
  const charger = useCallback(async (nombre) => {
    setN(nombre);
    setSelection(null);
    setSurvol(null);
    setTest(null);
    idx.current = null;
    marquer();
    setEtat(`Génération de ${nombre.toLocaleString("fr")} jumeaux…`);
    await new Promise((r) => setTimeout(r, 30));
    const g = genererGrand(nombre);
    setEtat("Construction de l'index et des niveaux de regroupement…");
    await new Promise((r) => setTimeout(r, 30));
    const index = construireIndex(g);
    idx.current = index;
    setMesures({ gen: Math.round(g.tGen), index: Math.round(index.tIndex), mo: Math.round(index.octets / 1048576), liens: g.m, niveaux: index.niveaux.length });
    setEtat("");
    toutVoir(true);
    return { gen: g.tGen, index: index.tIndex };
  }, [toutVoir]);

  // ---- Interactions -------------------------------------------------------------------------------------
  const versMonde = (ex, ey) => {
    const { W, H } = taille.current;
    const v = vue.current;
    return [(ex - W / 2) / v.zoom + v.cx, (ey - H / 2) / v.zoom + v.cy];
  };
  const surRoulette = (e) => {
    if (!idx.current) return;
    e.preventDefault();
    cancelAnimationFrame(anim.current);
    effacerSurvol();
    const r = cadre.current.getBoundingClientRect();
    const ex = e.clientX - r.left, ey = e.clientY - r.top;
    const [wx, wy] = versMonde(ex, ey);
    const v = vue.current;
    const z = Math.max(zMin.current, Math.min(6, v.zoom * Math.exp(-e.deltaY * 0.0016)));
    const { W, H } = taille.current;
    vue.current = { zoom: z, cx: wx - (ex - W / 2) / z, cy: wy - (ey - H / 2) / z };
    marquer();
  };
  const surPointeurBas = (e) => {
    if (!idx.current) return;
    drag.current = { x: e.clientX, y: e.clientY, cx: vue.current.cx, cy: vue.current.cy, bouge: false };
    e.currentTarget.setPointerCapture(e.pointerId);
    cancelAnimationFrame(anim.current);
  };
  const trouver = (ex, ey) => {
    const d = dernier.current;
    const [wx, wy] = versMonde(ex, ey);
    if (d.niv > 0) {
      let meilleur = null, dmin = 1e9;
      d.grappes.forEach((c) => {
        const dd = Math.hypot(c.px - ex, c.py - ey);
        if (dd <= c.r + 3 && dd < dmin) { dmin = dd; meilleur = c; }
      });
      return meilleur ? { type: "grappe", c: meilleur } : null;
    }
    const i = plusProche(idx.current.g, d.vis, wx, wy, 28 / vue.current.zoom);
    return i >= 0 ? { type: "noeud", i } : null;
  };
  const surPointeurBouge = (e) => {
    const r = cadre.current.getBoundingClientRect();
    const ex = e.clientX - r.left, ey = e.clientY - r.top;
    if (drag.current) {
      const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) { drag.current.bouge = true; effacerSurvol(); }
      vue.current = { ...vue.current, cx: drag.current.cx - dx / vue.current.zoom, cy: drag.current.cy - dy / vue.current.zoom };
      marquer();
      return;
    }
    if (!idx.current) return;
    const h = trouver(ex, ey);
    const cle = h ? (h.type === "noeud" ? h.i : `g${h.c.c}`) : null;
    if (cle !== survolCle.current) {
      survolCle.current = cle;
      survolRef.current = h?.type === "noeud" ? h.i : -1;
      marquer();
      setSurvol(h ? { ...h, x: ex, y: ey } : null);
    }
  };
  const survolCle = useRef(null);
  const surPointeurHaut = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.bouge) return;
    const r = cadre.current.getBoundingClientRect();
    const h = trouver(e.clientX - r.left, e.clientY - r.top);
    if (!h) return;
    if (h.type === "grappe") voler({ cx: h.c.x, cy: h.c.y, zoom: Math.min(6, vue.current.zoom * 3.2) }, 600);
    else setSelection(h.i);
  };
  const surDoubleClic = (e) => {
    const r = cadre.current.getBoundingClientRect();
    const [wx, wy] = versMonde(e.clientX - r.left, e.clientY - r.top);
    voler({ cx: wx, cy: wy, zoom: Math.min(6, vue.current.zoom * 2) }, 400);
  };

  // ---- Recherche et fiche -----------------------------------------------------------------------------------
  const allerA = (i) => {
    const g = idx.current.g;
    setSelection(i);
    voler({ cx: g.x[i], cy: g.y[i], zoom: 1.4 }, 900);
  };
  const chercher = (e) => {
    e.preventDefault();
    const index = idx.current;
    if (!index) return;
    const m = recherche.trim().match(/^(.+?)\s+(\d+)$/);
    if (!m) return;
    const d = NOMS_DOMAINES.findIndex((nom) => nom.toLowerCase() === m[1].toLowerCase());
    const k = Number(m[2]) - 1;
    if (d < 0 || k < 0 || k >= index.g.tailles[d]) { setEtat(`Introuvable : ${recherche}`); return; }
    setEtat("");
    allerA(index.g.debutDom[d] + k);
  };
  const fiche = useMemo(() => {
    const index = idx.current;
    if (selection == null || !index) return null;
    const g = index.g;
    const voisins = [];
    for (let k = index.adjDebut[selection]; k < index.adjDebut[selection + 1] && voisins.length < 8; k += 1) voisins.push(index.adjA[k]);
    return { i: selection, nom: `${NOMS_DOMAINES[g.dom[selection]]} ${selection - g.debutDom[g.dom[selection]] + 1}`, dom: g.dom[selection], deg: g.deg[selection], cov: g.cov[selection], voisins };
  }, [selection]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Parcours de test (caméra automatique : monde entier → plongée → balayage → retour) -----------------
  const parcours = useCallback(async () => {
    const index = idx.current;
    if (!index) return null;
    const g = index.g;
    const pivot = Math.floor(g.n / 3);
    const dt = [];
    const ms = [];
    let dernierT = performance.now();
    let actif = true;
    const suivre = (t) => { dt.push(t - dernierT); dernierT = t; if (actif) requestAnimationFrame(suivre); };
    requestAnimationFrame(suivre);
    chronos.current.length = 0;
    toutVoir(true);
    await new Promise((r) => setTimeout(r, 200));
    await voler({ cx: g.x[pivot], cy: g.y[pivot], zoom: 1.2 }, 2200); // plongée jusqu'aux robots
    await voler({ cx: g.x[pivot] + 2500, cy: g.y[pivot] + 1500, zoom: 1.2 }, 1200); // balayage
    await voler({ cx: g.x[pivot], cy: g.y[pivot], zoom: 0.1 }, 1600); // remontée
    toutVoir();
    await new Promise((r) => setTimeout(r, 700));
    actif = false;
    ms.push(...chronos.current);
    const tri = [...dt].sort((a, b) => a - b);
    const moyenne = dt.reduce((a, b) => a + b, 0) / dt.length;
    const tD = [...ms].sort((a, b) => a - b);
    const res = { ips: Math.round(1000 / moyenne), pireImage: Math.round(tri[tri.length - 1]), p95Image: Math.round(tri[Math.floor(tri.length * 0.95)]), dessinMoy: +(ms.reduce((a, b) => a + b, 0) / Math.max(1, ms.length)).toFixed(2), dessinPire: +(tD[tD.length - 1] || 0).toFixed(1), images: dt.length };
    setTest(res);
    return res;
  }, [toutVoir]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.__echelle = { charger, parcours, stats: () => ({ ...dernier.current, grappes: dernier.current.grappes.length, vis: dernier.current.vis.length, zoom: vue.current.zoom, ms: chronos.current.length ? chronos.current.reduce((a, b) => a + b, 0) / chronos.current.length : 0 }), voler, vue: () => vue.current, monde: () => idx.current?.g.bornes, memoire: () => Math.round((performance.memory?.usedJSHeapSize || 0) / 1048576) };
    return () => { delete window.__echelle; };
  }, [charger, parcours]); // eslint-disable-line react-hooks/exhaustive-deps

  const niveauTexte = stats.niv > 0 ? `niveau ${stats.niv} — grappes` : "jumeaux individuels";
  const hist = idx.current && survol?.type === "grappe" && dernier.current.niv > 0 ? idx.current.niveaux[dernier.current.niv - 1]?.hist ?? null : null;

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#071019]" data-testid="labo-echelle">
      <div ref={cadre} className="absolute inset-0 touch-none select-none" onWheel={surRoulette} onPointerDown={surPointeurBas} onPointerMove={surPointeurBouge} onPointerUp={surPointeurHaut} onPointerLeave={() => { if (!drag.current) { survolCle.current = null; survolRef.current = -1; setSurvol(null); marquer(); } }} onDoubleClick={surDoubleClic} style={{ cursor: survol ? "pointer" : drag.current ? "grabbing" : "grab" }}>
        <canvas ref={canvas} className="h-full w-full" data-testid="echelle-canvas" />
      </div>

      {/* Panneau de contrôle */}
      <div className="absolute left-4 top-4 z-10 w-[330px] space-y-2.5 rounded-xl border border-white/10 bg-[#0C1724] p-3.5 shadow-2xl" data-testid="echelle-hud">
        <div className="flex items-center gap-2">
          <Flask size={16} className="text-[#9B87F5]" />
          <div className="leading-tight">
            <div className="text-xs font-bold text-white">Laboratoire — passage à l'échelle</div>
            <div className="text-[10px] text-[#7C93A8]">Canvas + index spatial + grappes par niveau de zoom</div>
          </div>
        </div>
        <div className="inline-flex flex-wrap rounded-lg border border-white/10 bg-white/[0.03] p-0.5" role="group">
          {TAILLES.map(([v, l]) => (
            <button key={v} type="button" onClick={() => charger(v)} aria-pressed={n === v} data-testid={`echelle-n-${v}`} className={`min-h-[30px] rounded-md px-2.5 text-[11px] font-medium transition-colors ${n === v ? "bg-[#9B87F5]/25 text-white" : "text-[#7C93A8] hover:text-white"}`}>{l}</button>
          ))}
        </div>
        {etat && <p className="text-[11px] text-[#F2B84B]" data-testid="echelle-etat">{etat}</p>}
        {n && !etat && (
          <div className="space-y-0.5 rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="echelle-mesures">
            <div>{n.toLocaleString("fr")} jumeaux · {mesures.liens?.toLocaleString("fr")} liens · {mesures.niveaux} niveaux</div>
            <div>Génération {mesures.gen} ms · index {mesures.index} ms · ≈ {mesures.mo} Mo</div>
            <div className="text-[#DCE6EE]">À l'écran : {stats.niv > 0 ? `${stats.grappes} grappes` : `${stats.noeuds} jumeaux`} · {stats.liens} liens</div>
            <div>Vue : {niveauTexte} · zoom {stats.zoom ? stats.zoom.toFixed(3) : "—"}</div>
            <div className="text-[#25D0C8]">Dessin d'une image : {stats.ms ? stats.ms.toFixed(2) : "—"} ms</div>
          </div>
        )}
        <form onSubmit={chercher} className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#071019] px-2.5">
          <MagnifyingGlass size={13} className="text-[#7C93A8]" />
          <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Ex. : Support 120" data-testid="echelle-recherche" className="min-h-[32px] flex-1 bg-transparent text-xs text-white outline-none placeholder:text-[#526578]" />
        </form>
        <div className="flex gap-1.5">
          <button type="button" onClick={() => toutVoir()} data-testid="echelle-tout-voir" className="min-h-[30px] flex-1 rounded-lg border border-white/10 text-[11px] text-[#CBD5E1] hover:text-white">Tout voir</button>
          <button type="button" onClick={parcours} data-testid="echelle-parcours" className="flex min-h-[30px] flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#9B87F5]/40 bg-[#9B87F5]/15 text-[11px] font-semibold text-[#C4B5FD] hover:text-white"><Play size={11} weight="fill" /> Parcours de test</button>
        </div>
        {test && (
          <div className="rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="echelle-test">
            <div className="text-[#DCE6EE]">{test.ips} images/s · pire image {test.pireImage} ms · p95 {test.p95Image} ms</div>
            <div>Dessin : {test.dessinMoy} ms en moyenne · {test.dessinPire} ms au pire ({test.images} images)</div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-white/[0.07] pt-2" data-testid="echelle-legende">
          {NOMS_DOMAINES.map((d, i) => (
            <div key={d} className="flex items-center gap-1.5 text-[10px] text-[#94A3B8]">
              <span className="h-2 w-2 rounded-full" style={{ background: COULEURS_DOMAINES[i] }} /> {d}
              {idx.current && <span className="ml-auto font-code text-[9px] text-[#64748B]">{compact(idx.current.g.tailles[i])}</span>}
            </div>
          ))}
        </div>
        <Link to="/labo/atlas" className="block text-center font-code text-[10px] text-[#7C93A8] hover:text-white">← Laboratoire du graphe</Link>
      </div>

      {/* Aperçu au survol */}
      {survol && idx.current && (survol.type === "noeud" ? survol.i < idx.current.g.n : dernier.current.niv > 0) && (
        <div className="pointer-events-none absolute z-20 w-[230px] space-y-1 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3 shadow-2xl" style={{ left: Math.min(survol.x + 18, taille.current.W - 240), top: Math.max(8, Math.min(survol.y - 30, taille.current.H - 150)) }} data-testid="echelle-apercu">
          {survol.type === "noeud" ? (
            <>
              <div className="text-sm font-semibold text-white">{NOMS_DOMAINES[idx.current.g.dom[survol.i]]} {survol.i - idx.current.g.debutDom[idx.current.g.dom[survol.i]] + 1}</div>
              <div className="font-code text-[10px] text-[#7C93A8]">Degré {idx.current.g.deg[survol.i]} · couverture {idx.current.g.cov[survol.i]} %</div>
              <div className="font-code text-[9px] text-[#526578]">Cliquer pour épingler</div>
            </>
          ) : (
            <>
              <div className="text-sm font-semibold text-white">{survol.c.n.toLocaleString("fr")} jumeaux</div>
              <div className="font-code text-[10px] text-[#7C93A8]">{NOMS_DOMAINES[survol.c.dom]} à {Math.round(survol.c.part * 100)} %</div>
              {hist && <div className="flex h-1.5 overflow-hidden rounded-full">{NOMS_DOMAINES.map((d, i) => { const h = hist[survol.c.c * NOMS_DOMAINES.length + i]; return h ? <span key={d} style={{ width: `${(h / survol.c.n) * 100}%`, background: COULEURS_DOMAINES[i] }} /> : null; })}</div>}
              <div className="font-code text-[9px] text-[#526578]">Cliquer pour zoomer dans cette grappe</div>
            </>
          )}
        </div>
      )}

      {/* Fiche du jumeau épinglé */}
      {fiche && (
        <div className="absolute right-4 top-4 z-10 w-[260px] space-y-1.5 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3.5 shadow-2xl" data-testid="echelle-fiche">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: COULEURS_DOMAINES[fiche.dom] }} />
            <span className="flex-1 text-sm font-semibold text-white">{fiche.nom}</span>
            <button type="button" onClick={() => setSelection(null)} aria-label="Fermer" className="text-[#7C93A8] hover:text-white">✕</button>
          </div>
          <div className="font-code text-[10px] text-[#94A3B8]">Domaine {NOMS_DOMAINES[fiche.dom]} · degré {fiche.deg} · couverture {fiche.cov} %</div>
          <div className="pt-1 text-[10px] text-[#64748B]">Voisins</div>
          <div className="space-y-0.5">
            {fiche.voisins.map((j) => (
              <button key={j} type="button" onClick={() => allerA(j)} className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[11px] text-[#CBD5E1] hover:bg-white/[0.06]">
                <span className="h-2 w-2 rounded-full" style={{ background: COULEURS_DOMAINES[idx.current.g.dom[j]] }} />
                {NOMS_DOMAINES[idx.current.g.dom[j]]} {j - idx.current.g.debutDom[idx.current.g.dom[j]] + 1}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Aide de navigation */}
      <div className="pointer-events-none absolute bottom-3 right-4 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] text-[#7C93A8]">
        Molette : zoom · glisser : déplacer · clic sur une grappe : zoomer · double-clic : zoom ×2 · zoom ≥ {ZOOM_NOEUDS} : jumeaux individuels
      </div>
    </div>
  );
}
