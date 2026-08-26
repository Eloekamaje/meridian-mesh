import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls, SelectionMode } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { X, Sparkle } from "@phosphor-icons/react";
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
import useNavigationAtlas from "@/components/map/useNavigationAtlas";
import useZoomSemantique from "@/components/map/useZoomSemantique";
import { NIVEAUX_ZOOM, construireGraphe, statsDuDomaine } from "@/lib/atlasGraph";
import { couleurDomaine } from "@/lib/domaines";

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
  const [direct, setDirect] = useState(true);
  const [outil, setOutil] = useState("deplacement");
  const { selection, setSelection, domaineSel, setDomaineSel, focusCarte, commanderCarte, setFocusVisuel } = useContexte();
  const [relFocus, setRelFocus] = useState(false);
  const [posOverrides, setPosOverrides] = useState({});
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

  const { nodes, edges } = useMemo(
    () =>
      construireGraphe({
        mesh, situation, focus, vueActive, perimetreTravail,
        jumeauFocus, domaineInterne, posOverrides, compteurs, halo, selection,
        zoomNiveau, relFocus, focusCarte, domDe, statsRegions,
      }),
    [mesh, focus, situation, halo, compteurs, selection, relFocus, zoomNiveau, vueActive, posOverrides, domaineSel, domaineInterne, jumeauFocus, perimetreTravail, domDe, statsRegions, focusCarte]
  );

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
    <div className="relative h-full w-full overflow-hidden" data-testid="system-map">
      <ReactFlow
        key={focus || situationParam || "mesh"}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        maxZoom={2.6}
        zoomOnDoubleClick={false}
        onInit={(inst) => { rfRef.current = inst; }}
        onMove={onMove}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
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
                if (Math.abs(p.x - (pos.x + 95)) < 140 && Math.abs(p.y - (pos.y + 32)) < 75) { entrerJumeau(j); return; }
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
          setSelected(null); setSelectedRelation(null); setDomaineSel(null); setSelection([]); setRelFocus(false); setComparaison(null); setAttenteComparaison(false); commanderCarte(null);
          majUrl(domaineInterne ? { sel: null } : { sel: null, domaine: null, interne: null, jumeau: null });
        }}
        nodesDraggable
        nodesConnectable={false}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="rgba(255,255,255,0.05)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>

      <AtlasControle
        mesh={mesh} focus={focus}
        direct={direct} setDirect={setDirect}
        couches={couches} setCouches={setCouches}
        rechargerVues={rechargerVues}
      />

      <AtlasToolbar outil={outil} setOutil={setOutil} rfRef={rfRef} />

      {/* Bandeau situation (focus profond depuis Aujourd'hui / Investigations) */}
      {situation && (
        <div className="glass absolute left-1/2 top-4 z-10 flex max-w-md -translate-x-1/2 items-center gap-3 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
          <div>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#A78BFA]">Focus — situation</div>
            <div className="text-xs font-semibold text-white">{situation.titre}</div>
            <div className="mt-0.5 font-code text-[9px] text-white/40">
              {situation.jumeaux.length} jumeaux · contexte réduit au pertinent
            </div>
          </div>
          <button onClick={() => majUrl({ situation: null })} data-testid="map-clear-situation" title="Retirer le focus situation" className="shrink-0 text-white/40 transition-colors hover:text-white">
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
      {(
        <div className="glass absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg px-3 py-1.5 font-code text-[10px] text-white/50" data-testid="zoom-niveau">
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

      <AtlasPanneau
        onglet={onglet} setOnglet={setOnglet}
        comparaison={comparaison} selectedRelation={selectedRelation}
        selected={selected} domaineSel={domaineSel}
        statsDomaine={statsDomaine} actionsDomaine={actionsDomaine}
        confirmerRelation={confirmerRelation}
        eventsVisibles={eventsVisibles} jumeauPar={jumeauPar}
      />
    </div>
  );
}
