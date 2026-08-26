import { MATURITES } from "@/lib/domaines";
import { Handle, Position } from "@xyflow/react";

export default function RegionNode({ data }) {
  const m = data.maturite;
  const mc = m ? MATURITES[m.niveau] || "#71716D" : null;
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
      <div
        className="nopan absolute left-0 top-0 w-full cursor-pointer px-7 pb-3 pt-5 transition-colors hover:bg-[#F7F7F6]"
        style={{ pointerEvents: "auto", borderRadius: "56px 56px 0 0" }}
        title="Clic : sélectionner le domaine · Double-clic : entrer dans le domaine"
        data-testid={`region-header-${data.id}`}
      >
        <div className="flex items-center gap-2.5">
          {data.halo && (
            <span className="halo-anim h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: data.couleur }} data-testid={`region-activite-${data.id}`} />
          )}
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
          <div className="mt-1 font-code text-[9px] text-[#71716D]">
            {m.jumeaux} jumeaux · {data.decouvertes ?? 0} découverte{(data.decouvertes ?? 0) > 1 ? "s" : ""} · {data.investigations ?? 0} investigation{(data.investigations ?? 0) > 1 ? "s" : ""} · {m.zones_inconnues} zone{m.zones_inconnues > 1 ? "s" : ""} inconnue{m.zones_inconnues > 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  );
}
