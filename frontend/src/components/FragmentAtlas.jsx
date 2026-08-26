import { useMemo } from "react";
import { ReactFlow, Background, BackgroundVariant } from "@xyflow/react";
import TwinNode from "./map/TwinNode";
import { makeEdge } from "@/lib/atlasGraph";

const nodeTypes = { twin: TwinNode };

// Fragment vivant de l'Atlas : sous-graphe interactif embarqué dans une actualité
export default function FragmentAtlas({ mesh, jumeaux = [], dateTs }) {
  const { nodes, edges } = useMemo(() => {
    const js = jumeaux.map((id) => mesh?.jumeaux.find((j) => j.id === id)).filter(Boolean);
    if (!js.length) return { nodes: [], edges: [] };
    const esp = Math.max(260, 620 / js.length);
    const largeur = (js.length - 1) * esp;
    const ns = js.map((j, i) => ({
      id: j.id,
      type: "twin",
      position: { x: i * esp - largeur / 2, y: 20 },
      initialWidth: 190,
      initialHeight: 64,
      data: { jumeau: j },
      draggable: false,
      selectable: false,
    }));
    const idset = new Set(js.map((j) => j.id));
    const es = (mesh?.relations || [])
      .filter((r) => idset.has(r.source) && idset.has(r.cible))
      .map((r) => ({ ...makeEdge(r, 2), animated: true, style: { ...makeEdge(r, 2).style, strokeWidth: 2 } }));
    return { nodes: ns, edges: es };
  }, [mesh, jumeaux]);

  if (!nodes.length) return null;

  return (
    <div className="relative h-[190px] overflow-hidden rounded-lg border border-[#E5E5E3] bg-[#FBFBFA]" data-testid="fragment-atlas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        panOnDrag
        zoomOnScroll={false}
        zoomOnDoubleClick={false}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
        colorMode="light"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(17,17,16,0.06)" />
      </ReactFlow>
      <span className="pointer-events-none absolute right-2 top-2 font-code text-[8px] uppercase tracking-[0.2em] text-[#71716D]">Fragment vivant de l'Atlas</span>
    </div>
  );
}
