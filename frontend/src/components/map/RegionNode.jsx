import { MATURITES } from "@/lib/domaines";
import { Handle, Position } from "@xyflow/react";

export default function RegionNode({ data }) {
  const m = data.maturite;
  const mc = m ? MATURITES[m.niveau] || "#9CA3AF" : null;
  return (
    <div
      style={{
        width: data.w,
        height: data.h,
        pointerEvents: "none",
        borderRadius: 56,
        border: `1px solid ${data.couleur}2E`,
        background: `${data.couleur}08`,
      }}
      className="relative"
      data-testid={`region-${data.id}`}
    >
      <Handle type="target" position={Position.Left} className="!h-0 !w-0 !border-0 !bg-transparent" />
      <Handle type="source" position={Position.Right} className="!h-0 !w-0 !border-0 !bg-transparent" />
      <div className="absolute left-7 top-5 flex items-center gap-2.5">
        <span className="font-code text-[11px] font-medium uppercase tracking-[0.3em]" style={{ color: data.couleur }}>
          {data.label}
        </span>
        {mc && (
          <span
            className="rounded-full border px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider"
            style={{ color: mc, borderColor: `${mc}44`, backgroundColor: `${mc}10` }}
          >
            {m.niveau}
          </span>
        )}
      </div>
      {m && (
        <div className="absolute left-7 top-10 font-code text-[9px] text-white/35">
          {m.jumeaux} jumeaux · {m.relations_emergentes} découverte{m.relations_emergentes > 1 ? "s" : ""} · {m.zones_inconnues} zone{m.zones_inconnues > 1 ? "s" : ""} inconnue{m.zones_inconnues > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
