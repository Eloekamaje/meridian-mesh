import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls, SelectionMode } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Hand, Lasso, Path, Crosshair, Pulse, Pause, X, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
import { couleurDomaine, DOMAINES, NATURES_EVENEMENT, ETATS_RELATION } from "@/lib/domaines";

const nodeTypes = { twin: TwinNode, region: RegionNode };

const MODES = [
  { id: "territoire", label: "Territoire", question: "Comment le SI est-il organisé ?" },
  { id: "situation", label: "Situation", question: "Que se passe-t-il ici ?" },
  { id: "parcours", label: "Parcours", question: "Comment cette activité fonctionne-t-elle ?" },
];

const COUCHES = [
  ["operationnelle", "Opérationnelle", "#3B82F6"],
  ["connaissance", "Connaissance", "#22D3EE"],
  ["mesh", "Mesh", "#A78BFA"],
];

const NIVEAUX_ZOOM = { 1: "Entreprise", 2: "Domaine", 3: "Jumeau" };

const styleParEtat = (r) => {
  switch (r.etat) {
    case "observee":
      return { stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 };
    case "supposee":
      return { stroke: "#22D3EE", strokeWidth: 1.3, strokeDasharray: "4 5", opacity: 0.75 };
    case "validation":
      return { stroke: "#A78BFA", strokeWidth: 1.8, strokeDasharray: "8 6" };
    case "contestee":
      return { stroke: "#F87171", strokeWidth: 1.8, strokeDasharray: "12 3 3 3" };
    case "obsolete":
      return { stroke: "rgba(255,255,255,0.3)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.22 };
    default:
      return { stroke: r.active ? "#3B82F6" : "rgba(255,255,255,0.4)", strokeWidth: 1.5, opacity: r.active ? 0.9 : 0.5 };
  }
};

const makeEdge = (r, niveau) => ({
  id: r.id,
  source: r.source,
  target: r.cible,
  animated: !!r.active || r.etat === "validation",
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
  labelStyle: { fill: r.etat === "validation" ? "#A78BFA" : r.etat === "contestee" ? "#F87171" : "rgba(255,255,255,0.55)", fontSize: 10, fontFamily: "IBM Plex Mono" },
  labelBgStyle: { fill: "rgba(5,5,5,0.85)" },
});

export default function Atlas() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { mesh, jumeauPar, recharger } = useMesh();
  const { version, vueActive, rechargerVues } = usePerimetre();
  const [situations, setSituations] = useState([]);
  const modeParam = searchParams.get("mode");
  const [mode, setMode] = useState(modeParam || "territoire");
  const [situationId, setSituationId] = useState(searchParams.get("situation") || "sit-relation-emergente");
  const [parcoursId, setParcoursId] = useState("parcours-paiement");
  const focus = searchParams.get("focus");
  const [selected, setSelected] = useState(null);
  const [selectedRelation, setSelectedRelation] = useState(null);
  const [events, setEvents] = useState([]);
  const [halo, setHalo] = useState(null);
  const [compteurs, setCompteurs] = useState({});
  const [onglet, setOnglet] = useState("chrono");
  const [couches, setCouches] = useState({ operationnelle: true, connaissance: true, mesh: true });
  const [direct, setDirect] = useState(true);
  const [outil, setOutil] = useState("deplacement");
  const { selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte } = useContexte();
  const [relFocus, setRelFocus] = useState(false);
  const [zoomNiveau, setZoomNiveau] = useState(2);
  const [nomVue, setNomVue] = useState("");
  const [posOverrides, setPosOverrides] = useState({});
  const [domaineInterne, setDomaineInterne] = useState(null);
  const [porteFocus, setPorteFocus] = useState(null);
  const [perimetreTravail, setPerimetreTravail] = useState(null);
  const [attenteComparaison, setAttenteComparaison] = useState(false);
  const [comparaison, setComparaison] = useState(null);
  const rfRef = useRef(null);
  const dernierClicRegion = useRef({ label: null, t: 0 });
  const restaure = useRef(false);
  const selAvantLasso = useRef([]);

  const majUrl = useCallback((updates) => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      Object.entries(updates).forEach(([k, v]) => (v == null ? p.delete(k) : p.set(k, v)));
      return p;
    }, { replace: true });
  }, [setSearchParams]);

  const domDe = useMemo(() => {
    const m = {};
    (mesh?.jumeaux || []).forEach((j) => { m[j.id] = j.domaine; });
    return m;
  }, [mesh]);

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

  const entrerDomaine = useCallback((label) => {
    setDomaineInterne(label);
    setDomaineSel(label);
    setPorteFocus(null);
    setRelFocus(false);
    majUrl({ domaine: label, interne: "1", sel: null });
    const reg = mesh?.regions?.find((r) => r.label === label);
    if (reg && rfRef.current) {
      const ray = Math.max(reg.w, reg.h) / 2 + 130;
      const cx = reg.x + reg.w / 2;
      const cy = reg.y + reg.h / 2;
      rfRef.current.fitBounds({ x: cx - ray - 120, y: cy - ray - 120, width: 2 * (ray + 120), height: 2 * (ray + 120) }, { duration: 800 });
    }
  }, [mesh, majUrl]);

  const sortirDomaine = useCallback(() => {
    setDomaineInterne(null);
    setPorteFocus(null);
    majUrl({ interne: null });
    rfRef.current?.fitView({ duration: 800, padding: 0.15 });
  }, [majUrl]);

  const statsDomaine = useCallback((label) => {
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
  }, [mesh, situations, domDe]);

  const onNodesChange = useCallback((changes) => {
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
    if (modeParam) setMode(modeParam);
  }, [modeParam]);

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

  const situation = situations.find((s) => s.id === situationId);

  const { nodes, edges } = useMemo(() => {
    if (!mesh) return { nodes: [], edges: [] };
    const implique = situation?.jumeaux || [];
    const parcours = (mesh.parcours || []).find((p) => p.id === parcoursId);

    const dims = new Set();
    if (focus) {
      const deps = new Set([focus]);
      mesh.relations.forEach((r) => {
        if (r.source === focus && r.active) deps.add(r.cible);
        if (r.cible === focus && r.active) deps.add(r.source);
      });
      mesh.jumeaux.forEach((j) => { if (!deps.has(j.id)) dims.add(j.id); });
    } else if (mode === "situation" && implique.length) {
      mesh.jumeaux.forEach((j) => { if (!implique.includes(j.id)) dims.add(j.id); });
    }
    if (vueActive?.type === "selection") {
      mesh.jumeaux.forEach((j) => { if (!j.anonyme && !vueActive.jumeaux.includes(j.id)) dims.add(j.id); });
    }
    if (vueActive?.type === "vigilance") {
      mesh.jumeaux.forEach((j) => { if ((j.couverture ?? 100) >= 70) dims.add(j.id); });
    }
    if (perimetreTravail && mode === "territoire") {
      mesh.jumeaux.forEach((j) => { if (!j.anonyme && j.domaine !== perimetreTravail) dims.add(j.id); });
    }

    // Vue interne d'un domaine : jumeaux du domaine + portes externes
    if (mode === "territoire" && domaineInterne) {
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
      let nsInt = reg
        ? [{ id: reg.id, type: "region", position: { x: reg.x, y: reg.y }, initialWidth: reg.w, initialHeight: reg.h, data: { ...reg, investigations: statsRegions[reg.label]?.investigations ?? 0, decouvertes: statsRegions[reg.label]?.decouvertes ?? 0, halo: false }, draggable: false, selectable: false, zIndex: -10 }]
        : [];
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
          initialWidth: 190,
          initialHeight: 70,
          data: { jumeau: { id: pid, nom: `Vers ${dom} · ${extCount[dom].n} relation${extCount[dom].n > 1 ? "s" : ""}`, domaine: dom, porte: true, statut: "porte" }, porte: dom, dim: porteFocus && porteFocus !== dom },
          draggable: false,
          selectable: false,
        });
      });
      nsInt = nsInt.concat(
        internes.map((j) => ({
          id: j.id,
          type: "twin",
          position: posOverrides[j.id] || j.position,
          initialWidth: 190,
          initialHeight: 64,
          data: { jumeau: j, dim: false, halo: halo === j.id, evenements: compteurs[j.id] || 0, etape: null },
          selected: selection.includes(j.id),
        }))
      );
      const esInt = [];
      mesh.relations.forEach((r) => {
        const a = domDe[r.source] === domaineInterne;
        const b = domDe[r.cible] === domaineInterne;
        if (a && b) {
          esInt.push(makeEdge(r, zoomNiveau));
        } else if (a !== b) {
          const ext = a ? domDe[r.cible] : domDe[r.source];
          const pid = porteIds[ext];
          if (!pid) return;
          const e = makeEdge({ ...r, id: `${r.id}-porte`, source: a ? r.source : r.cible, cible: pid }, zoomNiveau);
          if (porteFocus && porteFocus !== ext) e.style = { ...e.style, opacity: 0.12 };
          esInt.push(e);
        }
      });
      return { nodes: nsInt, edges: esInt };
    }

    // Focus contextuel : sélection → voisins éclairés, reste translucide
    if (selection.length > 0 && mode === "territoire" && !focus) {
      const voisins = new Set(selection);
      mesh.relations.forEach((r) => {
        if (selection.includes(r.source)) voisins.add(r.cible);
        if (selection.includes(r.cible)) voisins.add(r.source);
      });
      mesh.jumeaux.forEach((j) => { if (!voisins.has(j.id)) dims.add(j.id); });
    }

    let ns = [];
    if (mode === "territoire") {
      ns = (mesh.regions || []).map((r) => ({
        id: r.id, type: "region", position: { x: r.x, y: r.y },
        initialWidth: r.w,
        initialHeight: r.h,
        data: { ...r, investigations: statsRegions[r.label]?.investigations ?? 0, decouvertes: statsRegions[r.label]?.decouvertes ?? 0, halo: !!halo && domDe[halo] === r.label },
        draggable: false, selectable: false, zIndex: -10,
      }));
    }

    let twins = mesh.jumeaux;
    if (mode === "parcours" && parcours) {
      twins = mesh.jumeaux.filter((j) => parcours.etapes.includes(j.id));
    }

    const entreprise = mode === "territoire" && zoomNiveau === 1;

    ns = ns.concat(
      twins.map((j) => {
        const etape = mode === "parcours" && parcours ? parcours.etapes.indexOf(j.id) + 1 : null;
        const position = posOverrides[j.id] || (etape ? { x: (etape - 1) * 250, y: 280 + (etape % 2) * 46 } : j.position);
        return {
          id: j.id,
          type: "twin",
          position,
          initialWidth: 190,
          initialHeight: 64,
          hidden: entreprise && !j.anonyme ? true : entreprise,
          data: { jumeau: j, dim: dims.has(j.id), halo: halo === j.id, evenements: compteurs[j.id] || 0, etape },
          selected: selection.includes(j.id),
        };
      })
    );

    let es = [];
    if (entreprise) {
      // Zoom Entreprise : corridors agrégés inter-domaines
      const domDe = {};
      mesh.jumeaux.forEach((j) => { domDe[j.id] = j.domaine; });
      const regParDom = {};
      (mesh.regions || []).forEach((r) => { regParDom[r.label] = r.id; });
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
      es = Object.values(corridors).map((c) => ({
        id: `corridor-${c.a}-${c.b}`,
        source: regParDom[c.a],
        target: regParDom[c.b],
        animated: c.actif,
        style: { stroke: "rgba(255,255,255,0.28)", strokeWidth: 2.5, opacity: 0.8 },
        label: `${c.a} ↔ ${c.b} · ${c.n} relation${c.n > 1 ? "s" : ""}${c.actif ? " · activité élevée" : ""}`,
        labelStyle: { fill: "rgba(255,255,255,0.65)", fontSize: 10, fontFamily: "IBM Plex Mono" },
        labelBgStyle: { fill: "rgba(5,5,5,0.85)" },
      }));
    } else if (mode === "parcours" && parcours) {
      es = parcours.etapes.slice(1).map((id, i) =>
        makeEdge({ id: `p-${i}`, source: parcours.etapes[i], cible: id, active: true, etat: "confirmee" }, zoomNiveau)
      );
    } else {
      es = mesh.relations
        .filter((r) => (mode === "situation" && implique.length ? implique.includes(r.source) && implique.includes(r.cible) : true))
        .filter((r) => !focus || r.source === focus || r.cible === focus)
        .map((r) => makeEdge(r, zoomNiveau));
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
    return { nodes: ns, edges: es };
  }, [mesh, mode, situationId, parcoursId, focus, halo, compteurs, selection, relFocus, zoomNiveau, situation, vueActive, posOverrides, domaineSel, domaineInterne, porteFocus, perimetreTravail, domDe, statsRegions, focusCarte]);

  const eventsVisibles = events.filter((e) => couches[e.dynamique || "operationnelle"]);
  const modeInfo = MODES.find((m) => m.id === mode);

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

  const outils = [
    { id: "deplacement", icon: Hand, label: "Déplacement" },
    { id: "lasso", icon: Lasso, label: "Sélection multiple / lasso" },
    { id: "parcours", icon: Path, label: "Explorer un parcours" },
    { id: "recentrage", icon: Crosshair, label: "Recentrage" },
  ];

  return (
    <div className="relative h-full w-full overflow-hidden" data-testid="system-map">
      <ReactFlow
        key={`${mode}-${situationId}-${parcoursId}-${focus || ""}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        maxZoom={2.2}
        zoomOnDoubleClick={false}
        onInit={(inst) => { rfRef.current = inst; }}
        onMove={(_, vp) => setZoomNiveau(vp.zoom < 0.6 ? 1 : vp.zoom > 1.15 ? 3 : 2)}
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
            dernierClicRegion.current = { label, t: Date.now() };
            if (dc.label === label && Date.now() - dc.t < 450 && !domaineInterne) {
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
            setPorteFocus((p) => (p === node.data.porte ? null : node.data.porte));
            setOnglet("detail");
            return;
          }
          if (node.type !== "twin") return;
          setSelected(node.data.jumeau);
          setSelectedRelation(null);
          setDomaineSel(null);
          setOnglet("detail");
          majUrl({ sel: node.data.jumeau.id, ...(domaineInterne ? {} : { domaine: null, interne: null }) });
        }}
        onNodeDoubleClick={(_, node) => {
          if (outil === "lasso") return;
          if (node.type === "region") entrerDomaine(node.data.label);
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
          dernierClicRegion.current = { label: null, t: 0 };
          if (!domaineInterne && dc.label && Date.now() - dc.t < 450 && rfRef.current && mesh) {
            const p = rfRef.current.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const reg = (mesh.regions || []).find((r) => r.label === dc.label);
            if (reg && p.x >= reg.x && p.x <= reg.x + reg.w && p.y >= reg.y && p.y <= reg.y + reg.h) {
              entrerDomaine(dc.label);
              return;
            }
          }
          setSelected(null); setSelectedRelation(null); setDomaineSel(null); setSelection([]); setRelFocus(false); setComparaison(null); setAttenteComparaison(false); commanderCarte(null);
          majUrl(domaineInterne ? { sel: null } : { sel: null, domaine: null, interne: null });
        }}
        nodesDraggable={mode === "territoire"}
        nodesConnectable={false}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="rgba(255,255,255,0.05)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>

      {/* Panneau de contrôle haut-gauche */}
      <div className="glass absolute left-4 top-4 z-10 rounded-xl p-3" data-testid="map-mode-switcher">
        <div className="flex gap-1">
          {MODES.map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              data-testid={`map-mode-${m.id}`}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors duration-200 ${
                mode === m.id ? "bg-[#3B82F6] text-white" : "text-white/55 hover:bg-white/[0.06] hover:text-white"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="mt-2 px-1 font-code text-[10px] text-white/40">{modeInfo?.question}</p>

        {mode === "situation" && (
          <select
            value={situationId}
            onChange={(e) => setSituationId(e.target.value)}
            data-testid="map-situation-select"
            className="mt-2 w-full rounded-md border border-white/10 bg-black/60 px-2 py-1.5 text-xs text-white focus:outline-none"
          >
            {situations.filter((s) => (s.jumeaux || []).length > 0).map((s) => (
              <option key={s.id} value={s.id} label={s.titre} />
            ))}
          </select>
        )}
        {mode === "parcours" && (
          <select
            value={parcoursId}
            onChange={(e) => setParcoursId(e.target.value)}
            data-testid="map-parcours-select"
            className="mt-2 w-full rounded-md border border-white/10 bg-black/60 px-2 py-1.5 text-xs text-white focus:outline-none"
          >
            {(mesh?.parcours || []).map((p) => (
              <option key={p.id} value={p.id} label={p.nom} />
            ))}
          </select>
        )}
        {focus && (
          <Link to="/atlas" className="mt-2 block px-1 font-code text-[10px] text-[#3B82F6] hover:underline" data-testid="map-clear-focus">
            ← Retirer le filtre « {focus} »
          </Link>
        )}

        {mesh?.perimetre?.nb_restreints > 0 && (
          <div className="mt-2 rounded border border-dashed border-white/15 px-2 py-1.5 font-code text-[9px] leading-relaxed text-white/45" data-testid="badge-dependances-restreintes">
            {mesh.perimetre.nb_restreints} dépendance(s) restreinte(s) — politique « {mesh.perimetre.politique === "anonymisee" ? "dépendance anonymisée" : mesh.perimetre.politique === "resume" ? "résumé autorisé" : "masquage complet"} »
          </div>
        )}

        {/* Direct / Pause */}
        <div className="mt-3 flex items-center gap-1 border-t border-white/[0.08] pt-2.5">
          <span className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Temps réel</span>
          <button
            onClick={() => setDirect(true)}
            data-testid="direct-btn"
            className={`flex items-center gap-1 rounded px-2 py-1 font-code text-[10px] transition-colors ${direct ? "bg-[#10B981]/15 text-[#10B981]" : "text-white/45 hover:text-white"}`}
          >
            <Pulse size={12} /> Direct
          </button>
          <button
            onClick={() => setDirect(false)}
            data-testid="pause-btn"
            className={`flex items-center gap-1 rounded px-2 py-1 font-code text-[10px] transition-colors ${!direct ? "bg-[#F59E0B]/15 text-[#F59E0B]" : "text-white/45 hover:text-white"}`}
          >
            <Pause size={12} /> Pause
          </button>
        </div>

        <div className="mt-2.5 border-t border-white/[0.08] pt-2.5">
          <div className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Dynamiques visibles</div>
          <div className="mt-1.5 space-y-1">
            {COUCHES.map(([id, label, c]) => (
              <label key={id} className="flex cursor-pointer items-center gap-2 px-1 py-0.5" data-testid={`couche-${id}`}>
                <input
                  type="checkbox"
                  checked={couches[id]}
                  onChange={(e) => setCouches({ ...couches, [id]: e.target.checked })}
                  className="h-3 w-3"
                  style={{ accentColor: c }}
                />
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} />
                <span className="text-[11px] text-white/60">{label}</span>
              </label>
            ))}
          </div>
        </div>

        {mode === "territoire" && !mesh?.perimetre?.global && (
          <div className="mt-2 flex gap-1.5 px-1">
            <input
              value={nomVue}
              onChange={(e) => setNomVue(e.target.value)}
              placeholder="Nom de la vue…"
              data-testid="nom-vue-input"
              className="h-7 w-full rounded border border-white/10 bg-black/50 px-2 text-[11px] text-white placeholder:text-white/25 focus:outline-none"
            />
            <button
              onClick={async () => {
                if (!nomVue.trim()) return;
                try {
                  await api.post("/vues", { nom: nomVue.trim(), type: "selection", jumeaux: (mesh?.jumeaux || []).filter((j) => !j.anonyme).map((j) => j.id) });
                  setNomVue("");
                  rechargerVues();
                  toast.success("Vue enregistrée — disponible dans le sélecteur de périmètre");
                } catch {
                  toast.error("Enregistrement impossible");
                }
              }}
              data-testid="enregistrer-vue-btn"
              className="h-7 shrink-0 rounded border border-white/15 px-2 text-[10px] text-white/60 transition-colors hover:border-white/40 hover:text-white"
            >
              Enregistrer
            </button>
          </div>
        )}
      </div>

      {/* Barre d'outils cartographique gauche */}
      <div className="glass absolute left-4 top-1/2 z-10 flex -translate-y-1/2 flex-col gap-1 rounded-xl p-1.5" data-testid="map-toolbar">
        {outils.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            title={label}
            data-testid={`outil-${id}`}
            onClick={() => {
              if (id === "recentrage") {
                rfRef.current?.fitView({ duration: 600, padding: 0.15 });
                return;
              }
              if (id === "parcours") {
                setMode("parcours");
                return;
              }
              setOutil(id);
            }}
            className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
              outil === id && id !== "recentrage" && id !== "parcours"
                ? "bg-[#22D3EE]/15 text-[#22D3EE]"
                : "text-white/45 hover:bg-white/[0.06] hover:text-white"
            }`}
          >
            <Icon size={16} />
          </button>
        ))}
      </div>

      {/* Bandeau situation */}
      {mode === "situation" && situation && (
        <div className="glass absolute left-1/2 top-4 z-10 max-w-md -translate-x-1/2 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
          <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#A78BFA]">Focus — situation</div>
          <div className="text-xs font-semibold text-white">{situation.titre}</div>
          <div className="mt-0.5 font-code text-[9px] text-white/40">
            {situation.jumeaux.length} jumeaux · contexte réduit au pertinent
          </div>
        </div>
      )}

      {/* Fil d'Ariane domaine */}
      {domaineInterne && (
        <div className="glass absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2" data-testid="breadcrumb">
          <button onClick={sortirDomaine} className="text-xs text-white/50 transition-colors hover:text-white" data-testid="breadcrumb-mesh">
            Mesh global
          </button>
          <span className="text-white/30">›</span>
          <span className="text-xs font-semibold text-white">Domaine {domaineInterne}</span>
          {perimetreTravail === domaineInterne && (
            <span className="rounded-full border border-[#22D3EE]/40 bg-[#22D3EE]/10 px-2 py-0.5 font-code text-[9px] text-[#22D3EE]">
              périmètre de travail (filtre, pas sécurité)
            </span>
          )}
        </div>
      )}

      {/* Indicateur de périmètre de travail actif (filtre volontaire, distinct de la sécurité) */}
      {perimetreTravail && perimetreTravail !== domaineInterne && (
        <div className="glass absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2" data-testid="perimetre-travail-chip">
          <span className="h-1.5 w-1.5 rounded-full bg-[#22D3EE]" />
          <span className="font-code text-[10px] text-white/60">
            Périmètre de travail : <span style={{ color: couleurDomaine(perimetreTravail) }}>{perimetreTravail}</span> — filtre volontaire, pas sécurité
          </span>
          <button onClick={() => setPerimetreTravail(null)} data-testid="perimetre-travail-clear" className="text-white/40 transition-colors hover:text-white">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Niveau de zoom sémantique */}
      {mode === "territoire" && (
        <div className="glass absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg px-3 py-1.5 font-code text-[10px] text-white/50" data-testid="zoom-niveau">
          Niveau {zoomNiveau} — {NIVEAUX_ZOOM[zoomNiveau]}
          {zoomNiveau === 1 && " · corridors agrégés"}
          {zoomNiveau === 3 && " · détail des relations"}
        </div>
      )}

      {/* Légende : états des relations */}
      <div className="glass absolute bottom-4 left-4 z-10 max-w-[400px] rounded-lg px-3 py-2" data-testid="map-legend">
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(ETATS_RELATION).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-white/50">
              <span
                className="inline-block h-0 w-4 border-t-2"
                style={{
                  borderColor: v.couleur,
                  borderStyle: ["supposee", "validation", "obsolete"].includes(k) ? "dashed" : k === "contestee" ? "dotted" : "solid",
                }}
              />
              {v.label}
            </span>
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 border-t border-white/[0.06] pt-1.5">
          {Object.entries(DOMAINES).filter(([d]) => d !== "Non classé").map(([d, c]) => (
            <span key={d} className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-white/40">
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} /> {d}
            </span>
          ))}
        </div>
      </div>

      {/* Chip « vue commandée par Aurora » */}
      {focusCarte && (
        <div className="glass absolute bottom-16 left-4 z-10 flex items-center gap-2 rounded-lg px-3 py-1.5" data-testid="focus-aurora-chip">
          <Sparkle size={12} className="text-[#3B82F6]" />
          <span className="font-code text-[10px] text-white/55">Vue commandée par Aurora</span>
          <button onClick={() => commanderCarte(null)} data-testid="focus-aurora-clear" className="text-white/40 transition-colors hover:text-white">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Panneau latéral droit */}
      <aside className="glass absolute right-4 top-4 z-10 flex max-h-[calc(100%-6rem)] w-80 flex-col overflow-hidden rounded-xl" data-testid="map-side-panel">
        <div className="flex border-b border-white/[0.08]">
          {[["detail", "Détail"], ["chrono", "Chronologie"]].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setOnglet(id)}
              data-testid={`map-tab-${id}`}
              className={`flex-1 px-3 py-2.5 font-code text-[10px] uppercase tracking-[0.2em] transition-colors ${
                onglet === id ? "bg-white/[0.06] text-white" : "text-white/40 hover:text-white/70"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {onglet === "detail" ? (
            comparaison ? (
              <ComparaisonDomaines a={comparaison.a} b={comparaison.b} statsDomaine={statsDomaine} />
            ) : porteFocus && domaineInterne ? (
              <PorteDetail interne={domaineInterne} externe={porteFocus} mesh={mesh} domDe={domDe} />
            ) : selectedRelation ? (
              <RelationDetail rel={selectedRelation} jumeauPar={jumeauPar} onConfirmer={confirmerRelation} />
            ) : selected ? (
              <TwinDetail selected={selected} />
            ) : domaineSel ? (
              <DomaineDetail
                label={domaineSel}
                stats={statsDomaine(domaineSel)}
                actions={{
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
                }}
              />
            ) : (
              <p className="text-xs text-white/35">
                Sélectionnez un jumeau, une relation ou un domaine. Double-clic sur un domaine pour y entrer ; le zoom révèle progressivement le contenu.
              </p>
            )
          ) : (
            <ul className="space-y-3" data-testid="map-chrono-list">
              {eventsVisibles.map((e) => {
                const j = jumeauPar(e.jumeau);
                const c = NATURES_EVENEMENT[e.nature] || "#6B7280";
                const dyn = COUCHES.find(([id]) => id === (e.dynamique || "operationnelle"));
                return (
                  <li key={e.uid} className="ticker-item flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span>
                        {dyn && <span className="font-code text-[8px] uppercase tracking-wider text-white/25">{dyn[1]}</span>}
                      </div>
                      <p className="text-xs leading-snug text-white/55">{e.texte}</p>
                    </div>
                  </li>
                );
              })}
              {eventsVisibles.length === 0 && <li className="text-xs text-white/30">Aucun événement sur les dynamiques visibles.</li>}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}

function RelationDetail({ rel, jumeauPar, onConfirmer }) {
  const etat = ETATS_RELATION[rel.etat] || ETATS_RELATION.confirmee;
  const s = jumeauPar(rel.source);
  const c = jumeauPar(rel.cible);
  return (
    <div data-testid="map-relation-detail">
      <span
        className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
        style={{ color: etat.couleur, borderColor: `${etat.couleur}55`, backgroundColor: `${etat.couleur}12` }}
      >
        {etat.label}
      </span>
      <h3 className="mt-2 font-display text-base font-bold text-white">
        {s?.nom || rel.source} → {c?.nom || rel.cible}
      </h3>
      {rel.confiance && <div className="mt-1 font-code text-[11px] text-white/60">confiance {rel.confiance} %</div>}

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex justify-between gap-2"><dt className="text-white/40">Découverte</dt><dd className="text-right text-white/80">{rel.decouverte_quand || "—"}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-white/40">Source</dt><dd className="text-right text-white/80">{rel.source_decouverte || "—"}</dd></div>
      </dl>

      {(rel.confirmee_par || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Confirmée par</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rel.confirmee_par.map((p, i) => (
              <span key={i} className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] text-white/70">{p}</span>
            ))}
          </div>
        </div>
      )}

      {(rel.claims || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Claims associés</div>
          <ul className="mt-1 space-y-1">
            {rel.claims.map((cl, i) => <li key={i} className="text-xs text-white/60">→ {cl}</li>)}
          </ul>
        </div>
      )}

      {(rel.observations_contraires || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#F87171]/70">Observations contraires</div>
          <ul className="mt-1 space-y-1">
            {rel.observations_contraires.map((o, i) => <li key={i} className="text-xs text-white/60">≠ {o}</li>)}
          </ul>
        </div>
      )}

      {(rel.evolution || []).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Évolution</div>
          <ul className="mt-1 space-y-1">
            {rel.evolution.map((ev, i) => (
              <li key={i} className="font-code text-[10px] text-white/50">{ev.quand} — <span className="text-white/80">{ev.etat}</span></li>
            ))}
          </ul>
        </div>
      )}

      {rel.etat !== "confirmee" && (
        <button
          onClick={() => onConfirmer(rel)}
          data-testid="confirmer-relation-btn"
          className="mt-4 w-full rounded-md bg-[#FBBF24] px-3 py-2 text-xs font-semibold text-black transition-colors hover:bg-[#E5A910]"
        >
          Confirmer la relation — enrichir la mémoire
        </button>
      )}
    </div>
  );
}

function DomaineDetail({ label, stats, actions }) {
  if (!stats) return null;
  const m = stats.reg?.maturite;
  return (
    <div data-testid="domaine-detail">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(label) }} />
        <h3 className="font-display text-base font-bold text-white">Domaine {label}</h3>
      </div>
      {m && <div className="mt-1 font-code text-[10px] text-white/45">{m.niveau} · {m.zones_inconnues} zone(s) inconnue(s)</div>}
      {actions && (
        <div className="mt-3 space-y-1.5" data-testid="domaine-actions">
          {actions.dedans ? (
            <button onClick={actions.onQuitter} data-testid="dom-quitter-btn" className="w-full rounded-md border border-white/15 px-3 py-2 text-xs text-white/70 transition-colors hover:text-white">
              Quitter le domaine
            </button>
          ) : (
            <button onClick={actions.onExplorer} data-testid="dom-explorer-btn" className="w-full rounded-md bg-[#22D3EE] px-3 py-2 text-xs font-semibold text-black transition-colors hover:bg-[#17B8D4]">
              Explorer ce domaine
            </button>
          )}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={actions.onComparer} data-testid="dom-comparer-btn" className="flex-1 rounded-md border border-white/15 px-2 py-1.5 text-[11px] text-white/70 transition-colors hover:text-white">
              Comparer…
            </button>
            <button onClick={actions.onEnregistrer} data-testid="dom-enregistrer-btn" className="flex-1 rounded-md border border-white/15 px-2 py-1.5 text-[11px] text-white/70 transition-colors hover:border-[#10B981]/50 hover:text-[#10B981]">
              Enregistrer comme espace
            </button>
          </div>
          <button
            onClick={actions.onPerimetre}
            data-testid="dom-perimetre-btn"
            className={`w-full rounded-md border px-3 py-2 text-xs font-semibold transition-colors ${actions.perimetre ? "border-[#22D3EE]/60 bg-[#22D3EE]/10 text-[#22D3EE]" : "border-white/15 text-white/70 hover:border-[#22D3EE]/50 hover:text-white"}`}
          >
            {actions.perimetre ? "Retirer le périmètre de travail" : "Utiliser comme périmètre de travail"}
          </button>
        </div>
      )}
      <dl className="mt-3 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-white/40">Jumeaux</dt><dd className="font-code text-white/85">{stats.twins.length}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Couverture moyenne</dt><dd className="font-code text-white/85">{stats.couv} %</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Situations liées</dt><dd className="font-code text-white/85">{stats.sits.length}</dd></div>
      </dl>
      {stats.equipes.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Équipes responsables</div>
          <ul className="mt-1 space-y-1">
            {stats.equipes.map((e, i) => <li key={i} className="text-xs text-white/60">→ {e}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3">
        <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Capacités métier</div>
        <ul className="mt-1 space-y-1">
          {stats.twins.map((j) => <li key={j.id} className="text-xs text-white/60">→ {j.nom} — {(j.mission || "").slice(0, 60)}</li>)}
        </ul>
      </div>
      {Object.keys(stats.ext).length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Dépendances vers l'extérieur</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {Object.entries(stats.ext).map(([dom, n]) => (
              <span key={dom} className="rounded-full border px-2 py-0.5 font-code text-[10px]" style={{ color: couleurDomaine(dom), borderColor: `${couleurDomaine(dom)}44`, backgroundColor: `${couleurDomaine(dom)}0D` }}>
                Vers {dom} · {n}
              </span>
            ))}
          </div>
        </div>
      )}
      {stats.sits.length > 0 && (
        <div className="mt-3">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Découvertes & investigations</div>
          <ul className="mt-1 space-y-1.5">
            {stats.sits.slice(0, 4).map((s) => <li key={s.id} className="text-xs leading-snug text-white/55">→ {s.titre}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function PorteDetail({ interne, externe, mesh, domDe }) {
  const relations = (mesh?.relations || []).filter((r) => {
    const a = domDe[r.source];
    const b = domDe[r.cible];
    return (a === interne && b === externe) || (a === externe && b === interne);
  });
  return (
    <div data-testid="porte-detail">
      <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Porte externe</div>
      <h3 className="mt-1.5 font-display text-base font-bold text-white">
        {interne} ↔ {externe}
      </h3>
      <p className="mt-1 font-code text-[10px] text-white/45">{relations.length} relation(s) entre les deux domaines</p>
      <ul className="mt-3 space-y-2">
        {relations.map((r) => {
          const etat = ETATS_RELATION[r.etat] || ETATS_RELATION.confirmee;
          return (
            <li key={r.id} className="rounded-md border border-white/[0.07] bg-white/[0.02] px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-code text-[10px] text-white/80">{r.source} → {r.cible}</span>
                <span className="font-code text-[9px]" style={{ color: etat.couleur }}>{etat.label}</span>
              </div>
              {r.label && <p className="mt-1 text-[11px] text-white/45">{r.label}</p>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ComparaisonDomaines({ a, b, statsDomaine }) {
  const sa = statsDomaine(a);
  const sb = statsDomaine(b);
  if (!sa || !sb) return null;
  const lignes = [
    ["Jumeaux", sa.twins.length, sb.twins.length],
    ["Couverture moyenne", `${sa.couv} %`, `${sb.couv} %`],
    ["Dépendances externes", Object.values(sa.ext).reduce((x, y) => x + y, 0), Object.values(sb.ext).reduce((x, y) => x + y, 0)],
    ["Situations liées", sa.sits.length, sb.sits.length],
    ["Zones inconnues", sa.reg?.maturite?.zones_inconnues ?? "—", sb.reg?.maturite?.zones_inconnues ?? "—"],
  ];
  return (
    <div data-testid="comparaison-domaines">
      <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Comparaison de domaines</div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-code text-[11px]">
        <div />
        <div className="font-semibold" style={{ color: couleurDomaine(a) }}>{a}</div>
        <div className="font-semibold" style={{ color: couleurDomaine(b) }}>{b}</div>
        {lignes.map(([label, va, vb]) => (
          <div key={label} className="contents">
            <div className="py-1 text-white/40">{label}</div>
            <div className="py-1 text-white/85">{va}</div>
            <div className="py-1 text-white/85">{vb}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TwinDetail({ selected }) {
  return (
    <div data-testid="map-twin-detail">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(selected.domaine) }} />
        <h3 className="font-display text-base font-bold text-white">{selected.nom}</h3>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-white/60">{selected.mission}</p>
      <dl className="mt-4 space-y-2 text-xs">
        <div className="flex justify-between"><dt className="text-white/40">Propriétaire</dt><dd className="text-white/80">{selected.proprietaire || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Statut</dt><dd className="font-code text-white/80">{selected.statut}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Autonomie</dt><dd className="font-code text-white/80">{selected.autonomie || "—"}</dd></div>
        <div className="flex justify-between"><dt className="text-white/40">Fraîcheur</dt><dd className="font-code text-white/80">{selected.fraicheur}</dd></div>
      </dl>
      <div className="mt-3">
        <div className="flex justify-between text-xs"><span className="text-white/40">Couverture</span><span className="font-code text-white/85">{selected.couverture} %</span></div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.07]">
          <div className="h-full rounded-full" style={{ width: `${selected.couverture}%`, backgroundColor: couleurDomaine(selected.domaine) }} />
        </div>
      </div>
      {selected.sources && (
        <div className="mt-4">
          <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Sources</div>
          <div className="mt-1.5 flex gap-1.5">
            {Object.entries(selected.sources).map(([k, v]) => (
              <span key={k} title={k} className={`h-2 w-2 rounded-full ${v ? "bg-[#10B981]" : "bg-white/15"}`} />
            ))}
          </div>
        </div>
      )}
      <Link to="/jumeaux" className="mt-4 inline-block text-xs text-[#3B82F6] hover:underline" data-testid="map-goto-registry">
        Administrer dans Jumeaux →
      </Link>
    </div>
  );
}
