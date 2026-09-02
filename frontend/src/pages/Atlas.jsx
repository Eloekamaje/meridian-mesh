import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls, ControlButton, MiniMap, SelectionMode, ViewportPortal } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Sparkle, CornersOut, MagnifyingGlass } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
import AreteOrthogonale from "@/components/map/AreteOrthogonale";
import AtlasControle from "@/components/map/AtlasControle";
import AtlasToolbar from "@/components/map/AtlasToolbar";
import AtlasLegende from "@/components/map/AtlasLegende";
import AtlasPanneau from "@/components/map/AtlasPanneau";
import FilAriane from "@/components/map/FilAriane";
import ExpliquerCarte from "@/components/map/ExpliquerCarte";
import ComposerFlore from "@/components/ComposerFlore";
import useNavigationAtlas from "@/components/map/useNavigationAtlas";
import useZoomSemantique from "@/components/map/useZoomSemantique";
import { NIVEAUX_ZOOM, construireGraphe, statsDuDomaine, idNumerique } from "@/lib/atlasGraph";
import { useRoutageFinal } from "@/lib/routage";
import { couleurDomaine, ETATS_RELATION, MATURITES } from "@/lib/domaines";
import { parseQuand, finDeJournee, fmtDate } from "@/lib/temps";

const nodeTypes = { twin: TwinNode, region: RegionNode };
const edgeTypes = { ortho: AreteOrthogonale };

export default function Atlas() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { mesh, jumeauPar, recharger } = useMesh();
  const { version, vueActive, rechargerVues } = usePerimetre();
  const [situations, setSituations] = useState([]);
  const focus = searchParams.get("focus");
  const situationParam = searchParams.get("situation");
  const [selected, setSelected] = useState(null);
  const [selectedRelation, setSelectedRelation] = useState(null);
  const [events, setEvents] = useState([]);
  const [halo, setHalo] = useState(null);
  const [compteurs, setCompteurs] = useState({});
  const [onglet, setOnglet] = useState("chrono");
  const [couches, setCouches] = useState({ operationnelle: true, connaissance: true, mesh: true });
  const [modeTemps, setModeTemps] = useState("direct"); // direct | pause | replay | historique | avantapres
  const [dateRef, setDateRef] = useState(null); // ms — curseur temporel
  const [replaying, setReplaying] = useState(false);
  const [expliquerOuvert, setExpliquerOuvert] = useState(false);
  const direct = modeTemps === "direct";
  const [outil, setOutil] = useState("deplacement");
  const { selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, setFocusVisuel, ouvrirFlore } = useContexte();
  const [relFocus, setRelFocus] = useState(false);
  const [posOverrides, setPosOverrides] = useState({});
  const [epingle, setEpingle] = useState(null); // jumeau épinglé (panneau flottant persistant)
  const [survolJumeau, setSurvolJumeau] = useState(null);
  const [relSurvolee, setRelSurvolee] = useState(null); // relation survolée (arête)
  const [relTooltipPos, setRelTooltipPos] = useState(null);
  const [couchesRel, setCouchesRel] = useState({ bcm: true, realite: true, ecarts: true });
  const [recherche, setRecherche] = useState("");
  const carteRef = useRef(null);
  const [amorce, setAmorce] = useState(0);
  const [mesures, setMesures] = useState({}); // dimensions mesurées par React Flow, réinjectées dans le graphe
  const [zoomActuel, setZoomActuel] = useState(1);
  const [regionSurvolee, setRegionSurvolee] = useState(null); // membrane survolée {id, label} (proximité frontière)
  const [regionTooltip, setRegionTooltip] = useState(null);
  const [modeEdition, setModeEdition] = useState(false); // déplacement des robots uniquement en mode explicite
  const [provisoire, setProvisoire] = useState(false); // drag en cours : routage maison simple, recalcul final au relâchement
  const { routesFin, pousser } = useRoutageFinal(); // routes finales calculées par libavoid (Web Worker)
  const [fantome, setFantome] = useState(null); // position de départ du robot pendant le drag
  const coquesRef = useRef({}); // rect actuellement affiché de chaque membrane
  const ciblesCoques = useRef({}); // rect cible calculé
  const rafCoques = useRef(null);
  const [tickCoques, setTickCoques] = useState(0);
  const mouvements = useRef([]); // échantillons du viewport pour l'inertie
  const inertie = useRef(false);
  const [perimetreTravail, setPerimetreTravail] = useState(null);
  const [attenteComparaison, setAttenteComparaison] = useState(false);
  const [comparaison, setComparaison] = useState(null);
  const rfRef = useRef(null);
  const dernierClicRegion = useRef({ kind: null, t: 0 });
  const dernierClicPane = useRef(0);
  const restaure = useRef(false);
  const selAvantLasso = useRef([]);
  const centreFocusFait = useRef(null);
  const selectionFocusFaite = useRef(null);

  const urlRef = useRef(null);
  useEffect(() => { urlRef.current = new URLSearchParams(searchParams); }, [searchParams]);
  const majUrl = useCallback((updates) => {
    const p = new URLSearchParams(urlRef.current || undefined);
    Object.entries(updates).forEach(([k, v]) => (v == null ? p.delete(k) : p.set(k, v)));
    urlRef.current = p;
    setSearchParams(p, { replace: true });
  }, [setSearchParams]);

  const domDe = useMemo(() => {
    const m = {};
    (mesh?.jumeaux || []).forEach((j) => { m[j.id] = j.domaine; });
    return m;
  }, [mesh]);

  // Dates de découverte des relations (projection temporelle du Mesh)
  const relTs = useMemo(() => {
    const m = {};
    (mesh?.relations || []).forEach((r) => {
      const d = parseQuand(r.decouverte_quand);
      if (d) m[r.id] = d.getTime();
    });
    return m;
  }, [mesh]);

  const plageMin = useMemo(() => {
    const vals = Object.values(relTs);
    return vals.length ? Math.min(...vals) : Date.now() - 30 * 864e5;
  }, [relTs]);

  // ?date=AAAA-MM-JJ — photographie historique ; ?avant-apres=AAAA-MM-JJ — comparaison
  const dateParam = searchParams.get("date");
  useEffect(() => {
    if (!dateParam) return;
    const d = new Date(`${dateParam.slice(0, 10)}T12:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setModeTemps("historique");
    setDateRef(finDeJournee(d).getTime());
  }, [dateParam]);

  const aaParam = searchParams.get("avant-apres");
  useEffect(() => {
    if (!aaParam) return;
    const d = new Date(`${aaParam.slice(0, 10)}T12:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setModeTemps("avantapres");
    setDateRef(finDeJournee(d).getTime());
  }, [aaParam]);

  // Replay : relecture accélérée de la construction du Mesh (de la 1re relation à maintenant)
  useEffect(() => {
    if (!replaying) return undefined;
    const fin = Date.now();
    const pas = Math.max((fin - plageMin) / 50, 3600e3);
    setDateRef(plageMin);
    const t = setInterval(() => {
      setDateRef((d) => {
        const n = (d ?? plageMin) + pas;
        if (n >= fin) {
          clearInterval(t);
          setReplaying(false);
          return fin;
        }
        return n;
      });
    }, 160);
    return () => clearInterval(t);
  }, [replaying, plageMin]);

  const temps = useMemo(() => {
    if (modeTemps === "direct" || modeTemps === "pause" || !dateRef) return null;
    return { mode: modeTemps === "avantapres" ? "avantapres" : "historique", dateTs: dateRef, relTs };
  }, [modeTemps, dateRef, relTs]);

  const nbNouvelles = useMemo(
    () => (modeTemps === "avantapres" && dateRef ? Object.values(relTs).filter((ts) => ts > dateRef).length : 0),
    [modeTemps, dateRef, relTs]
  );

  // Découvertes et investigations actives par domaine (situations non closes touchant le domaine)
  const statsRegions = useMemo(() => {
    const stats = {};
    situations.forEach((s) => {
      if (["ignorée", "classée", "décidée"].includes(s.statut)) return;
      const doms = new Set((s.jumeaux || []).map((j) => domDe[j]).filter(Boolean));
      doms.forEach((d) => {
        if (!stats[d]) stats[d] = { decouvertes: 0, investigations: 0 };
        if (s.verbe === "a_comprendre") stats[d].investigations += 1;
        else if (s.verbe === "decouvert") stats[d].decouvertes += 1;
      });
    });
    return stats;
  }, [situations, domDe]);

  const {
    domaineInterne, setDomaineInterne, jumeauFocus, setJumeauFocus,
    historique, indexHist,
    entrerDomaine, sortirDomaine, entrerJumeau, sortirJumeau, allerHist, revenirSelection,
    verrouNav, zoomEntree,
  } = useNavigationAtlas({
    mesh, jumeauPar, posOverrides, selection, majUrl,
    setDomaineSel, setOnglet, setSelected, setRelFocus, setFocusVisuel, rfRef,
  });

  const { zoomNiveau, onMove, onNodeMouseEnter, onNodeMouseLeave } = useZoomSemantique({
    jumeauFocus, domaineInterne,
    sortirJumeau, sortirDomaine, entrerJumeau, entrerDomaine,
    jumeauPar, verrouNav, zoomEntree,
  });

  // Restauration du contexte depuis l'URL au chargement (?domaine=X&interne=1&sel=y)
  useEffect(() => {
    if (!mesh || restaure.current) return;
    restaure.current = true;
    const d = searchParams.get("domaine");
    const s = searchParams.get("sel");
    if (d && (mesh.regions || []).some((r) => r.label === d)) {
      setDomaineSel(d);
      setOnglet("detail");
      if (searchParams.get("interne") === "1") setDomaineInterne(d);
    }
    if (s) {
      const j = mesh.jumeaux.find((x) => x.id === s && !x.anonyme);
      if (j) { setSelected(j); setOnglet("detail"); }
    }
    const jf = searchParams.get("jumeau");
    if (jf) {
      const j = mesh.jumeaux.find((x) => x.id === jf && !x.anonyme);
      if (j) { setDomaineInterne(j.domaine); setJumeauFocus(j.id); setSelected(j); setOnglet("detail"); }
    }
  }, [mesh]);

  // Commandes carte envoyées par Aurora (éclairer des relations, isoler un parcours, aller à un domaine)
  useEffect(() => {
    if (!focusCarte) return;
    if (focusCarte.type === "parcours" && focusCarte.ids?.length) {
      setSelection(focusCarte.ids.filter((id) => mesh?.jumeaux.some((j) => j.id === id)));
      setRelFocus(true);
    } else if (focusCarte.type === "domaine" && focusCarte.domaine) {
      entrerDomaine(focusCarte.domaine);
    }
  }, [focusCarte]);

  const statsDomaine = useCallback(
    (label) => statsDuDomaine(mesh, situations, domDe, label),
    [mesh, situations, domDe]
  );

  const onNodesChange = useCallback((changes) => {
    // Changements de dimensions : les réinjecter dans nos nœuds dérivés — sinon le store
    // interne ne connaît jamais les ports et les arêtes restent invisibles (course au montage)
    const dims = changes.filter((c) => c.type === "dimensions" && c.dimensions);
    if (dims.length) {
      setMesures((m) => {
        let next = m;
        for (const c of dims) {
          const cur = m[c.id];
          if (cur && Math.abs(cur.width - c.dimensions.width) < 1 && Math.abs(cur.height - c.dimensions.height) < 1) continue;
          if (next === m) next = { ...m };
          next[c.id] = { width: c.dimensions.width, height: c.dimensions.height };
        }
        return next;
      });
    }
    setSelection((prev) => {
      let next = prev;
      for (const ch of changes) {
        if (ch.type !== "select" || ch.id.startsWith("reg-")) continue;
        const has = next.includes(ch.id);
        if (ch.selected && !has) next = next === prev ? [...prev, ch.id] : [...next, ch.id];
        if (!ch.selected && has) next = (next === prev ? [...prev] : next).filter((x) => x !== ch.id);
      }
      return next;
    });
    setPosOverrides((prev) => {
      let next = prev;
      for (const ch of changes) {
        if (ch.type === "position" && ch.position) {
          if (next === prev) next = { ...prev };
          next[ch.id] = ch.position;
        }
      }
      return next;
    });
  }, []);

  useEffect(() => {
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
  }, [version]);

  useEffect(() => {
    setEvents([]);
    setCompteurs({});
  }, [version]);

  useEffect(() => {
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (stop) return;
        setEvents((prev) => [...data.map((e, i) => ({ ...e, uid: `${Date.now()}-${i}` })), ...prev].slice(0, 18));
        setHalo(data[Math.floor(Math.random() * data.length)].jumeau);
        setCompteurs((c) => {
          const n = { ...c };
          data.forEach((e) => { n[e.jumeau] = (n[e.jumeau] || 0) + 1; });
          return n;
        });
        clearTimeout(timer);
        timer = setTimeout(() => setHalo(null), 2600);
      } catch {}
    };
    tick();
    if (!direct) return;
    const t = setInterval(tick, 6000);
    return () => { stop = true; clearInterval(t); clearTimeout(timer); };
  }, [version, direct]);

  const situation = situations.find((s) => s.id === situationParam);

  // Focus profond : la caméra cadre les jumeaux concernés (situation ou jumeau filtré)
  useEffect(() => {
    const cle = situation?.id || focus || null;
    if (!mesh || !cle || domaineInterne || jumeauFocus || centreFocusFait.current === cle) return;
    const cibles = situation
      ? (situation.jumeaux || []).map((id) => mesh.jumeaux.find((j) => j.id === id)).filter(Boolean)
      : [mesh.jumeaux.find((j) => j.id === focus)].filter(Boolean);
    if (!cibles.length) return;
    centreFocusFait.current = cle;
    const t = setTimeout(() => {
      const pts = cibles.map((j) => posOverrides[j.id] || j.position);
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      rfRef.current?.fitBounds(
        { x: Math.min(...xs) - 230, y: Math.min(...ys) - 190, width: Math.max(...xs) - Math.min(...xs) + 460, height: Math.max(...ys) - Math.min(...ys) + 380 },
        { duration: 800 }
      );
    }, 350);
    return () => clearTimeout(t);
  }, [mesh, situation, focus, domaineInterne, jumeauFocus]);

  // Le contexte Aurora suit toujours le focus profond : les jumeaux concernés deviennent la sélection
  useEffect(() => {
    if (!mesh || !situation || selectionFocusFaite.current === situation.id) return;
    const ids = (situation.jumeaux || []).filter((id) => mesh.jumeaux.some((j) => j.id === id && !j.anonyme));
    if (ids.length) {
      selectionFocusFaite.current = situation.id;
      setSelection(ids);
    }
  }, [mesh, situation]);

  const { nodes, edges, snapshot } = useMemo(() => {
    const g = construireGraphe({
      mesh, situation, focus, vueActive, perimetreTravail,
      jumeauFocus, domaineInterne, posOverrides, compteurs, halo, selection,
      zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps,
      zoomFort: zoomActuel >= 1.5,
      routesFin, provisoire,
    });
    // Conserve les dimensions mesurées par React Flow : le graphe est reconstruit à chaque
    // tick de drag — sans cela les nœuds perdent leur mesure et les arêtes disparaissent.
    const internes = rfRef.current?.getNodes?.() || [];
    const parId = new Map(internes.map((n) => [n.id, n]));
    const nouvellesCibles = {};
    g.nodes = g.nodes.map((n) => {
      if (n.type === "region") {
        const cible = { x: n.position.x, y: n.position.y, w: n.data.w, h: n.data.h };
        nouvellesCibles[n.id] = cible;
        const cur = coquesRef.current[n.id];
        if (!cur) coquesRef.current[n.id] = { ...cible };
        // Ressort : la membrane affichée poursuit sa cible (matière souple, stabilisation ~300 ms)
        const a = coquesRef.current[n.id];
        n = {
          ...n,
          position: { x: a.x, y: a.y },
          initialWidth: a.w,
          initialHeight: a.h,
          data: {
            ...n.data,
            w: a.w,
            h: a.h,
            wCible: cible.w,
            hCible: cible.h,
            survol: regionSurvolee?.id === n.data.id,
            attenue: !!regionSurvolee && regionSurvolee.id !== n.data.id,
          },
        };
      }
      if (n.type === "twin" && regionSurvolee && n.data.jumeau && !n.data.jumeau.porte && n.data.jumeau.domaine !== regionSurvolee.label) {
        n = { ...n, data: { ...n.data, adouci: true } };
      }
      // Robots source/cible de la relation survolée ou sélectionnée : anneau turquoise
      const relActive = relSurvolee || selectedRelation?.id;
      if (n.type === "twin" && relActive && mesh) {
        const rel = mesh.relations.find((r) => r.id === relActive);
        if (rel && n.data.jumeau && (rel.source === n.data.jumeau.id || rel.cible === n.data.jumeau.id)) {
          n = { ...n, data: { ...n.data, relLiee: true } };
        }
      }
      const prev = parId.get(n.id);
      const dim = mesures[n.id];
      const base = prev?.measured ? { ...n, measured: prev.measured, dragging: prev.dragging || undefined } : n;
      return dim ? { ...base, width: dim.width, height: dim.height, measured: { width: dim.width, height: dim.height } } : base;
    });
    ciblesCoques.current = nouvellesCibles;
    return g;
  }, [mesh, focus, situation, halo, compteurs, selection, relFocus, zoomNiveau, vueActive, posOverrides, domaineSel, domaineInterne, jumeauFocus, perimetreTravail, domDe, statsRegions, focusCarte, temps, amorce, mesures, regionSurvolee, tickCoques, relSurvolee, selectedRelation, zoomActuel, routesFin, provisoire]);

  // Routage final : nouveau snapshot géométrique → Web Worker libavoid
  // (jamais pendant le drag, jamais pendant le pan/zoom — la signature géométrique est stable)
  useEffect(() => {
    if (!provisoire && snapshot) pousser(snapshot);
  }, [snapshot, provisoire, pousser]);

  // Couches de relations (BCM déclaré / Réalité découverte / Écarts) + accentuation au survol/épinglage
  const edgesVisibles = useMemo(() => {
    let es = edges.filter((e) => {
      const etat = e.data?.etat;
      if (etat === "confirmee" || etat === "obsolete") return couchesRel.bcm;
      if (etat === "observee" || etat === "validation") return couchesRel.realite;
      if (etat === "supposee" || etat === "contestee") return couchesRel.ecarts;
      return true;
    });
    const actif = epingle || survolJumeau;
    if (actif) {
      es = es.map((e) =>
        e.source === actif || e.target === actif || e.source === `voisin-${actif}` || e.target === `voisin-${actif}`
          ? { ...e, zIndex: 20, style: { ...e.style, strokeWidth: (e.style?.strokeWidth || 1.5) + 1, opacity: 1 } }
          : { ...e, label: undefined, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.12 } }
      );
    }
    // Survol d'une voie agrégée « N flux » : déploiement temporaire des routes membres
    if (relSurvolee?.startsWith("agg-")) {
      return es.map((e) => {
        if (e.id === relSurvolee) return { ...e, hidden: true };
        if (e.data?.groupe === relSurvolee) return { ...e, hidden: false, zIndex: 25, style: { ...e.style, opacity: 1 } };
        return { ...e, label: undefined, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.15 } };
      });
    }
    // Survol/sélection d'une relation : trajet mis en avant, les autres estompées (15–30 % d'opacité)
    const relActive = relSurvolee || selectedRelation?.id;
    if (relActive) {
      es = es.map((e) =>
        e.id === relActive
          ? { ...e, zIndex: 30, data: { ...e.data, survolee: true, estompee: false }, style: { ...e.style, opacity: 1 } }
          : { ...e, data: { ...e.data, estompee: true }, style: { ...e.style, opacity: 0.2 } }
      );
      // la relation active se dessine au-dessus des autres
      es = [...es.filter((e) => e.id !== relActive), ...es.filter((e) => e.id === relActive)];
    }
    return es;
  }, [edges, couchesRel, epingle, survolJumeau, relSurvolee, selectedRelation]);

  // Jumeau survolé ou épinglé → panneau flottant à gauche
  const jumeauSurvole = useMemo(() => {
    const id = epingle || survolJumeau;
    return id && mesh ? mesh.jumeaux.find((x) => x.id === id && !x.anonyme) || null : null;
  }, [epingle, survolJumeau, mesh]);
  const statsJumeau = useMemo(() => {
    if (!jumeauSurvole || !mesh) return null;
    const liees = mesh.relations.filter((r) => r.source === jumeauSurvole.id || r.cible === jumeauSurvole.id);
    return {
      flux: liees.filter((r) => r.etat === "observee").length,
      ecarts: liees.filter((r) => r.etat === "supposee" || r.etat === "contestee").length,
    };
  }, [jumeauSurvole, mesh]);

  const resultatsRecherche = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    if (!q || !mesh) return [];
    const js = mesh.jumeaux
      .filter((j) => !j.anonyme && (j.nom.toLowerCase().includes(q) || idNumerique(j.id).includes(q)))
      .slice(0, 5)
      .map((j) => ({ type: "jumeau", id: j.id, label: j.nom, sub: `${idNumerique(j.id)} · ${j.domaine}` }));
    const ds = (mesh.regions || [])
      .filter((r) => r.label.toLowerCase().includes(q))
      .slice(0, 3)
      .map((r) => ({ type: "domaine", id: r.label, label: r.label, sub: "domaine" }));
    return [...js, ...ds];
  }, [recherche, mesh]);

  // Échap ferme la sélection épinglée ; +/−/0 pilotent le zoom (comme Google Maps)
  useEffect(() => {
    const h = (e) => {
      const cible = e.target?.tagName;
      if (cible === "INPUT" || cible === "TEXTAREA") return;
      if (e.key === "Escape") setEpingle(null);
      if (e.key === "+" || e.key === "=") rfRef.current?.zoomIn({ duration: 220 });
      if (e.key === "-") rfRef.current?.zoomOut({ duration: 220 });
      if (e.key === "0") rfRef.current?.fitView({ duration: 300, padding: 0.15 });
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  // Amorce : force une reconstruction du graphe après le montage pour que React Flow
  // ait mesuré les ports (sinon les arêtes peuvent rester invisibles au premier rendu)
  useEffect(() => {
    if (amorce >= 2) return undefined;
    const t = setTimeout(() => setAmorce((a) => a + 1), amorce === 0 ? 250 : 700);
    return () => clearTimeout(t);
  }, [amorce]);

  const pleinEcran = () => {
    const el = carteRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };

  // Ressort des membranes : poursuite exponentielle (~300 ms, sans vibration)
  const poursuite = useCallback(() => {
    let actif = false;
    const alpha = 1 - Math.exp(-(1 / 60) * 9);
    for (const [id, cible] of Object.entries(ciblesCoques.current)) {
      const cur = coquesRef.current[id] || { ...cible };
      const n = {
        x: cur.x + (cible.x - cur.x) * alpha,
        y: cur.y + (cible.y - cur.y) * alpha,
        w: cur.w + (cible.w - cur.w) * alpha,
        h: cur.h + (cible.h - cur.h) * alpha,
      };
      const fini = Math.abs(n.x - cible.x) + Math.abs(n.y - cible.y) + Math.abs(n.w - cible.w) + Math.abs(n.h - cible.h) < 0.6;
      coquesRef.current[id] = fini ? { ...cible } : n;
      if (!fini) actif = true;
    }
    if (actif) {
      setTickCoques((t) => t + 1);
      rafCoques.current = requestAnimationFrame(poursuite);
    } else {
      rafCoques.current = null;
    }
  }, []);

  useEffect(() => {
    if (!rafCoques.current && Object.keys(ciblesCoques.current).length > 0) {
      rafCoques.current = requestAnimationFrame(poursuite);
    }
  }, [nodes, poursuite]);

  // Survol des membranes par proximité de la frontière (les zones d'interaction des arêtes les recouvrent)
  const surSurvolCarte = (e) => {
    if (!rfRef.current || !mesh || jumeauFocus) return;
    const rect = carteRef.current?.getBoundingClientRect();
    if (!rect) return;
    if (relSurvolee) setRelTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const zoom = rfRef.current.getZoom() || 1;
    let trouve = null;
    for (const n of nodes) {
      if (n.type !== "region" || !n.data.points) continue;
      const ox = n.position.x;
      const oy = n.position.y;
      const pts = n.data.points;
      let min = Infinity;
      for (let i = 0; i < pts.length; i++) {
        const ax = pts[i].x + ox;
        const ay = pts[i].y + oy;
        const bx = pts[(i + 1) % pts.length].x + ox;
        const by = pts[(i + 1) % pts.length].y + oy;
        const dx = bx - ax;
        const dy = by - ay;
        const L2 = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((p.x - ax) * dx + (p.y - ay) * dy) / L2));
        const d = Math.hypot(p.x - (ax + t * dx), p.y - (ay + t * dy));
        if (d < min) min = d;
      }
      if (min < 18 / zoom) { trouve = n; break; }
    }
    if (trouve) {
      if (regionSurvolee?.id !== trouve.data.id) setRegionSurvolee({ id: trouve.data.id, label: trouve.data.label });
      setRegionTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, data: trouve.data });
    } else if (regionSurvolee) {
      setRegionSurvolee(null);
      setRegionTooltip(null);
    }
  };

  // Inertie de déplacement : échantillonnage du viewport, décélération progressive au relâchement
  const surMove = (e, vp) => {
    onMove(e, vp);
    setZoomActuel((z) => {
      const arr = Math.round(vp.zoom * 20) / 20;
      return Math.abs(arr - z) >= 0.05 ? arr : z;
    });
    if (inertie.current) return;
    const t = Date.now();
    mouvements.current.push({ t, x: vp.x, y: vp.y, zoom: vp.zoom });
    mouvements.current = mouvements.current.filter((m) => t - m.t < 180);
  };

  const surMoveEnd = () => {
    const ms = mouvements.current;
    mouvements.current = [];
    if (!rfRef.current || ms.length < 2) return;
    const a = ms[0];
    const b = ms[ms.length - 1];
    const dt = (b.t - a.t) / 1000;
    if (dt <= 0.02) return;
    let vx = (b.x - a.x) / dt;
    let vy = (b.y - a.y) / dt;
    if (Math.hypot(vx, vy) < 80) return; // trop lent : pas d'inertie
    inertie.current = true;
    let px = b.x;
    let py = b.y;
    let dernier = performance.now();
    const pas = (t) => {
      const d = Math.min((t - dernier) / 1000, 0.05);
      dernier = t;
      const fr = Math.exp(-d * 5.5); // amortissement rapide
      vx *= fr;
      vy *= fr;
      px += vx * d;
      py += vy * d;
      rfRef.current?.setViewport({ x: px, y: py, zoom: rfRef.current.getZoom() });
      if (Math.hypot(vx, vy) > 14) requestAnimationFrame(pas);
      else inertie.current = false;
    };
    requestAnimationFrame(pas);
  };

  // Déplacement d'un robot — uniquement en mode réorganisation
  const debutDrag = (_, node) => {
    if (node.type !== "twin" || !node.data?.jumeau || node.data.jumeau.porte || node.data.voisinRel) return;
    setProvisoire(true);
    const rect = carteRef.current?.getBoundingClientRect();
    if (!rect || !rfRef.current) return;
    const sp = rfRef.current.flowToScreenPosition({ x: node.position.x + 30, y: node.position.y + 40 });
    setFantome({ x: sp.x - rect.left, y: sp.y - rect.top });
  };

  const finDrag = async (_, node) => {
    setFantome(null);
    setProvisoire(false); // déclenche le routage final (Worker) + interpolation des trajets
    if (node.type !== "twin" || !node.data?.jumeau || node.data.jumeau.porte || node.data.voisinRel) return;
    const j = node.data.jumeau;
    const pos = node.position;
    try {
      await api.patch(`/jumeaux/${j.id}`, { position: { x: Math.round(pos.x), y: Math.round(pos.y) } });
    } catch {
      toast.error("Position non enregistrée");
      return;
    }
    // Reclassification jamais automatique : proposition à l'humain
    const centre = { x: pos.x + 30, y: pos.y + 40 };
    const dansPolygone = (pts, ox, oy) => {
      let dedans = false;
      for (let i = 0, k = pts.length - 1; i < pts.length; k = i++) {
        const xi = pts[i].x + ox;
        const yi = pts[i].y + oy;
        const xj = pts[k].x + ox;
        const yj = pts[k].y + oy;
        if (yi > centre.y !== yj > centre.y && centre.x < ((xj - xi) * (centre.y - yi)) / (yj - yi) + xi) dedans = !dedans;
      }
      return dedans;
    };
    let domaineHote = null;
    let minDist = Infinity;
    for (const n of nodes) {
      if (n.type !== "region" || !n.data.points) continue;
      if (dansPolygone(n.data.points, n.position.x, n.position.y)) domaineHote = n.data.label;
      for (const p of n.data.points) {
        minDist = Math.min(minDist, Math.hypot(centre.x - (p.x + n.position.x), centre.y - (p.y + n.position.y)));
      }
    }
    if (domaineHote && domaineHote !== j.domaine) {
      toast(`${j.nom} semble appartenir au domaine ${domaineHote}`, {
        description: "La reclassification n'est jamais automatique — elle vous appartient.",
        duration: 9000,
        action: {
          label: `Reclasser dans ${domaineHote}`,
          onClick: async () => {
            try {
              await api.patch(`/jumeaux/${j.id}`, { domaine: domaineHote });
              toast.success(`${j.nom} reclassé dans ${domaineHote}`);
              recharger();
            } catch {
              toast.error("Reclassification impossible");
            }
          },
        },
      });
    } else if (!domaineHote && minDist > 160) {
      toast.info(`${j.nom} s'éloigne fortement de « ${j.domaine} » — appartenance à qualifier.`, { duration: 7000 });
    }
  };

  const centrerSurJumeau = (id) => {
    const j = mesh?.jumeaux.find((x) => x.id === id);
    if (!j) return;
    const pos = posOverrides[id] || j.position;
    setEpingle(id);
    setHalo(id); // membrane + robot brièvement mis en évidence
    setTimeout(() => setHalo((h) => (h === id ? null : h)), 2000);
    rfRef.current?.setCenter(pos.x + 30, pos.y + 40, { zoom: 1.4, duration: 600 });
    setRecherche("");
  };

  const eventsVisibles = events.filter((e) => couches[e.dynamique || "operationnelle"]);

  const confirmerRelation = async (r) => {
    try {
      await api.post(`/relations/${r.id}/confirmer`);
      toast.success("Relation confirmée — mémoire du Mesh enrichie");
      setSelectedRelation(null);
      recharger();
    } catch {
      toast.error("Confirmation impossible — permission « Valider » requise");
    }
  };

  const actionsDomaine = domaineSel
    ? {
        dedans: domaineInterne === domaineSel,
        onExplorer: () => entrerDomaine(domaineSel),
        onQuitter: sortirDomaine,
        onComparer: () => { setAttenteComparaison(true); toast.info("Cliquez un second domaine pour comparer"); },
        onEnregistrer: async () => {
          const stats = statsDomaine(domaineSel);
          if (!stats) return;
          try {
            await api.post("/vues", { nom: `Domaine ${domaineSel}`, type: "selection", jumeaux: stats.twins.map((j) => j.id) });
            rechargerVues();
            toast.success(`Domaine ${domaineSel} enregistré comme espace de travail (vue)`);
          } catch {
            toast.error("Enregistrement impossible");
          }
        },
        perimetre: perimetreTravail === domaineSel,
        onPerimetre: () => setPerimetreTravail(perimetreTravail === domaineSel ? null : domaineSel),
      }
    : null;

  return (
    <div className="flex h-full flex-col">
    <div ref={carteRef} onPointerMove={surSurvolCarte} onPointerLeave={() => { setRegionSurvolee(null); setRegionTooltip(null); }} className="relative min-h-0 flex-1 overflow-hidden" data-testid="system-map" style={{ background: "radial-gradient(ellipse at 50% 38%, #FDFDFB 0%, #F5F4F0 65%, #EDECE6 100%)" }}>
      <ReactFlow
        key={focus || situationParam || "mesh"}
        nodes={nodes}
        edges={edgesVisibles}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        maxZoom={2.6}
        zoomOnDoubleClick={false}
        onInit={(inst) => {
          rfRef.current = inst;
          setTimeout(() => {
            try { inst.updateNodeInternals(inst.getNodes().map((n) => n.id)); } catch { /* mesure ultérieure */ }
          }, 120);
        }}
        onMove={surMove}
        onMoveEnd={surMoveEnd}
        onNodeDragStart={debutDrag}
        onNodeDragStop={finDrag}
        onNodeMouseEnter={(e, node) => {
          onNodeMouseEnter(e, node);
          if (node.type === "twin" && !node.data?.porte && !node.data?.voisinRel && !node.data?.jumeau?.anonyme) setSurvolJumeau(node.data.jumeau.id);
        }}
        onNodeMouseLeave={(e, node) => { onNodeMouseLeave(e, node); setSurvolJumeau(null); }}
        onNodesChange={onNodesChange}
        panOnDrag={outil === "deplacement"}
        selectionOnDrag={outil === "lasso"}
        selectionMode={SelectionMode.Partial}
        multiSelectionKeyCode={["Meta", "Control", "Shift"]}
        onSelectionStart={() => { selAvantLasso.current = selection; }}
        onSelectionEnd={() => {
          const ids = (rfRef.current?.getNodes() || []).filter((n) => n.selected && n.type === "twin").map((n) => n.id);
          if (ids.length) setSelection([...new Set([...selAvantLasso.current, ...ids])]);
        }}
        onNodeClick={(_, node) => {
          if (outil === "lasso") return;
          if (node.type === "region") {
            const label = node.data.label;
            const dc = dernierClicRegion.current;
            dernierClicRegion.current = { kind: "region", label, t: Date.now() };
            if (dc.kind === "region" && dc.label === label && Date.now() - dc.t < 450 && !domaineInterne && !jumeauFocus) {
              entrerDomaine(label);
              return;
            }
            if (attenteComparaison && domaineSel && label !== domaineSel) {
              setComparaison({ a: domaineSel, b: label });
              setAttenteComparaison(false);
            } else {
              setDomaineSel(label);
            }
            majUrl({ domaine: label, sel: null, ...(domaineInterne ? {} : { interne: null }) });
            setSelected(null);
            setSelectedRelation(null);
            setOnglet("detail");
            return;
          }
          if (node.data?.porte) {
            entrerDomaine(node.data.porte);
            return;
          }
          if (node.data?.voisinRel) {
            if (!node.data.jumeau.anonyme) entrerJumeau(node.data.jumeau);
            return;
          }
          if (node.type !== "twin") return;
          const dcT = dernierClicRegion.current;
          dernierClicRegion.current = { kind: "twin", id: node.data.jumeau.id, t: Date.now() };
          if (dcT.kind === "twin" && dcT.id === node.data.jumeau.id && Date.now() - dcT.t < 450 && !jumeauFocus && !node.data.jumeau.anonyme) {
            entrerJumeau(node.data.jumeau);
            return;
          }
          setEpingle((p) => (p === node.data.jumeau.id ? null : node.data.jumeau.id));
          setSelected(node.data.jumeau);
          setSelectedRelation(null);
          setDomaineSel(null);
          setOnglet("detail");
          majUrl({ sel: node.data.jumeau.id, ...(domaineInterne ? {} : { domaine: null, interne: null }) });
        }}
        onNodeDoubleClick={(_, node) => {
          if (outil === "lasso") return;
          if (node.type === "region") {
            if (!domaineInterne && !jumeauFocus) entrerDomaine(node.data.label);
            return;
          }
          if (node.data?.porte) { entrerDomaine(node.data.porte); return; }
          if (node.type === "twin" && node.data?.jumeau && !node.data.jumeau.anonyme && !jumeauFocus) entrerJumeau(node.data.jumeau);
        }}
        onEdgeClick={(_, edge) => {
          const rel = mesh?.relations.find((r) => r.id === edge.id);
          if (!rel) return;
          setSelectedRelation(rel);
          setSelected(null);
          setOnglet("detail");
        }}
        onEdgeMouseEnter={(e, edge) => {
          setRelSurvolee(edge.id);
          const rect = carteRef.current?.getBoundingClientRect();
          if (rect) setRelTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
        }}
        onEdgeMouseLeave={() => { setRelSurvolee(null); setRelTooltipPos(null); }}
        onPaneClick={(e) => {
          // Double-clic sur une zone vide : zoom centré sur le pointeur (façon Google Maps)
          const dcP = dernierClicPane.current;
          dernierClicPane.current = Date.now();
          if (Date.now() - dcP < 420 && rfRef.current && carteRef.current) {
            const rect = carteRef.current.getBoundingClientRect();
            const f = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const vp = rfRef.current.getViewport();
            const z2 = Math.min(vp.zoom * 1.35, 2.6);
            rfRef.current.setViewport({ x: e.clientX - rect.left - f.x * z2, y: e.clientY - rect.top - f.y * z2, zoom: z2 }, { duration: 240 });
          }
          const dc = dernierClicRegion.current;
          dernierClicRegion.current = { kind: null, t: 0 };
          if (Date.now() - dc.t < 450 && rfRef.current && mesh) {
            const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            if (dc.kind === "twin" && !jumeauFocus) {
              const j = mesh.jumeaux.find((x) => x.id === dc.id && !x.anonyme);
              if (j) {
                const pos = posOverrides[j.id] || j.position;
                if (Math.abs(p.x - (pos.x + 30)) < 90 && Math.abs(p.y - (pos.y + 40)) < 85) { entrerJumeau(j); return; }
              }
            }
            if (dc.kind === "region" && !domaineInterne && !jumeauFocus) {
              const reg = (mesh.regions || []).find((r) => r.label === dc.label);
              if (reg && p.x >= reg.x && p.x <= reg.x + reg.w && p.y >= reg.y && p.y <= reg.y + reg.h) {
                entrerDomaine(dc.label);
                return;
              }
            }
          }
          setSelected(null); setSelectedRelation(null); setDomaineSel(null); setSelection([]); setRelFocus(false); setComparaison(null); setAttenteComparaison(false); commanderCarte(null); setEpingle(null);
          majUrl(domaineInterne ? { sel: null } : { sel: null, domaine: null, interne: null, jumeau: null });
        }}
        nodesDraggable={modeEdition}
        nodesConnectable={false}
        colorMode="light"
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.3} color="rgba(17,17,16,0.13)" />
        <Controls showInteractive={false} position="bottom-right" style={{ marginBottom: 128 }}>
          <ControlButton onClick={pleinEcran} title="Plein écran" data-testid="plein-ecran-btn">
            <CornersOut size={14} />
          </ControlButton>
        </Controls>
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          style={{ width: 168, height: 112 }}
          nodeColor={(n) => (n.type === "region" ? `${n.data?.couleur || "#71716D"}66` : couleurDomaine(n.data?.jumeau?.domaine))}
          maskColor="rgba(247,247,246,0.6)"
          data-testid="minimap"
        />
        {/* Étiquettes de domaines — ViewportPortal, à l'intérieur des membranes sans chevaucher les flux */}
        <ViewportPortal>
          {nodes.filter((n) => n.type === "region").map((n) => {
            const d = n.data;
            const m = d.maturite;
            const mc = m ? MATURITES[m.niveau] || "#71716D" : null;
            const sx = d.w / (d.wCible || d.w);
            const sy = d.h / (d.hCible || d.h);
            const lx = n.position.x + (d.labelX ?? d.w / 2) * sx;
            const ly = n.position.y + (d.labelY ?? 30) * sy;
            return (
              <div
                key={n.id}
                className="nopan"
                style={{ position: "absolute", left: lx, top: ly, transform: "translate(-50%, -50%)", pointerEvents: "auto", cursor: "pointer" }}
                title="Clic : sélectionner le domaine · Double-clic : entrer dans le domaine"
                data-testid={`region-header-${d.id}`}
                onClick={() => {
                  setSelected(null);
                  setSelectedRelation(null);
                  setDomaineSel(d.label);
                  setOnglet("detail");
                  majUrl({ domaine: d.label, sel: null, ...(domaineInterne ? {} : { interne: null }) });
                }}
                onDoubleClick={() => { if (!domaineInterne && !jumeauFocus) entrerDomaine(d.label); }}
              >
                <div className="flex flex-col items-center gap-0.5">
                  <div className="flex items-center justify-center gap-2">
                    {d.halo && (
                      <span className="halo-anim h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: d.couleur }} data-testid={`region-activite-${d.id}`} />
                    )}
                    <span className="whitespace-nowrap rounded bg-white/60 px-1.5 py-0.5 font-code text-[11px] font-semibold uppercase tracking-[0.25em] backdrop-blur-[2px]" style={{ color: d.couleur }}>
                      {d.label}
                    </span>
                  </div>
                  {mc && !d.macro && (
                    <span className="rounded-full border bg-white/80 px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider" style={{ color: mc, borderColor: `${mc}44` }}>
                      {m.niveau}
                    </span>
                  )}
                </div>
                {d.macro && m && (
                  <div className="mt-1 flex items-center justify-center gap-2 font-code text-[10px] text-[#52524F]" data-testid={`region-macro-${d.id}`}>
                    <span>{m.jumeaux} jumeau{m.jumeaux > 1 ? "x" : ""}</span>
                    <span className="text-[#71716D]">·</span>
                    <span>{d.flux ?? 0} flux</span>
                    <span className="text-[#71716D]">·</span>
                    <span className={(d.ecarts ?? 0) > 0 ? "text-[#D97706]" : ""}>{d.ecarts ?? 0} écart{(d.ecarts ?? 0) > 1 ? "s" : ""}</span>
                  </div>
                )}
              </div>
            );
          })}
        </ViewportPortal>
      </ReactFlow>

      {/* Marqueurs de flèches partagés par les arêtes orthogonales */}
      <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
          <marker id="marqueur-ardoise" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="rgba(17,17,16,0.5)" />
          </marker>
          <marker id="marqueur-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#0E7490" />
          </marker>
          <marker id="marqueur-orange" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#D97706" />
          </marker>
          <marker id="marqueur-violet" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#6D28D9" />
          </marker>
        </defs>
      </svg>

      {/* Sélecteur de couches de relations + recherche */}
      <div className={`pointer-events-none absolute left-32 top-3 z-10 flex items-start justify-between gap-3 transition-all ${selected || selectedRelation || domaineSel ? "right-[400px]" : "right-24"}`}>
        <div className="glass pointer-events-auto flex items-center gap-1 rounded-xl p-1" data-testid="couches-relations">
          {[
            ["bcm", "BCM déclaré", "rgba(17,17,16,0.45)", "solid"],
            ["realite", "Réalité découverte", "#0E7490", "solid"],
            ["ecarts", "Écarts", "#D97706", "dashed"],
          ].map(([id, label, coul, st]) => (
            <button
              key={id}
              onClick={() => setCouchesRel((c) => ({ ...c, [id]: !c[id] }))}
              data-testid={`couche-rel-${id}`}
              title={label}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 font-code text-[10px] transition-colors ${couchesRel[id] ? "bg-white text-[#111110] shadow-sm" : "text-[#71716D] opacity-50"}`}
            >
              <span className="inline-block w-5 border-t-2" style={{ borderColor: coul, borderTopStyle: st }} />
              {label}
            </button>
          ))}
        </div>
        <div className="pointer-events-auto relative">
          <div className="glass flex items-center gap-2 rounded-xl px-3 py-2">
            <MagnifyingGlass size={13} className="shrink-0 text-[#71716D]" />
            <input
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Rechercher un jumeau, domaine, flux…"
              data-testid="atlas-recherche"
              className="w-60 bg-transparent text-xs text-[#111110] placeholder:text-[#71716D] focus:outline-none"
            />
          </div>
          {resultatsRecherche.length > 0 && (
            <div className="glass absolute right-0 top-11 z-30 w-72 rounded-xl p-1.5" data-testid="atlas-recherche-resultats">
              {resultatsRecherche.map((r) => (
                <button
                  key={`${r.type}-${r.id}`}
                  onClick={() => (r.type === "jumeau" ? centrerSurJumeau(r.id) : (setDomaineSel(r.id), setRecherche("")))}
                  data-testid={`recherche-${r.type}-${r.id}`}
                  className="w-full rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-[#F0F0EE]"
                >
                  <div className="text-xs font-semibold text-[#111110]">{r.label}</div>
                  <div className="font-code text-[9px] text-[#71716D]">{r.sub}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Panneau flottant du jumeau — survol (aperçu) ou épinglé au clic */}
      {jumeauSurvole && statsJumeau && (
        <div
          className={`absolute left-4 top-20 z-20 w-64 rounded-2xl border border-[#E5E5E3] bg-white p-4 shadow-lg ${epingle ? "" : "pointer-events-none"}`}
          data-testid="panneau-jumeau-flottant"
        >
          <div className="flex items-center gap-3">
            <span className={`flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white ${epingle ? "ring-2 ring-[#0E7490]" : "ring-1 ring-black/10"}`}>
              <img src="/assets/robot-jumeau.jpg" alt="" draggable={false} className="h-11 w-11 scale-[1.65] object-cover" />
            </span>
            <div className="min-w-0">
              <div className="font-code text-[10px] font-semibold tracking-wide text-[#71716D]">{idNumerique(jumeauSurvole.id)}</div>
              <div className="truncate font-display text-base font-bold text-[#111110]" data-testid="panneau-jumeau-nom">{jumeauSurvole.nom}</div>
              <div className="font-code text-[9px] uppercase tracking-[0.15em] text-[#71716D]">Jumeau applicatif</div>
            </div>
          </div>
          <dl className="mt-3 space-y-1.5 border-t border-[#F0F0EE] pt-3 text-xs">
            <div className="flex items-center justify-between">
              <dt className="text-[#71716D]">Statut</dt>
              <dd className="font-code font-semibold text-[#111110]" data-testid="panneau-jumeau-statut">{jumeauSurvole.statut}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-[#71716D]">Confiance</dt>
              <dd className="font-code font-semibold text-[#0E7490]" data-testid="panneau-jumeau-confiance">{jumeauSurvole.confiance?.valeur ?? jumeauSurvole.couverture ?? "—"} %</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-[#71716D]">Relations observées</dt>
              <dd className="font-code font-semibold text-[#111110]" data-testid="panneau-jumeau-flux">{statsJumeau.flux}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-[#71716D]">Écarts au BCM</dt>
              <dd className={`font-code font-semibold ${statsJumeau.ecarts > 0 ? "text-[#D97706]" : "text-[#111110]"}`} data-testid="panneau-jumeau-ecarts">{statsJumeau.ecarts}</dd>
            </div>
          </dl>
          <div className="mt-3 space-y-1.5">
            <button
              onClick={() => { setSelection([jumeauSurvole.id]); ouvrirFlore(); }}
              data-testid="panneau-jumeau-interroger"
              className="w-full rounded-lg bg-[#0E7490] px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#155E75]"
            >
              Interroger
            </button>
            <button
              onClick={() => { setSelected(jumeauSurvole); setSelectedRelation(null); setDomaineSel(null); setOnglet("detail"); }}
              data-testid="panneau-jumeau-ouvrir"
              className="w-full rounded-lg border border-[#0E7490]/40 px-3 py-2 text-xs font-semibold text-[#0E7490] transition-colors hover:bg-[#0E7490]/10"
            >
              Ouvrir le jumeau
            </button>
          </div>
          {epingle && (
            <button onClick={() => setEpingle(null)} data-testid="panneau-jumeau-fermer" title="Fermer (Échap)" className="absolute right-2.5 top-2.5 text-[#71716D] transition-colors hover:text-[#111110]">
              <X size={13} />
            </button>
          )}
        </div>
      )}

      <AtlasControle
        mesh={mesh} focus={focus}
        modeTemps={modeTemps} setModeTemps={(m) => { setModeTemps(m); if (m === "direct" || m === "pause") { setReplaying(false); setDateRef(null); } }}
        dateRef={dateRef} setDateRef={setDateRef}
        replaying={replaying} onRejouer={() => setReplaying(true)}
        couches={couches} setCouches={setCouches}
        rechargerVues={rechargerVues}
      />

      <AtlasToolbar outil={outil} setOutil={setOutil} rfRef={rfRef} onExpliquer={() => setExpliquerOuvert((o) => !o)} expliquerOuvert={expliquerOuvert} modeEdition={modeEdition} setModeEdition={setModeEdition} />

      {/* Indicateur du mode réorganisation */}
      {modeEdition && (
        <div className="glass absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-lg px-3 py-1.5" data-testid="mode-edition-chip" style={{ transform: "translateX(-50%) translateY(-28px)" }}>
          <span className="h-1.5 w-1.5 rounded-full bg-[#B45309]" />
          <span className="font-code text-[10px] text-[#52524F]">
            Mode réorganisation — glissez un robot ; la reclassification est toujours proposée, jamais automatique
          </span>
          <button onClick={() => setModeEdition(false)} data-testid="mode-edition-quitter" className="text-[#71716D] transition-colors hover:text-[#111110]">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Position fantôme du robot en cours de déplacement */}
      {fantome && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2"
          style={{ left: fantome.x, top: fantome.y }}
          data-testid="robot-fantome"
        >
          <span className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-dashed border-[#71716D]/50 bg-white/50">
            <img src="/assets/robot-jumeau.jpg" alt="" className="h-10 w-10 scale-[1.65] rounded-full object-cover opacity-35" />
          </span>
        </div>
      )}

      {/* Bandeau temporel — photographie ou avant/après */}
      {(modeTemps === "historique" || modeTemps === "replay") && dateRef && (
        <div className="glass absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-temps">
          <span className="font-code text-[10px] text-[#52524F]">
            {modeTemps === "replay" ? "Relecture du Mesh" : "Photographie du Mesh"} au <strong className="text-[#111110]">{fmtDate(dateRef)}</strong>
          </span>
          <button onClick={() => { setModeTemps("direct"); setReplaying(false); setDateRef(null); majUrl({ date: null }); }} data-testid="retour-direct-btn" className="rounded-md border border-[#3730A3]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#3730A3] transition-colors hover:bg-[#3730A3]/10">
            Revenir au direct
          </button>
        </div>
      )}
      {modeTemps === "avantapres" && dateRef && (
        <div className="glass absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-xl px-4 py-2" data-testid="bandeau-avant-apres">
          <span className="h-2 w-2 rounded-sm border-2 border-dashed border-[#0E7490]" />
          <span className="font-code text-[10px] text-[#52524F]">
            Avant/Après depuis le <strong className="text-[#111110]">{fmtDate(dateRef)}</strong> — {nbNouvelles} nouvelle{nbNouvelles > 1 ? "s" : ""} relation{nbNouvelles > 1 ? "s" : ""}
          </span>
          <button onClick={() => { setModeTemps("direct"); setDateRef(null); }} data-testid="retour-direct-btn-aa" className="rounded-md border border-[#3730A3]/40 px-2 py-0.5 font-code text-[10px] font-semibold text-[#3730A3] transition-colors hover:bg-[#3730A3]/10">
            Revenir au direct
          </button>
        </div>
      )}

      {expliquerOuvert && (
        <ExpliquerCarte
          mesh={mesh}
          fermer={() => setExpliquerOuvert(false)}
          domaineInterne={domaineInterne}
          jumeauFocus={jumeauFocus}
          jumeauPar={jumeauPar}
          selection={selection}
        />
      )}

      {/* Bandeau situation (focus profond depuis Aujourd'hui / Investigations) */}
      {situation && (
        <div className="glass absolute left-1/2 top-4 z-10 flex max-w-md -translate-x-1/2 items-center gap-3 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
          <div>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#6D28D9]">Focus — situation</div>
            <div className="text-xs font-semibold text-[#111110]">{situation.titre}</div>
            <div className="mt-0.5 font-code text-[9px] text-[#71716D]">
              {situation.jumeaux.length} jumeaux · contexte réduit au pertinent
            </div>
          </div>
          <button onClick={() => majUrl({ situation: null })} data-testid="map-clear-situation" title="Retirer le focus situation" className="shrink-0 text-[#71716D] transition-colors hover:text-[#111110]">
            <X size={13} />
          </button>
        </div>
      )}

      <FilAriane
        domaineInterne={domaineInterne} jumeauFocus={jumeauFocus} jumeauPar={jumeauPar}
        historique={historique} indexHist={indexHist} allerHist={allerHist}
        sortirDomaine={sortirDomaine} sortirJumeau={sortirJumeau}
        perimetreTravail={perimetreTravail} selection={selection} revenirSelection={revenirSelection}
      />

      {/* Indicateur de périmètre de travail actif (filtre volontaire, distinct de la sécurité) */}
      {perimetreTravail && perimetreTravail !== domaineInterne && (
        <div className="glass absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2" data-testid="perimetre-travail-chip">
          <span className="h-1.5 w-1.5 rounded-full bg-[#0E7490]" />
          <span className="font-code text-[10px] text-[#52524F]">
            Périmètre de travail : <span style={{ color: couleurDomaine(perimetreTravail) }}>{perimetreTravail}</span> — filtre volontaire, pas sécurité
          </span>
          <button onClick={() => setPerimetreTravail(null)} data-testid="perimetre-travail-clear" className="text-[#71716D] transition-colors hover:text-[#111110]">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Niveau de zoom sémantique */}
      {(
        <div className="glass absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg px-3 py-1.5 font-code text-[10px] text-[#52524F]" data-testid="zoom-niveau">
          {jumeauFocus
            ? `Focus jumeau — ${jumeauPar(jumeauFocus)?.nom} · zoom arrière pour remonter`
            : domaineInterne
              ? `Domaine ${domaineInterne} — zoom arrière pour remonter`
              : `Niveau ${zoomNiveau} · ${NIVEAUX_ZOOM[zoomNiveau]}`}
          {!jumeauFocus && !domaineInterne && zoomNiveau === 1 && " · corridors agrégés"}
          {!jumeauFocus && !domaineInterne && zoomNiveau === 3 && " · détail des relations"}
        </div>
      )}

      <AtlasLegende />

      {/* Infobulle de relation — survol d'une arête, près du pointeur */}
      {relSurvolee?.startsWith("agg-") && !selectedRelation && relTooltipPos && (() => {
        const agg = edges.find((x) => x.id === relSurvolee);
        if (!agg?.data?.agregat) return null;
        return (
          <div
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="agregat-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#111110]">
              {idNumerique(agg.source)} ↔ {idNumerique(agg.target)}
            </div>
            <div className="mt-1.5 font-code text-[10px] text-[#52524F]">
              {agg.data.agregat.length} flux partagent ce corridor
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">Routes déployées au survol</div>
          </div>
        );
      })()}
      {relSurvolee && !relSurvolee.startsWith("agg-") && !selectedRelation && relTooltipPos && mesh && (() => {
        const r = mesh.relations.find((x) => x.id === relSurvolee);
        if (!r) return null;
        const e = edgesVisibles.find((x) => x.id === relSurvolee);
        const etat = ETATS_RELATION[r.etat] || { label: r.etat, couleur: "#71716D" };
        return (
          <div
            className="pointer-events-none absolute z-30 w-56 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
            style={{ left: Math.min(relTooltipPos.x + 14, (carteRef.current?.clientWidth || 1200) - 240), top: Math.max(relTooltipPos.y + 14, 8) }}
            data-testid="relation-tooltip"
          >
            <div className="font-code text-[11px] font-semibold text-[#111110]">
              {idNumerique(r.source)} → {idNumerique(r.cible)}
            </div>
            <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
              <div style={{ color: etat.couleur }}>Relation {etat.label.toLowerCase()}</div>
              {e?.data?.label && <div>{e.data.label}</div>}
              {r.confiance != null && <div>Confiance : {r.confiance} %</div>}
              {(r.claims?.length ?? 0) > 0 && <div>{r.claims.length} preuve{r.claims.length > 1 ? "s" : ""}</div>}
            </div>
            <div className="mt-2 font-code text-[9px] text-[#0E7490]">Clic : qualifier la relation →</div>
          </div>
        );
      })()}

      {/* Infobulle de membrane — proche de la frontière survolée */}
      {regionTooltip && regionSurvolee && (
        <div
          className="pointer-events-none absolute z-30 w-52 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
          style={{ left: Math.min(regionTooltip.x + 16, (carteRef.current?.clientWidth || 1200) - 230), top: Math.max(regionTooltip.y + 16, 8) }}
          data-testid={`region-tooltip-${regionSurvolee.id}`}
        >
          <div className="font-display text-xs font-bold" style={{ color: regionTooltip.data.couleur }}>Domaine {regionTooltip.data.label}</div>
          <div className="mt-1.5 space-y-0.5 font-code text-[10px] text-[#52524F]">
            <div>{regionTooltip.data.maturite?.jumeaux ?? "—"} jumeaux</div>
            <div>{regionTooltip.data.flux ?? 0} flux observés</div>
            <div>{regionTooltip.data.ecarts ?? 0} écart{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""} structurel{(regionTooltip.data.ecarts ?? 0) > 1 ? "s" : ""}</div>
          </div>
          <div className="mt-2 font-code text-[9px] text-[#0E7490]">Double-clic : explorer le domaine →</div>
        </div>
      )}

      {/* Chip « vue commandée par Flore » */}
      {focusCarte && (
        <div className="glass absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="focus-flore-chip">
          <Sparkle size={12} className="text-[#3730A3]" />
          <span className="font-code text-[10px] text-[#52524F]">Vue commandée par Flore</span>
          <button onClick={() => commanderCarte(null)} data-testid="focus-flore-clear" className="text-[#71716D] transition-colors hover:text-[#111110]">
            <X size={12} />
          </button>
        </div>
      )}

      <AtlasPanneau
        onglet={onglet} setOnglet={setOnglet}
        comparaison={comparaison} selectedRelation={selectedRelation}
        selected={selected} domaineSel={domaineSel}
        statsDomaine={statsDomaine} actionsDomaine={actionsDomaine}
        confirmerRelation={confirmerRelation}
        eventsVisibles={eventsVisibles} jumeauPar={jumeauPar}
      />

      {/* Composer cartographique — flottant, repliable, au-dessus de la carte */}
      <div className="pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center" data-testid="atlas-composer-zone">
        <div className="pointer-events-auto w-[min(560px,92%)] opacity-95 transition-opacity hover:opacity-100">
          <ComposerFlore compact flottant placeholder="Interrogez cette carte…" testidPrefix="atlas-composer" />
        </div>
      </div>
    </div>
    </div>
  );
}
