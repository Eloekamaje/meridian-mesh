export default function RegionNode({ data }) {
  return (
    <div
      style={{ width: data.w, height: data.h, pointerEvents: "none" }}
      className="relative rounded-2xl border border-white/[0.05] bg-white/[0.015]"
      data-testid={`region-${data.id}`}
    >
      <span
        className="absolute left-4 top-3 font-code text-[10px] uppercase tracking-[0.3em]"
        style={{ color: data.couleur }}
      >
        {data.label}
      </span>
    </div>
  );
}
