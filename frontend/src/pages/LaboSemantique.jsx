import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Flask, MagnifyingGlass, Play } from "@phosphor-icons/react";
import { ecouterSprites, spriteRobot } from "@/lib/spritesRobot";
import { COULEURS_DOMAINES, NOMS_DOMAINES, liensNoeuds, noeudsVisibles, plusProche } from "@/lib/laboEchelle";
import {
  bullesVisibles, construireIndexHier, genererHierarchie, liensBulles, niveauSemantique, nomBulle, rangDansDomaine,
} from "@/lib/laboHierarchie";

// ============================================================================================
// LABORATOIRE — agrégation SÉMANTIQUE : domaine → groupe → communauté → jumeau.
// Même moteur canvas que /labo/echelle, mais les grappes sont les vraies unités métier : nommées,
// stables, sans chevauchement, et elles PORTENT LEURS SIGNAUX (écarts, situations). Une grappe
// s'ouvre en fondu sur ses enfants au lieu de « sauter ».
// ============================================================================================

const TAILLES = [[1000, "1 000"], [10000, "10 000"], [100000, "100 000"], [1000000, "1 000 000"]];
const ZOOM_ROBOTS = 0.45;
const ZOOM_POINTS = 0.1;
const HAUTEUR_ROBOT_UNITE = 65;
const ORANGE = "#F59E0B";
const VIOLET = "#60A5FA";
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} M` : n >= 1e3 ? `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)} k` : String(n)).replace(".", ",");
const numero = (i) => String(1000 + ((i * 7919) % 9000));

export default function LaboSemantique() {
  const cadre = useRef(null);
  const canvas = useRef(null);
  const idx = useRef(null);
  const vue = useRef({ cx: 0, cy: 0, zoom: 1 });
  const taille = useRef({ W: 800, H: 600, dpr: 1 });
  const sale = useRef(true);
  const dernier = useRef({ mode: "bulles", niv: 3, bulles: [], vis: [], liens: 0, points: 0, fondu: 0 });
  const chronos = useRef([]);
  const anim = useRef(null);
  const drag = useRef(null);
  const zMin = useRef(0.001);
  const survolCle = useRef(null);
  const survolRef = useRef(-1);
  const selRef = useRef(-1);
  const opts = useRef({ signaux: true, fondu: true });

  const [n, setN] = useState(null);
  const [etat, setEtat] = useState("Choisissez un nombre de jumeaux.");
  const [mesures, setMesures] = useState({});
  const [stats, setStats] = useState({});
  const [survol, setSurvol] = useState(null);
  const [selection, setSelection] = useState(null);
  const [recherche, setRecherche] = useState("");
  const [test, setTest] = useState(null);
  const [signaux, setSignaux] = useState(true);
  const [fondu, setFondu] = useState(true);
  const [chemin, setChemin] = useState([]);
  selRef.current = selection ?? -1;
  opts.current = { signaux, fondu };

  const marquer = () => { sale.current = true; };

  // ---- Anneaux de signaux : orange = excès d'écarts, violet = situations actives ------------------------------
  const anneaux = (ctx, px, py, rr, v, id, alpha) => {
    const g = idx.current.g;
    const nn = v.taille[id];
    const excesEcarts = Math.max(0, v.ecarts[id] / nn - g.moyEcarts);
    const fa = v.alertes[id] / nn;
    if (excesEcarts <= 0.005 && v.alertes[id] === 0) return;
    ctx.lineCap = "round";
    ctx.lineWidth = Math.max(2, Math.min(4.5, rr * 0.13));
    ctx.globalAlpha = alpha;
    if (excesEcarts > 0.005) {
      ctx.strokeStyle = ORANGE;
      ctx.beginPath();
      ctx.arc(px, py, rr + 3.5, -Math.PI / 2, -Math.PI / 2 + Math.min(1, excesEcarts / 0.08) * 6.2832 * 0.98);
      ctx.stroke();
    }
    if (v.alertes[id] > 0) {
      ctx.strokeStyle = VIOLET;
      ctx.beginPath();
      ctx.arc(px, py, rr + 3.5, Math.PI / 2, Math.PI / 2 + Math.max(0.09, Math.min(1, fa / 0.15)) * 6.2832 * 0.98);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  };

  // ---- Dessin -----------------------------------------------------------------------------------------------------
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
    const g = index.g;
    const sx = (wx) => (wx - v.cx) * z + W / 2;
    const sy = (wy) => (wy - v.cy) * z + H / 2;
    const m = 120 / z;
    const w0 = v.cx - W / 2 / z - m, w1 = v.cx + W / 2 / z + m, h0 = v.cy - H / 2 / z - m, h1 = v.cy + H / 2 / z + m;
    const { signaux: avecSignaux, fondu: avecFondu } = opts.current;

    const dessinerBulles = (niv, ids, alpha, etiquettes, avecAnneaux) => {
      const B = g.niveaux[niv];
      const sorties = [];
      ids.forEach((id) => {
        const px = sx(B.x[id]), py = sy(B.y[id]), rr = B.r[id] * z;
        if (rr < 1.2) return;
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(px, py, rr, 0, 6.2832);
        ctx.fillStyle = `${COULEURS_DOMAINES[B.dom[id]]}${niv === 1 ? "38" : niv === 2 ? "2e" : "26"}`;
        ctx.fill();
        ctx.lineWidth = niv === 3 ? 2 : 1.4;
        ctx.strokeStyle = `${COULEURS_DOMAINES[B.dom[id]]}${niv === 3 ? "cc" : "99"}`;
        ctx.stroke();
        ctx.globalAlpha = 1;
        if (avecAnneaux && avecSignaux && rr >= 5) anneaux(ctx, px, py, rr, B, id, alpha);
        if (etiquettes && rr >= 14) {
          ctx.globalAlpha = etiquettes;
          ctx.fillStyle = "#E8F0F6";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          if (niv === 3 || rr >= 60) {
            ctx.font = `600 ${Math.min(22, Math.max(11, rr * 0.16))}px ui-sans-serif, system-ui`;
            ctx.fillText(niv === 3 ? NOMS_DOMAINES[id] : nomBulle(g, niv, id).split(" · ").slice(1).join(" · "), px, py - Math.min(14, rr * 0.1));
          }
          ctx.font = `600 ${Math.min(15, Math.max(10, rr * 0.5))}px ui-monospace, monospace`;
          ctx.fillText(compact(B.taille[id]), px, py + (niv === 3 || rr >= 60 ? Math.min(14, rr * 0.1) + 6 : 0));
          if (avecSignaux && rr >= 22 && B.alertes[id] > 0) {
            ctx.fillStyle = VIOLET;
            ctx.font = "600 10px ui-monospace, monospace";
            ctx.fillText(`⚠ ${compact(B.alertes[id])}`, px, py + rr * 0.55);
          }
          ctx.globalAlpha = 1;
        }
        sorties.push({ id, niv, px, py, r: rr });
      });
      return sorties;
    };

    if (z >= ZOOM_ROBOTS) {
      const vis = noeudsVisibles(index, w0, h0, w1, h1);
      const liens = liensNoeuds(index, vis);
      ctx.lineWidth = Math.max(0.8, Math.min(2.2, z * 1.4));
      ctx.globalAlpha = 0.55;
      ctx.strokeStyle = "rgba(148,163,184,0.75)";
      liens.forEach(([i, j]) => { ctx.beginPath(); ctx.moveTo(sx(g.x[i]), sy(g.y[i])); ctx.lineTo(sx(g.x[j]), sy(g.y[j])); ctx.stroke(); });
      ctx.globalAlpha = 1;
      const h = Math.max(16, Math.min(200, HAUTEUR_ROBOT_UNITE * z));
      const w = h * (124 / 190);
      vis.forEach((i) => {
        const px = sx(g.x[i]), py = sy(g.y[i]);
        const sp = spriteRobot(COULEURS_DOMAINES[g.dom[i]]);
        if (sp) ctx.drawImage(sp, px - w / 2, py - h / 2, w, h);
        else { ctx.beginPath(); ctx.arc(px, py, h * 0.25, 0, 6.2832); ctx.fillStyle = COULEURS_DOMAINES[g.dom[i]]; ctx.fill(); }
        if (avecSignaux && g.ecartN[i]) { ctx.beginPath(); ctx.ellipse(px, py + h * 0.02, w * 0.52, h * 0.5, 0, 0, 6.2832); ctx.setLineDash([5, 4]); ctx.strokeStyle = ORANGE; ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]); }
        if (avecSignaux && g.alerteN[i]) { ctx.beginPath(); ctx.arc(px + w * 0.36, py - h * 0.4, Math.max(3, h * 0.07), 0, 6.2832); ctx.fillStyle = VIOLET; ctx.fill(); }
        if (i === survolRef.current || i === selRef.current) { ctx.beginPath(); ctx.arc(px, py, h * 0.52, 0, 6.2832); ctx.strokeStyle = i === selRef.current ? "#BFDBFE" : "rgba(255,255,255,0.7)"; ctx.lineWidth = 2; ctx.stroke(); }
      });
      if (z >= 0.9) {
        ctx.font = "10px ui-monospace, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = "rgba(220,230,238,0.9)";
        vis.forEach((i) => ctx.fillText(z >= 0.7 && g.deg[i] >= 8 ? `${NOMS_DOMAINES[g.dom[i]]} ${rangDansDomaine(g, i)}` : numero(i), sx(g.x[i]), sy(g.y[i]) + h / 2 - 2));
      }
      dernier.current = { mode: "robots", niv: 0, bulles: [], vis, liens: liens.length, points: 0, fondu: 0 };
    } else {
      let vis = null;
      if (z >= ZOOM_POINTS) { vis = noeudsVisibles(index, w0, h0, w1, h1, 9001); if (vis.length > 9000) vis = null; }
      if (vis) {
        // communautés (membranes) + jumeaux en points
        const ids = bullesVisibles(index, 1, w0, h0, w1, h1);
        const b = dessinerBulles(1, ids, 1, 0, true);
        const seaux = Array.from({ length: NOMS_DOMAINES.length }, () => []);
        vis.forEach((i) => seaux[g.dom[i]].push(i));
        seaux.forEach((liste, d) => {
          ctx.fillStyle = COULEURS_DOMAINES[d];
          liste.forEach((i) => ctx.fillRect(sx(g.x[i]) - 1.4, sy(g.y[i]) - 1.4, 2.8, 2.8));
        });
        if (avecSignaux) vis.forEach((i) => {
          if (g.ecartN[i]) { ctx.fillStyle = ORANGE; ctx.fillRect(sx(g.x[i]) - 2.4, sy(g.y[i]) - 2.4, 4.8, 4.8); }
          if (g.alerteN[i]) { ctx.beginPath(); ctx.arc(sx(g.x[i]), sy(g.y[i]), 5, 0, 6.2832); ctx.strokeStyle = VIOLET; ctx.lineWidth = 1.6; ctx.stroke(); }
        });
        dernier.current = { mode: "points", niv: 1, bulles: b, vis, liens: 0, points: vis.length, fondu: 0 };
      } else {
        const { niv, fondu: t } = niveauSemantique(g, z);
        const ids = bullesVisibles(index, niv, w0, h0, w1, h1);
        const liens = liensBulles(index, niv, ids, w0, h0, w1, h1);
        const B = g.niveaux[niv];
        ctx.lineCap = "round";
        liens.forEach(({ a, b, poids }) => {
          const A = ids[a], Bb = ids[b];
          ctx.strokeStyle = `rgba(148,163,184,${Math.min(0.5, 0.12 + Math.log10(poids + 1) * 0.15)})`;
          ctx.lineWidth = 0.6 + Math.log10(poids + 1) * 1.0;
          ctx.beginPath(); ctx.moveTo(sx(B.x[A]), sy(B.y[A])); ctx.lineTo(sx(B.x[Bb]), sy(B.y[Bb])); ctx.stroke();
        });
        const tFondu = avecFondu ? t : 0;
        // ouverture en fondu : les enfants apparaissent tandis que le libellé du parent s'efface
        if (tFondu > 0.02 && niv > 1) {
          const enfants = bullesVisibles(index, niv - 1, w0, h0, w1, h1);
          if (enfants.length <= 900) dessinerBulles(niv - 1, enfants, tFondu, 0, true);
        }
        // le libellé du parent reste plein tant que l'ouverture n'est pas bien engagée, puis s'efface
        const sorties = dessinerBulles(niv, ids, 1, 1 - Math.max(0, (tFondu - 0.35) / 0.65), true);
        dernier.current = { mode: "bulles", niv, bulles: sorties, vis: [], liens: liens.length, points: 0, fondu: tFondu };
      }
    }
    const ms = performance.now() - t0;
    chronos.current.push(ms);
    if (chronos.current.length > 40) chronos.current.shift();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let raf;
    const boucle = () => { if (sale.current) { sale.current = false; dessiner(); } raf = requestAnimationFrame(boucle); };
    raf = requestAnimationFrame(boucle);
    return () => cancelAnimationFrame(raf);
  }, [dessiner]);
  useEffect(() => { marquer(); }, [signaux, fondu]);

  // fil d'Ariane passif : domaine › groupe › communauté qui contiennent le centre de la vue
  const cheminCentre = () => {
    const index = idx.current;
    if (!index) return [];
    const { cx, cy } = vue.current;
    const g = index.g;
    const out = [];
    [3, 2, 1].forEach((niv) => {
      const ids = bullesVisibles(index, niv, cx, cy, cx, cy);
      let meilleur = -1, rmin = 1e12;
      ids.forEach((id) => { const B = g.niveaux[niv]; if (Math.hypot(B.x[id] - cx, B.y[id] - cy) <= B.r[id] && B.r[id] < rmin) { rmin = B.r[id]; meilleur = id; } });
      if (meilleur >= 0) out.push({ niv, id: meilleur, nom: niv === 3 ? NOMS_DOMAINES[meilleur] : niv === 2 ? `Groupe ${meilleur - g.domG0[g.niveaux[2].dom[meilleur]] + 1}` : `Communauté ${meilleur - g.grpC0[g.comGrp[meilleur]] + 1}` });
    });
    return out;
  };
  useEffect(() => {
    const t = setInterval(() => {
      const c = chronos.current, d = dernier.current;
      setStats({ mode: d.mode, niv: d.niv, bulles: d.bulles.length, points: d.points, noeuds: d.mode === "robots" ? d.vis.length : 0, liens: d.liens, fondu: d.fondu, ms: c.length ? c.reduce((a, b) => a + b, 0) / c.length : 0, zoom: vue.current.zoom });
      const ch = cheminCentre();
      setChemin((p) => (JSON.stringify(p.map((e) => `${e.niv}:${e.id}`)) === JSON.stringify(ch.map((e) => `${e.niv}:${e.id}`)) ? p : ch));
    }, 250);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
  useEffect(() => ecouterSprites(marquer), []);

  // ---- Caméra -----------------------------------------------------------------------------------------------------
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
        vue.current = { cx: de.cx + (cible.cx - de.cx) * e, cy: de.cy + (cible.cy - de.cy) * e, zoom: de.zoom * (cible.zoom / de.zoom) ** e };
        marquer();
        if (k < 1) anim.current = requestAnimationFrame(pas);
        else resolve();
      };
      anim.current = requestAnimationFrame(pas);
    });
  }
  const toutVoir = useCallback((instant = false) => {
    const index = idx.current;
    if (!index) return Promise.resolve();
    const { x0, y0, x1, y1 } = index.g.bornes;
    const { W, H } = taille.current;
    const z = Math.min(W / (x1 - x0), H / (y1 - y0)) * 0.9;
    zMin.current = z * 0.8;
    return voler({ cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, zoom: z }, instant ? 0 : 500);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const charger = useCallback(async (nombre) => {
    setN(nombre); setSelection(null); setSurvol(null); setTest(null);
    idx.current = null; marquer();
    setEtat(`Génération de ${nombre.toLocaleString("fr")} jumeaux et de leur hiérarchie…`);
    await new Promise((r) => setTimeout(r, 30));
    const g = genererHierarchie(nombre);
    let tot = 0;
    for (let d = 0; d < NOMS_DOMAINES.length; d += 1) tot += g.niveaux[3].ecarts[d];
    g.moyEcarts = tot / g.n;
    setEtat("Construction de l'index…");
    await new Promise((r) => setTimeout(r, 30));
    const index = construireIndexHier(g);
    idx.current = index;
    setMesures({ gen: Math.round(g.tGen), index: Math.round(index.tIndex), mo: Math.round(index.octets / 1048576), liens: g.m, dom: g.niveaux[3].n, grp: g.niveaux[2].n, com: g.niveaux[1].n });
    setEtat("");
    await toutVoir(true);
  }, [toutVoir]);

  // ---- Interactions ---------------------------------------------------------------------------------------------------
  const versMonde = (ex, ey) => { const { W, H } = taille.current; const v = vue.current; return [(ex - W / 2) / v.zoom + v.cx, (ey - H / 2) / v.zoom + v.cy]; };
  const surRoulette = (e) => {
    if (!idx.current) return;
    e.preventDefault();
    cancelAnimationFrame(anim.current);
    effacerSurvol();
    const r = cadre.current.getBoundingClientRect();
    const ex = e.clientX - r.left, ey = e.clientY - r.top;
    const [wx, wy] = versMonde(ex, ey);
    const z = Math.max(zMin.current, Math.min(6, vue.current.zoom * Math.exp(-e.deltaY * 0.0016)));
    const { W, H } = taille.current;
    vue.current = { zoom: z, cx: wx - (ex - W / 2) / z, cy: wy - (ey - H / 2) / z };
    marquer();
  };
  const trouver = (ex, ey) => {
    const d = dernier.current;
    const g = idx.current.g;
    if (d.mode === "robots" || d.mode === "points") {
      const [wx, wy] = versMonde(ex, ey);
      const rayon = (d.mode === "robots" ? 28 : 7) / vue.current.zoom;
      const i = plusProche(g, d.vis, wx, wy, rayon);
      if (i >= 0) return { type: "noeud", i };
    }
    let meilleur = null, rmin = 1e12;
    d.bulles.forEach((b) => { const dd = Math.hypot(b.px - ex, b.py - ey); if (dd <= b.r + 2 && b.r < rmin) { rmin = b.r; meilleur = b; } });
    return meilleur ? { type: "bulle", niv: meilleur.niv, id: meilleur.id, r: meilleur.r } : null;
  };
  const surPointeurBas = (e) => {
    if (!idx.current) return;
    drag.current = { x: e.clientX, y: e.clientY, cx: vue.current.cx, cy: vue.current.cy, bouge: false };
    e.currentTarget.setPointerCapture(e.pointerId);
    cancelAnimationFrame(anim.current);
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
    const cle = h ? (h.type === "noeud" ? `n${h.i}` : `b${h.niv}:${h.id}`) : null;
    if (cle !== survolCle.current) {
      survolCle.current = cle;
      survolRef.current = h?.type === "noeud" ? h.i : -1;
      marquer();
      setSurvol(h ? { ...h, x: ex, y: ey } : null);
    }
  };
  const surPointeurHaut = (e) => {
    const d = drag.current;
    drag.current = null;
    if (!d || d.bouge) return;
    const r = cadre.current.getBoundingClientRect();
    const h = trouver(e.clientX - r.left, e.clientY - r.top);
    if (!h) return;
    if (h.type === "noeud") { setSelection(h.i); return; }
    const B = idx.current.g.niveaux[h.niv];
    const { W, H } = taille.current;
    voler({ cx: B.x[h.id], cy: B.y[h.id], zoom: Math.min(6, (Math.min(W, H) * 0.4) / B.r[h.id]) }, 700);
  };
  const surDoubleClic = (e) => {
    const r = cadre.current.getBoundingClientRect();
    const [wx, wy] = versMonde(e.clientX - r.left, e.clientY - r.top);
    voler({ cx: wx, cy: wy, zoom: Math.min(6, vue.current.zoom * 2) }, 400);
  };

  const allerA = (i) => { const g = idx.current.g; setSelection(i); voler({ cx: g.x[i], cy: g.y[i], zoom: 1.4 }, 900); };
  const chercher = (e) => {
    e.preventDefault();
    const index = idx.current;
    const m = recherche.trim().match(/^(.+?)\s+(\d+)$/);
    if (!index || !m) return;
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
    const c = g.com[selection];
    return { i: selection, nom: `${NOMS_DOMAINES[g.dom[selection]]} ${rangDansDomaine(g, selection)}`, dom: g.dom[selection], deg: g.deg[selection], cov: g.cov[selection], ecart: g.ecartN[selection], alerte: g.alerteN[selection], com: nomBulle(g, 1, c), voisins };
  }, [selection]); // eslint-disable-line react-hooks/exhaustive-deps

  const parcours = useCallback(async () => {
    const index = idx.current;
    if (!index) return null;
    const g = index.g;
    const pivot = Math.floor(g.n / 3);
    const dt = [];
    let dernierT = performance.now();
    let actif = true;
    const suivre = (t) => { dt.push(t - dernierT); dernierT = t; if (actif) requestAnimationFrame(suivre); };
    requestAnimationFrame(suivre);
    chronos.current.length = 0;
    await toutVoir(true);
    await new Promise((r) => setTimeout(r, 200));
    await voler({ cx: g.x[pivot], cy: g.y[pivot], zoom: 1.2 }, 2600); // domaine → groupe → communauté → points → robots
    await voler({ cx: g.x[pivot] + 2500, cy: g.y[pivot] + 1500, zoom: 1.2 }, 1200);
    await voler({ cx: g.x[pivot], cy: g.y[pivot], zoom: 0.006 }, 2000);
    await toutVoir();
    await new Promise((r) => setTimeout(r, 700));
    actif = false;
    const ms = [...chronos.current];
    const tri = [...dt].sort((a, b) => a - b);
    const moy = dt.reduce((a, b) => a + b, 0) / dt.length;
    const tD = [...ms].sort((a, b) => a - b);
    const res = { ips: Math.round(1000 / moy), pireImage: Math.round(tri[tri.length - 1]), p95Image: Math.round(tri[Math.floor(tri.length * 0.95)]), dessinMoy: +(ms.reduce((a, b) => a + b, 0) / Math.max(1, ms.length)).toFixed(2), dessinPire: +(tD[tD.length - 1] || 0).toFixed(1), images: dt.length };
    setTest(res);
    return res;
  }, [toutVoir]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.__semantique = { charger, parcours, voler, pos: (i) => ({ x: idx.current.g.x[i], y: idx.current.g.y[i] }), signaux: () => { const g = idx.current.g; return { ecarts: g.niveaux[3].ecarts.reduce((a, b) => a + b, 0), alertes: g.niveaux[3].alertes.reduce((a, b) => a + b, 0) }; }, stats: () => ({ ...dernier.current, bulles: dernier.current.bulles.length, vis: dernier.current.vis.length, zoom: vue.current.zoom }), memoire: () => Math.round((performance.memory?.usedJSHeapSize || 0) / 1048576) };
    return () => { delete window.__semantique; };
  }, [charger, parcours]); // eslint-disable-line react-hooks/exhaustive-deps

  const modeTexte = stats.mode === "robots" ? "jumeaux (robots)" : stats.mode === "points" ? "communautés + jumeaux en points" : `${["", "communautés", "groupes", "domaines"][stats.niv] || ""}${stats.fondu > 0.02 ? ` → ouverture ${Math.round(stats.fondu * 100)} %` : ""}`;
  const B = idx.current && survol?.type === "bulle" ? idx.current.g.niveaux[survol.niv] : null;

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#071019]" data-testid="labo-semantique">
      <div ref={cadre} className="absolute inset-0 touch-none select-none" onWheel={surRoulette} onPointerDown={surPointeurBas} onPointerMove={surPointeurBouge} onPointerUp={surPointeurHaut} onPointerLeave={() => { if (!drag.current) { effacerSurvol(); marquer(); } }} onDoubleClick={surDoubleClic} style={{ cursor: survol ? "pointer" : "grab" }}>
        <canvas ref={canvas} className="h-full w-full" data-testid="semantique-canvas" />
      </div>

      <div className="absolute left-4 top-4 z-10 w-[340px] space-y-2.5 rounded-xl border border-white/10 bg-[#0C1724] p-3.5 shadow-2xl" data-testid="semantique-hud">
        <div className="flex items-center gap-2">
          <Flask size={16} className="text-[#60A5FA]" />
          <div className="leading-tight">
            <div className="text-xs font-bold text-white">Laboratoire — agrégation sémantique</div>
            <div className="text-[10px] text-[#7C93A8]">Domaine → groupe → communauté → jumeau</div>
          </div>
        </div>
        <div className="inline-flex flex-wrap rounded-lg border border-white/10 bg-white/[0.03] p-0.5" role="group">
          {TAILLES.map(([v, l]) => (
            <button key={v} type="button" onClick={() => charger(v)} aria-pressed={n === v} data-testid={`semantique-n-${v}`} className={`min-h-[30px] rounded-md px-2.5 text-[11px] font-medium transition-colors ${n === v ? "bg-[#60A5FA]/25 text-white" : "text-[#7C93A8] hover:text-white"}`}>{l}</button>
          ))}
        </div>
        {etat && <p className="text-[11px] text-[#F2B84B]" data-testid="semantique-etat">{etat}</p>}
        {n && !etat && (
          <div className="space-y-0.5 rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="semantique-mesures">
            <div>{n.toLocaleString("fr")} jumeaux · {mesures.liens?.toLocaleString("fr")} liens</div>
            <div>{mesures.dom} domaines · {mesures.grp?.toLocaleString("fr")} groupes · {mesures.com?.toLocaleString("fr")} communautés</div>
            <div>Génération {mesures.gen} ms · index {mesures.index} ms · ≈ {mesures.mo} Mo</div>
            <div className="text-[#DCE6EE]">Vue : {modeTexte}</div>
            <div className="text-[#DCE6EE]">À l'écran : {stats.mode === "robots" ? `${stats.noeuds} jumeaux` : stats.mode === "points" ? `${stats.bulles} communautés · ${stats.points} points` : `${stats.bulles} grappes`} · {stats.liens} liens</div>
            <div className="text-[#60A5FA]">Dessin d'une image : {stats.ms ? stats.ms.toFixed(2) : "—"} ms</div>
          </div>
        )}
        <div className="space-y-1 border-t border-white/[0.07] pt-2">
          {[["Anneaux de signaux sur les grappes", signaux, setSignaux, "semantique-signaux"], ["Ouverture en fondu (grappe → enfants)", fondu, setFondu, "semantique-fondu"]].map(([l, v, set, id]) => (
            <button key={id} type="button" role="switch" aria-checked={v} onClick={() => set(!v)} data-testid={id} className="flex min-h-[28px] w-full items-center justify-between gap-3 text-left text-[11px] text-[#CBD5E1] hover:text-white">
              <span>{l}</span>
              <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${v ? "bg-[#60A5FA]" : "bg-white/15"}`}><span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${v ? "left-3.5" : "left-0.5"}`} /></span>
            </button>
          ))}
        </div>
        <form onSubmit={chercher} className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#071019] px-2.5">
          <MagnifyingGlass size={13} className="text-[#7C93A8]" />
          <input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Ex. : Support 120" data-testid="semantique-recherche" className="min-h-[32px] flex-1 bg-transparent text-xs text-white outline-none placeholder:text-[#526578]" />
        </form>
        <div className="flex gap-1.5">
          <button type="button" onClick={() => toutVoir()} data-testid="semantique-tout-voir" className="min-h-[30px] flex-1 rounded-lg border border-white/10 text-[11px] text-[#CBD5E1] hover:text-white">Tout voir</button>
          <button type="button" onClick={parcours} data-testid="semantique-parcours" className="flex min-h-[30px] flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#60A5FA]/40 bg-[#60A5FA]/15 text-[11px] font-semibold text-[#BFDBFE] hover:text-white"><Play size={11} weight="fill" /> Parcours de test</button>
        </div>
        {test && (
          <div className="rounded-lg bg-white/[0.03] p-2 font-code text-[10px] leading-relaxed text-[#94A3B8]" data-testid="semantique-test">
            <div className="text-[#DCE6EE]">{test.ips} images/s · pire image {test.pireImage} ms · p95 {test.p95Image} ms</div>
            <div>Dessin : {test.dessinMoy} ms en moyenne · {test.dessinPire} ms au pire ({test.images} images)</div>
          </div>
        )}
        <div className="space-y-1 border-t border-white/[0.07] pt-2 text-[10px] text-[#94A3B8]" data-testid="semantique-legende">
          <div className="flex items-center gap-2"><span className="inline-block h-2.5 w-5 rounded-full border-2 border-t-[#F59E0B] border-r-transparent border-b-transparent border-l-transparent" /> Arc orange : excès de jumeaux en écart (déclaré ≠ calculé)</div>
          <div className="flex items-center gap-2"><span className="inline-block h-2.5 w-5 rounded-full border-2 border-b-[#60A5FA] border-r-transparent border-t-transparent border-l-transparent" /> Arc violet : situations actives dans la grappe</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 pt-1">
            {NOMS_DOMAINES.map((d, i) => (<div key={d} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: COULEURS_DOMAINES[i] }} />{d}</div>))}
          </div>
        </div>
        <Link to="/labo/echelle" className="block text-center font-code text-[10px] text-[#7C93A8] hover:text-white">← Version grille (prototype 1)</Link>
      </div>

      {/* Fil d'Ariane passif */}
      {chemin.length > 0 && stats.mode !== undefined && (
        <div className="pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-full border border-white/10 bg-[#0C1724]/95 px-3.5 py-1.5 font-code text-[11px] text-[#CBD5E1] shadow-lg" data-testid="semantique-chemin">
          {chemin.map((c, i) => (<span key={c.niv}>{i > 0 && <span className="px-1.5 text-[#64748B]">›</span>}{c.nom}</span>))}
        </div>
      )}

      {/* Aperçu au survol */}
      {survol && idx.current && (
        <div className="pointer-events-none absolute z-20 w-[250px] space-y-1 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3 shadow-2xl" style={{ left: Math.min(survol.x + 18, taille.current.W - 260), top: Math.max(8, Math.min(survol.y - 30, taille.current.H - 190)) }} data-testid="semantique-apercu">
          {survol.type === "noeud" ? (
            <>
              <div className="text-sm font-semibold text-white">{NOMS_DOMAINES[idx.current.g.dom[survol.i]]} {rangDansDomaine(idx.current.g, survol.i)}</div>
              <div className="font-code text-[10px] text-[#7C93A8]">Degré {idx.current.g.deg[survol.i]} · couverture {idx.current.g.cov[survol.i]} %</div>
              {idx.current.g.ecartN[survol.i] === 1 && <div className="font-code text-[10px] text-[#F59E0B]">⚠ écart déclaré ↔ calculé</div>}
              {idx.current.g.alerteN[survol.i] === 1 && <div className="font-code text-[10px] text-[#60A5FA]">● situation active</div>}
            </>
          ) : B ? (
            <>
              <div className="text-[10px] uppercase tracking-wider text-[#64748B]">{B.nom}</div>
              <div className="text-sm font-semibold text-white">{nomBulle(idx.current.g, survol.niv, survol.id)}</div>
              <div className="font-code text-[11px] text-[#CBD5E1]">{B.taille[survol.id].toLocaleString("fr")} jumeaux</div>
              <div className="font-code text-[10px] text-[#F59E0B]">{B.ecarts[survol.id].toLocaleString("fr")} en écart ({(100 * B.ecarts[survol.id] / B.taille[survol.id]).toFixed(1)} %)</div>
              <div className="font-code text-[10px] text-[#60A5FA]">{B.alertes[survol.id].toLocaleString("fr")} en situation active</div>
              <div className="font-code text-[9px] text-[#526578]">Cliquer pour ouvrir cette grappe</div>
            </>
          ) : null}
        </div>
      )}

      {fiche && (
        <div className="absolute right-4 top-4 z-10 w-[270px] space-y-1.5 rounded-xl border border-white/10 bg-[#0C1724]/95 p-3.5 shadow-2xl" data-testid="semantique-fiche">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: COULEURS_DOMAINES[fiche.dom] }} />
            <span className="flex-1 text-sm font-semibold text-white">{fiche.nom}</span>
            <button type="button" onClick={() => setSelection(null)} aria-label="Fermer" className="text-[#7C93A8] hover:text-white">✕</button>
          </div>
          <div className="font-code text-[10px] text-[#94A3B8]">{fiche.com}</div>
          <div className="font-code text-[10px] text-[#94A3B8]">Degré {fiche.deg} · couverture {fiche.cov} %</div>
          {fiche.ecart === 1 && <div className="font-code text-[10px] text-[#F59E0B]">⚠ écart déclaré ↔ calculé</div>}
          {fiche.alerte === 1 && <div className="font-code text-[10px] text-[#60A5FA]">● situation active</div>}
          <div className="pt-1 text-[10px] text-[#64748B]">Voisins</div>
          <div className="space-y-0.5">
            {fiche.voisins.map((j) => (
              <button key={j} type="button" onClick={() => allerA(j)} className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[11px] text-[#CBD5E1] hover:bg-white/[0.06]">
                <span className="h-2 w-2 rounded-full" style={{ background: COULEURS_DOMAINES[idx.current.g.dom[j]] }} />{NOMS_DOMAINES[idx.current.g.dom[j]]} {rangDansDomaine(idx.current.g, j)}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute bottom-3 right-4 z-10 rounded-md bg-[#071019]/80 px-2.5 py-1 font-code text-[10px] text-[#7C93A8]">
        Molette : zoom · glisser : déplacer · clic sur une grappe : l'ouvrir · double-clic : zoom ×2
      </div>
    </div>
  );
}
