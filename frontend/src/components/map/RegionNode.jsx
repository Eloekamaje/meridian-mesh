import { Handle, Position } from "@xyflow/react";

// Membrane polygonale translucide — coque concave qui épouse les avatars du domaine
// Le survol est géré par proximité au niveau de la carte (les zones d'interaction des arêtes recouvrent les frontières)
export default function RegionNode({ data }) {
  const survol = !!data.survol;
  // Propulsion : la membrane du territoire ciblé se révèle au fil de la progression du geste
  const prop = data.propulsion || 0;
  const a = (v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0");

  return (
    <div
      style={{ width: data.w, height: data.h, pointerEvents: "none" }}
      className="relative"
      data-testid={`region-${data.id}`}
    >
      <Handle type="target" id="t-l" position={Position.Left} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="source" id="s-l" position={Position.Left} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="target" id="t-r" position={Position.Right} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="source" id="s-r" position={Position.Right} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <svg
        viewBox={`0 0 ${data.wCible || data.w} ${data.hCible || data.h}`}
        width={data.w}
        height={data.h}
        preserveAspectRatio="none"
        className={`absolute inset-0 transition-opacity duration-300 ${data.attenue ? "opacity-40" : "opacity-100"}`}
        style={{ overflow: "visible" }}
      >
        {data.path ? (
          <path
            d={data.path}
            fill={prop ? `${data.couleur}${a(0.11 + prop * 0.14)}` : survol ? `${data.couleur}26` : `${data.couleur}1C`}
            stroke={prop ? `${data.couleur}${a(0.25 + prop * 0.5)}` : survol ? `${data.couleur}59` : `${data.couleur}30`}
            strokeWidth={prop ? 1.8 + prop * 1.8 : survol ? 2.2 : 1.8}
            strokeLinejoin="round"
            style={{ transition: "fill 200ms, stroke 200ms" }}
            data-testid={`region-membrane-${data.id}`}
          />
        ) : (
          <rect width={data.w} height={data.h} rx={56} fill={`${data.couleur}13`} stroke={`${data.couleur}38`} strokeWidth={1.5} />
        )}
      </svg>
    </div>
  );
}
