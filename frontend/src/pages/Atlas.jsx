import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls, ControlButton, MiniMap, SelectionMode } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Sparkle, CornersOut, MagnifyingGlass } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
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
import { couleurDomaine } from "@/lib/domaines";
import { parseQuand, finDeJournee, fmtDate } from "@/lib/temps";

const nodeTypes = { twin: TwinNode, region: RegionNode };

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
  const [couchesRel, setCouchesRel] = useState({ bcm: true, realite: true, ecarts: true });
  const [recherche, setRecherche] = useState("");
  const carteRef = useRef(null);
  const [amorce, setAmorce] = useState(0);
  const [mesures, setMesures] = useState({}); // dimensions mesurées par React Flow, réinjectées dans le graphe
  const [regionSurvoleeId, setRegionSurvoleeId] = useState(null); // membrane survolée (proximité frontière)
  const [regionTooltip, setRegionTooltip] = useState(null);
  const [perimetreTravail, setPerimetreTravail] = useState(null);
  const [attenteComparaison, setAttenteComparaison] = useState(false);
  const [comparaison, setComparaison] = useState(null);
  const rfRef = useRef(null);
  const dernierClicRegion = useRef({ kind: null, t: 0 });
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

  const { nodes, edges } = useMemo(() => {
    const g = construireGraphe({
      mesh, situation, focus, vueActive, perimetreTravail,
      jumeauFocus, domaineInterne, posOverrides, compteurs, halo, selection,
      zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps,
    });
    // Conserve les dimensions mesurées par React Flow : le graphe est reconstruit à chaque
    // tick de drag — sans cela les nœuds perdent leur mesure et les arêtes disparaissent.
    const internes = rfRef.current?.getNodes?.() || [];
    const parId = new Map(internes.map((n) => [n.id, n]));
    g.nodes = g.nodes.map((n) => {
      if (n.type === "region" && n.data.id === regionSurvoleeId) n = { ...n, data: { ...n.data, survol: true } };
      const a = parId.get(n.id);
      const dim = mesures[n.id];
      const base = a?.measured ? { ...n, measured: a.measured, dragging: a.dragging || undefined } : n;
      return dim ? { ...base, width: dim.width, height: dim.height, measured: { width: dim.width, height: dim.height } } : base;
    });
    return g;
  }, [mesh, focus, situation, halo, compteurs, selection, relFocus, zoomNiveau, vueActive, posOverrides, domaineSel, domaineInterne, jumeauFocus, perimetreTravail, domDe, statsRegions, focusCarte, temps, amorce, mesures, regionSurvoleeId]);

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
          : { ...e, label: undefined, style: { ...e.style, opacity: 0.12 } }
      );
    }
    return es;
  }, [edges, couchesRel, epingle, survolJumeau]);

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

  // Échap ferme la sélection épinglée
  useEffect(() => {
    const h = (e) => { if (e.key === "Escape") setEpingle(null); };
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

  // Survol des membranes par proximité de la frontière (les zones d'interaction des arêtes les recouvrent)
  const surSurvolCarte = (e) => {
    if (!rfRef.current || !mesh || jumeauFocus) return;
    const rect = carteRef.current?.getBoundingClientRect();
    if (!rect) return;
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
      if (regionSurvoleeId !== trouve.data.id) setRegionSurvoleeId(trouve.data.id);
      setRegionTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, data: trouve.data });
    } else if (regionSurvoleeId) {
      setRegionSurvoleeId(null);
      setRegionTooltip(null);
    }
  };

  const centrerSurJumeau = (id) => {
    const j = mesh?.jumeaux.find((x) => x.id === id);
    if (!j) return;
    const pos = posOverrides[id] || j.position;
    setEpingle(id);
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
    <div ref={carteRef} onPointerMove={surSurvolCarte} onPointerLeave={() => { setRegionSurvoleeId(null); setRegionTooltip(null); }} className="relative min-h-0 flex-1 overflow-hidden" data-testid="system-map" style={{ background: "radial-gradient(ellipse at 50% 38%, #FDFDFB 0%, #F5F4F0 65%, #EDECE6 100%)" }}>
      <ReactFlow
        key={focus || situationParam || "mesh"}
        nodes={nodes}
        edges={edgesVisibles}
        nodeTypes={nodeTypes}
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
        onMove={onMove}
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
        onPaneClick={(e) => {
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
        nodesDraggable
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
      </ReactFlow>

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

      <AtlasToolbar outil={outil} setOutil={setOutil} rfRef={rfRef} onExpliquer={() => setExpliquerOuvert((o) => !o)} expliquerOuvert={expliquerOuvert} />

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
              : `Niveau ${zoomNiveau} — ${NIVEAUX_ZOOM[zoomNiveau]}`}
          {!jumeauFocus && !domaineInterne && zoomNiveau === 1 && " · corridors agrégés"}
          {!jumeauFocus && !domaineInterne && zoomNiveau === 3 && " · détail des relations"}
        </div>
      )}

      <AtlasLegende />

      {/* Infobulle de membrane — proche de la frontière survolée */}
      {regionTooltip && regionSurvoleeId && (
        <div
          className="pointer-events-none absolute z-30 w-52 rounded-xl border border-[#E5E5E3] bg-white p-3 shadow-lg"
          style={{ left: Math.min(regionTooltip.x + 16, (carteRef.current?.clientWidth || 1200) - 230), top: Math.max(regionTooltip.y + 16, 8) }}
          data-testid={`region-tooltip-${regionSurvoleeId}`}
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
    </div>

    {/* Composer compact — place réservée dans le layout, jamais flottant au-dessus de la carte */}
    <div className="shrink-0 border-t border-[#E5E5E3] bg-white px-4 py-2.5" data-testid="atlas-composer-zone">
      <div className="mx-auto max-w-3xl">
        <ComposerFlore compact placeholder="Interrogez cette carte…" testidPrefix="atlas-composer" />
      </div>
    </div>
    </div>
  );
}
