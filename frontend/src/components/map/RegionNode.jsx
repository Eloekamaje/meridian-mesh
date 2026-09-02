import { MATURITES } from "@/lib/domaines";
import { Handle, Position } from "@xyflow/react";

// Membrane polygonale translucide — coque concave qui épouse les avatars du domaine
// Le survol est géré par proximité au niveau de la carte (les zones d'interaction des arêtes recouvrent les frontières)
export default function RegionNode({ data }) {
  const m = data.maturite;
  const mc = m ? MATURITES[m.niveau] || "#71716D" : null;
  const survol = !!data.survol;

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
            fill={survol ? `${data.couleur}1F` : `${data.couleur}13`}
            stroke={survol ? `${data.couleur}66` : `${data.couleur}38`}
            strokeWidth={survol ? 2 : 1.5}
            strokeLinejoin="round"
            style={{ transition: "fill 200ms, stroke 200ms" }}
            data-testid={`region-membrane-${data.id}`}
          />
        ) : (
          <rect width={data.w} height={data.h} rx={56} fill={`${data.couleur}13`} stroke={`${data.couleur}38`} strokeWidth={1.5} />
        )}
      </svg>

      <div
        className="nopan absolute top-4 cursor-pointer text-center"
        style={{ pointerEvents: "auto", left: `${(((data.labelX ?? data.w / 2) / (data.wCible || data.w)) * 100).toFixed(2)}%`, transform: "translateX(-50%)" }}
        title="Clic : sélectionner le domaine · Double-clic : entrer dans le domaine"
        data-testid={`region-header-${data.id}`}
      >
        <div className="flex items-center justify-center gap-2.5">
          {data.halo && (
            <span className="halo-anim h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: data.couleur }} data-testid={`region-activite-${data.id}`} />
          )}
          <span className="whitespace-nowrap font-code text-xs font-semibold uppercase tracking-[0.25em]" style={{ color: data.couleur }}>
            {data.label}
          </span>
          {mc && (
            <span
              className="rounded-full border bg-white/70 px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider"
              style={{ color: mc, borderColor: `${mc}44` }}
            >
              {m.niveau}
            </span>
          )}
        </div>
        {data.macro && m && (
          <div className="mt-1.5 flex items-center justify-center gap-2 font-code text-[10px] text-[#52524F]" data-testid={`region-macro-${data.id}`}>
            <span>{m.jumeaux} jumeau{m.jumeaux > 1 ? "x" : ""}</span>
            <span className="text-[#71716D]">·</span>
            <span>{data.flux ?? 0} flux</span>
            <span className="text-[#71716D]">·</span>
            <span className={(data.ecarts ?? 0) > 0 ? "text-[#D97706]" : ""}>{data.ecarts ?? 0} écart{(data.ecarts ?? 0) > 1 ? "s" : ""}</span>
          </div>
        )}
      </div>
    </div>
  );
}
