import { useEffect, useMemo, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
import { couleurDomaine, DOMAINES, NATURES_EVENEMENT } from "@/lib/domaines";

const nodeTypes = { twin: TwinNode, region: RegionNode };

const MODES = [
  { id: "territoire", label: "Territoire", question: "Comment le SI est-il organisé ?" },
  { id: "situation", label: "Situation", question: "Que se passe-t-il ici ?" },
  { id: "parcours", label: "Parcours", question: "Comment cette activité fonctionne-t-elle ?" },
];

const makeEdge = (r) => {
  const decouverte = r.type === "decouverte";
  return {
    id: r.id,
    source: r.source,
    target: r.cible,
    animated: !!r.active,
    style: {
      stroke: decouverte ? "#F59E0B" : r.active ? "#3B82F6" : "rgba(255,255,255,0.16)",
      strokeWidth: decouverte ? 2 : 1.5,
      strokeDasharray: decouverte ? "7 5" : r.active ? undefined : "3 6",
      opacity: decouverte || r.active ? 0.95 : 0.5,
    },
    label: decouverte ? `relation non documentée${r.confiance ? ` — ${r.confiance} %` : ""}` : undefined,
    labelStyle: { fill: "#FBBF24", fontSize: 10, fontFamily: "IBM Plex Mono" },
    labelBgStyle: { fill: "rgba(5,5,5,0.85)" },
  };
};

export default function SystemMap() {
  const [searchParams] = useSearchParams();
  const { mesh } = useMesh();
  const [situations, setSituations] = useState([]);
  const modeParam = searchParams.get("mode");
  const [mode, setMode] = useState(modeParam || "territoire");
  const [situationId, setSituationId] = useState(searchParams.get("situation") || "sit-latence-paiements");
  const [parcoursId, setParcoursId] = useState("parcours-paiement");
  const focus = searchParams.get("focus");
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]);
  const [halo, setHalo] = useState(null);
  const [compteurs, setCompteurs] = useState({});
  const [onglet, setOnglet] = useState("chrono");

  useEffect(() => {
    if (modeParam) setMode(modeParam);
  }, [modeParam]);

  useEffect(() => {
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    let stop = false;
    let timer;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (stop) return;
        setEvents((prev) => [...data.map((e, i) => ({ ...e, uid: `${Date.now()}-${i}` })), ...prev].slice(0, 16));
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
    const t = setInterval(tick, 6000);
    return () => { stop = true; clearInterval(t); clearTimeout(timer); };
  }, []);

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

    let ns = [];
    if (mode === "territoire") {
      ns = (mesh.regions || []).map((r) => ({
        id: r.id, type: "region", position: { x: r.x, y: r.y }, data: r,
        draggable: false, selectable: false, zIndex: -10,
      }));
    }

    let twins = mesh.jumeaux;
    if (mode === "parcours" && parcours) {
      twins = mesh.jumeaux.filter((j) => parcours.etapes.includes(j.id));
    }

    ns = ns.concat(
      twins.map((j) => {
        const etape = mode === "parcours" && parcours ? parcours.etapes.indexOf(j.id) + 1 : null;
        const position = etape ? { x: (etape - 1) * 250, y: 280 + (etape % 2) * 46 } : j.position;
        return {
          id: j.id,
          type: "twin",
          position,
          data: { jumeau: j, dim: dims.has(j.id), halo: halo === j.id, evenements: compteurs[j.id] || 0, etape },
          selected: selected?.id === j.id,
        };
      })
    );

    let es = [];
    if (mode === "parcours" && parcours) {
      es = parcours.etapes.slice(1).map((id, i) =>
        makeEdge({ id: `p-${i}`, source: parcours.etapes[i], cible: id, active: true, type: "structurante" })
      );
    } else {
      es = mesh.relations
        .filter((r) => (mode === "situation" && implique.length ? implique.includes(r.source) && implique.includes(r.cible) : r.type !== "secondaire"))
        .filter((r) => !focus || r.source === focus || r.cible === focus)
        .map(makeEdge);
    }
    return { nodes: ns, edges: es };
  }, [mesh, mode, situationId, parcoursId, focus, halo, compteurs, selected, situation]);

  const modeInfo = MODES.find((m) => m.id === mode);

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
        maxZoom={1.6}
        onNodeClick={(_, node) => {
          if (node.type !== "twin") return;
          setSelected(node.data.jumeau);
          setOnglet("detail");
        }}
        onPaneClick={() => setSelected(null)}
        nodesDraggable={mode === "territoire"}
        nodesConnectable={false}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="rgba(255,255,255,0.06)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>

      {/* Sélecteur de mode */}
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
              <option key={s.id} value={s.id}>{s.titre}</option>
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
              <option key={p.id} value={p.id}>{p.nom}</option>
            ))}
          </select>
        )}
        {focus && (
          <Link to="/carte" className="mt-2 block px-1 font-code text-[10px] text-[#3B82F6] hover:underline" data-testid="map-clear-focus">
            ← Retirer le filtre « {focus} »
          </Link>
        )}
      </div>

      {/* Bandeau situation */}
      {mode === "situation" && situation && (
        <div className="glass absolute left-1/2 top-4 z-10 max-w-md -translate-x-1/2 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
          <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#F59E0B]">Situation active</div>
          <div className="text-xs font-semibold text-white">{situation.titre}</div>
        </div>
      )}

      {/* Légende */}
      <div className="glass absolute bottom-4 left-4 z-10 flex flex-wrap gap-3 rounded-lg px-3 py-2" data-testid="map-legend">
        {Object.entries(DOMAINES).filter(([d]) => d !== "Non classé").map(([d, c]) => (
          <span key={d} className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-white/50">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} /> {d}
          </span>
        ))}
        <span className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-[#F59E0B]">
          <span className="inline-block h-px w-4 border-t border-dashed border-[#F59E0B]" /> découverte
        </span>
      </div>

      {/* Panneau latéral */}
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
            selected ? (
              <div data-testid="map-twin-detail">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: couleurDomaine(selected.domaine) }} />
                  <h3 className="font-display text-base font-bold text-white">{selected.nom}</h3>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-white/60">{selected.mission}</p>
                <dl className="mt-4 space-y-2 text-xs">
                  <div className="flex justify-between"><dt className="text-white/40">Propriétaire</dt><dd className="text-white/80">{selected.proprietaire}</dd></div>
                  <div className="flex justify-between"><dt className="text-white/40">Statut</dt><dd className="font-code text-white/80">{selected.statut}</dd></div>
                  <div className="flex justify-between"><dt className="text-white/40">Autonomie</dt><dd className="font-code text-white/80">{selected.autonomie}</dd></div>
                  <div className="flex justify-between"><dt className="text-white/40">Fraîcheur</dt><dd className="font-code text-white/80">{selected.fraicheur}</dd></div>
                </dl>
                <div className="mt-3">
                  <div className="flex justify-between text-xs"><span className="text-white/40">Couverture</span><span className="font-code text-white/85">{selected.couverture} %</span></div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.07]">
                    <div className="h-full rounded-full" style={{ width: `${selected.couverture}%`, backgroundColor: couleurDomaine(selected.domaine) }} />
                  </div>
                </div>
                <div className="mt-4">
                  <div className="font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Sources</div>
                  <div className="mt-1.5 flex gap-1.5">
                    {Object.entries(selected.sources || {}).map(([k, v]) => (
                      <span key={k} title={k} className={`h-2 w-2 rounded-full ${v ? "bg-[#10B981]" : "bg-white/15"}`} />
                    ))}
                  </div>
                </div>
                <Link to="/registry" className="mt-4 inline-block text-xs text-[#3B82F6] hover:underline" data-testid="map-goto-registry">
                  Administrer dans Registry →
                </Link>
              </div>
            ) : (
              <p className="text-xs text-white/35">Sélectionnez un jumeau sur la carte pour afficher son identité, sa couverture et ses sources.</p>
            )
          ) : (
            <ul className="space-y-3" data-testid="map-chrono-list">
              {events.map((e) => {
                const j = mesh?.jumeaux.find((x) => x.id === e.jumeau);
                const c = NATURES_EVENEMENT[e.nature] || "#6B7280";
                return (
                  <li key={e.uid} className="ticker-item flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: c }} />
                    <div>
                      <span className="font-code text-[10px]" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span>
                      <p className="text-xs leading-snug text-white/55">{e.texte}</p>
                    </div>
                  </li>
                );
              })}
              {events.length === 0 && <li className="text-xs text-white/30">Écoute du Mesh en cours…</li>}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
