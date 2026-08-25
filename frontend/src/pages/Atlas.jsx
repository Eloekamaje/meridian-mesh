import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ForceGraph3D from "react-force-graph-3d";
import { toast } from "sonner";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import TwinNode from "@/components/map/TwinNode";
import RegionNode from "@/components/map/RegionNode";
import { couleurDomaine, DOMAINES, NATURES_EVENEMENT, ETATS_RELATION } from "@/lib/domaines";

const nodeTypes = { twin: TwinNode, region: RegionNode };

const MODES = [
  { id: "territoire", label: "Territoire", question: "Comment le SI est-il organisé ?" },
  { id: "situation", label: "Situation", question: "Que se passe-t-il ici ?" },
  { id: "parcours", label: "Parcours", question: "Comment cette activité fonctionne-t-elle ?" },
  { id: "orbite", label: "Orbite 3D", question: "Explorer le Mesh en trois dimensions — tourner, zoomer, survoler" },
];

const COUCHES = [
  ["operationnelle", "Opérationnelle", "#3B82F6"],
  ["connaissance", "Connaissance", "#22D3EE"],
  ["mesh", "Mesh", "#A78BFA"],
];

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

const makeEdge = (r) => ({
  id: r.id,
  source: r.source,
  target: r.cible,
  animated: !!r.active || r.etat === "validation",
  data: { etat: r.etat, restreinte: !!r.restreinte },
  style: r.restreinte
    ? { ...styleParEtat(r), opacity: 0.35, strokeDasharray: "3 5" }
    : styleParEtat(r),
  label:
    r.etat === "validation"
      ? `validation A2A${r.confiance ? ` — ${r.confiance} %` : ""}`
      : r.etat === "contestee"
        ? "contestée — contradiction"
        : undefined,
  labelStyle: { fill: r.etat === "validation" ? "#A78BFA" : "#F87171", fontSize: 10, fontFamily: "IBM Plex Mono" },
  labelBgStyle: { fill: "rgba(5,5,5,0.85)" },
});

export default function Atlas() {
  const [searchParams] = useSearchParams();
  const { mesh, jumeauPar, recharger } = useMesh();
  const { version, vueActive, rechargerVues } = usePerimetre();
  const [situations, setSituations] = useState([]);
  const [nomVue, setNomVue] = useState("");
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

  useEffect(() => {
    if (modeParam) setMode(modeParam);
  }, [modeParam]);

  useEffect(() => {
    api.get("/situations").then((r) => setSituations(r.data)).catch(() => {});
  }, [version]);

  useEffect(() => {
    setEvents([]);
    setCompteurs({});
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
    const t = setInterval(tick, 6000);
    return () => { stop = true; clearInterval(t); clearTimeout(timer); };
  }, [version]);

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
        makeEdge({ id: `p-${i}`, source: parcours.etapes[i], cible: id, active: true, etat: "confirmee" })
      );
    } else {
      es = mesh.relations
        .filter((r) => (mode === "situation" && implique.length ? implique.includes(r.source) && implique.includes(r.cible) : true))
        .filter((r) => !focus || r.source === focus || r.cible === focus)
        .map(makeEdge);
    }
    if (vueActive?.type === "relations_non_confirmees") {
      es = es.map((e) =>
        e.data?.etat === "confirmee" ? { ...e, animated: false, style: { ...e.style, opacity: 0.1 } } : e
      );
    }
    return { nodes: ns, edges: es };
  }, [mesh, mode, situationId, parcoursId, focus, halo, compteurs, selected, situation, vueActive]);

  const eventsVisibles = events.filter((e) => couches[e.dynamique || "operationnelle"]);
  const modeInfo = MODES.find((m) => m.id === mode);

  const fgRef = useRef();
  useEffect(() => {
    if (mode !== "orbite" || !fgRef.current) return;
    const controls = fgRef.current.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.55;
    const t = setTimeout(() => fgRef.current?.cameraPosition({ x: 0, y: 0, z: 240 }), 1500);
    return () => clearTimeout(t);
  }, [mode]);

  const graphData = useMemo(() => {
    if (!mesh) return { nodes: [], links: [] };
    const ids = new Set(mesh.jumeaux.map((j) => j.id));
    return {
      nodes: mesh.jumeaux.map((j) => ({
        id: j.id,
        nom: j.nom,
        domaine: j.domaine,
        anonyme: !!j.anonyme,
        couleur: j.anonyme ? "#374151" : couleurDomaine(j.domaine),
        couverture: j.couverture || 40,
        jumeau: j,
      })),
      links: mesh.relations
        .filter((r) => ids.has(r.source) && ids.has(r.cible))
        .map((r) => ({ id: r.id, source: r.source, target: r.cible, etat: r.etat, active: !!r.active, restreinte: !!r.restreinte })),
    };
  }, [mesh]);

  const confirmerRelation = async (r) => {
    try {
      await api.post(`/relations/${r.id}/confirmer`);
      toast.success("Relation confirmée — mémoire du Mesh enrichie");
      setSelectedRelation(null);
      recharger();
    } catch {
      toast.error("Confirmation impossible");
    }
  };

  return (
    <div className="relative h-full w-full overflow-hidden" data-testid="system-map">
      {mode === "orbite" ? (
        <div className="absolute inset-0" data-testid="atlas-orbite">
          <ForceGraph3D
            ref={fgRef}
            graphData={graphData}
            backgroundColor="#050505"
            nodeColor={(n) => n.couleur}
            nodeVal={(n) => (n.anonyme ? 0.6 : Math.max(0.8, (n.couverture || 40) / 22))}
            nodeOpacity={0.95}
            nodeResolution={24}
            nodeLabel={(n) => (n.anonyme ? "Périmètre restreint — identité masquée" : `${n.nom} · ${n.domaine}`)}
            linkColor={(l) =>
              l.restreinte
                ? "rgba(255,255,255,0.14)"
                : l.etat === "validation"
                  ? "#A78BFA"
                  : l.etat === "contestee"
                    ? "#F87171"
                    : l.etat === "supposee"
                      ? "#22D3EE"
                      : l.etat === "obsolete"
                        ? "rgba(255,255,255,0.10)"
                        : l.active
                          ? "#3B82F6"
                          : "rgba(255,255,255,0.22)"
            }
            linkWidth={(l) => (l.etat === "validation" ? 1.8 : l.active ? 1.4 : 0.8)}
            linkOpacity={0.55}
            linkDirectionalParticles={(l) => (l.active || l.etat === "validation" ? 2 : 0)}
            linkDirectionalParticleWidth={1.6}
            linkDirectionalParticleSpeed={0.005}
            onNodeClick={(n) => {
              if (n.anonyme) return;
              setSelected(n.jumeau);
              setSelectedRelation(null);
              setOnglet("detail");
            }}
            onBackgroundClick={() => { setSelected(null); setSelectedRelation(null); }}
            cooldownTicks={140}
            enableNodeDrag={false}
          />
        </div>
      ) : (
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
          setSelectedRelation(null);
          setOnglet("detail");
        }}
        onEdgeClick={(_, edge) => {
          const rel = mesh?.relations.find((r) => r.id === edge.id);
          if (!rel) return;
          setSelectedRelation(rel);
          setSelected(null);
          setOnglet("detail");
        }}
        onPaneClick={() => { setSelected(null); setSelectedRelation(null); }}
        nodesDraggable={mode === "territoire"}
        nodesConnectable={false}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="rgba(255,255,255,0.06)" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      )}

      {/* Sélecteur de mode + couches */}
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
          <Link to="/atlas" className="mt-2 block px-1 font-code text-[10px] text-[#3B82F6] hover:underline" data-testid="map-clear-focus">
            ← Retirer le filtre « {focus} »
          </Link>
        )}

        {mesh?.perimetre?.nb_restreints > 0 && (
          <div className="mt-2 rounded border border-dashed border-white/15 px-2 py-1.5 font-code text-[9px] leading-relaxed text-white/45" data-testid="badge-dependances-restreintes">
            {mesh.perimetre.nb_restreints} dépendance(s) restreinte(s) — politique « {mesh.perimetre.politique === "anonymisee" ? "dépendance anonymisée" : mesh.perimetre.politique === "resume" ? "résumé autorisé" : "masquage complet"} »
          </div>
        )}

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

        <div className="mt-3 border-t border-white/[0.08] pt-2.5">
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
      </div>

      {/* Bandeau situation */}
      {mode === "situation" && situation && (
        <div className="glass absolute left-1/2 top-4 z-10 max-w-md -translate-x-1/2 rounded-xl px-4 py-2.5" data-testid="map-situation-banner">
          <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#A78BFA]">Situation en cours de compréhension</div>
          <div className="text-xs font-semibold text-white">{situation.titre}</div>
        </div>
      )}

      {/* Légende : états des relations */}
      <div className="glass absolute bottom-4 left-4 z-10 max-w-[420px] rounded-lg px-3 py-2" data-testid="map-legend">
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
            selectedRelation ? (
              <RelationDetail rel={selectedRelation} jumeauPar={jumeauPar} onConfirmer={confirmerRelation} />
            ) : selected ? (
              <TwinDetail selected={selected} />
            ) : (
              <p className="text-xs text-white/35">
                Sélectionnez un jumeau ou une relation pour voir ce que Méridian connaît, vient de découvrir ou cherche encore à comprendre.
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

function TwinDetail({ selected }) {
  return (
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
      <Link to="/jumeaux" className="mt-4 inline-block text-xs text-[#3B82F6] hover:underline" data-testid="map-goto-registry">
        Administrer dans Jumeaux →
      </Link>
    </div>
  );
}
