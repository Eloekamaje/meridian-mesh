import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ReactFlow, Background, BackgroundVariant, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Compass } from "@phosphor-icons/react";
import TwinNode from "@/components/map/TwinNode";
import { makeEdge } from "@/lib/atlasGraph";
import { useContexte } from "@/lib/contexte";

const nodeTypes = { twin: TwinNode };

export default function OngletAtlas({ cas, mesh }) {
  const navigate = useNavigate();
  const { setSelection } = useContexte();
  const ids = cas.jumeaux || [];

  const { nodes, edges } = useMemo(() => {
    if (!mesh || ids.length === 0) return { nodes: [], edges: [] };
    const presents = ids.map((id) => mesh.jumeaux.find((j) => j.id === id)).filter(Boolean);
    const cx = 400;
    const cy = 260;
    const ray = presents.length > 2 ? 220 : 150;
    const ns = presents.map((j, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / presents.length;
      return {
        id: j.id,
        type: "twin",
        position: presents.length === 1 ? { x: cx - 95, y: cy - 32 } : { x: cx + Math.cos(ang) * ray - 95, y: cy + Math.sin(ang) * ray - 32 },
        initialWidth: 190,
        initialHeight: 64,
        data: { jumeau: j, dim: false, evenements: 0 },
        draggable: false,
        selectable: false,
      };
    });
    const es = (mesh.relations || [])
      .filter((r) => ids.includes(r.source) && ids.includes(r.cible))
      .map((r) => makeEdge(r, 3));
    return { nodes: ns, edges: es };
  }, [mesh, cas.id]);

  if (ids.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 p-10 text-center" data-testid="onglet-atlas-vide">
        <p className="text-sm text-white/40">Aucun jumeau mobilisé — le sous-graphe du case apparaîtra ici.</p>
      </div>
    );
  }

  return (
    <div data-testid="onglet-atlas">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">
          Sous-graphe du case — {ids.length} jumeau{ids.length > 1 ? "x" : ""} mobilisé{ids.length > 1 ? "s" : ""}
        </p>
        <button
          onClick={() => { setSelection(ids); navigate("/atlas"); }}
          data-testid="case-atlas-complet-btn"
          className="flex items-center gap-1.5 rounded-md border border-[#22D3EE]/30 bg-[#22D3EE]/[0.06] px-3 py-1.5 text-xs text-[#22D3EE] transition-colors hover:bg-[#22D3EE]/15"
        >
          <Compass size={13} /> Ouvrir dans l'Atlas complet
        </button>
      </div>
      <div className="h-[460px] overflow-hidden rounded-xl border border-white/[0.07] bg-[#050505]" data-testid="case-minimap">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.4}
          maxZoom={1.6}
          nodesDraggable={false}
          nodesConnectable={false}
          zoomOnDoubleClick={false}
          colorMode="dark"
        >
          <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="rgba(255,255,255,0.05)" />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </div>
  );
}
