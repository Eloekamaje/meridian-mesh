import { MATURITES } from "@/lib/domaines";
import { Handle, Position } from "@xyflow/react";

// Région = coque organique (SVG) qui épouse ses nœuds internes et se déforme avec eux
export default function RegionNode({ data }) {
  const m = data.maturite;
  const mc = m ? MATURITES[m.niveau] || "#71716D" : null;
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
      <svg width={data.w} height={data.h} className="absolute inset-0" style={{ overflow: "visible" }}>
        {data.path ? (
          <path d={data.path} fill={`${data.couleur}13`} stroke={`${data.couleur}38`} strokeWidth={1.5} strokeLinejoin="round" />
        ) : (
          <rect width={data.w} height={data.h} rx={56} fill={`${data.couleur}13`} stroke={`${data.couleur}38`} strokeWidth={1.5} />
        )}
      </svg>
      <div
        className="nopan absolute top-4 cursor-pointer text-center"
        style={{ pointerEvents: "auto", left: data.labelX ?? data.w / 2, transform: "translateX(-50%)" }}
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
        {m && (
          <div className="mt-1 whitespace-nowrap font-code text-[9px] text-[#71716D]">
            {m.jumeaux} jumeaux · {data.decouvertes ?? 0} découverte{(data.decouvertes ?? 0) > 1 ? "s" : ""} · {data.investigations ?? 0} investigation{(data.investigations ?? 0) > 1 ? "s" : ""} · {m.zones_inconnues} zone{m.zones_inconnues > 1 ? "s" : ""} inconnue{m.zones_inconnues > 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  );
}
