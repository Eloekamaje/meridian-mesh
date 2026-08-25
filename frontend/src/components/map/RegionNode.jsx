import { MATURITES } from "@/lib/domaines";

export default function RegionNode({ data }) {
  const m = data.maturite;
  const mc = m ? MATURITES[m.niveau] || "#9CA3AF" : null;
  return (
    <div
      style={{ width: data.w, height: data.h, pointerEvents: "none" }}
      className="relative rounded-2xl border border-white/[0.05] bg-white/[0.015]"
      data-testid={`region-${data.id}`}
    >
      <div className="absolute left-4 top-3 flex items-center gap-2.5">
        <span className="font-code text-[10px] uppercase tracking-[0.3em]" style={{ color: data.couleur }}>
          {data.label}
        </span>
        {m && (
          <span
            className="rounded border px-1.5 py-0.5 font-code text-[8px] uppercase tracking-wider"
            style={{ color: mc, borderColor: `${mc}44`, backgroundColor: `${mc}10` }}
          >
            {m.niveau}
          </span>
        )}
      </div>
      {m && (
        <div className="absolute left-4 top-8 font-code text-[9px] text-white/30">
          {m.jumeaux} jumeaux connus · {m.relations_emergentes} relation{m.relations_emergentes > 1 ? "s" : ""} émergente{m.relations_emergentes > 1 ? "s" : ""} · {m.zones_inconnues} zone{m.zones_inconnues > 1 ? "s" : ""} inconnue{m.zones_inconnues > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
