import { useEffect, useState } from "react";
import { CaretDown, CaretUp } from "@phosphor-icons/react";
import { DOMAINES, ETATS_RELATION } from "@/lib/domaines";

export default function AtlasLegende() {
  const [pliee, setPliee] = useState(() => typeof window !== "undefined" && window.innerWidth < 1500);

  // Repli automatique quand la fenêtre devient petite
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1500px)");
    const maj = (e) => { if (!e.matches) setPliee(true); };
    mq.addEventListener("change", maj);
    return () => mq.removeEventListener("change", maj);
  }, []);

  if (pliee) {
    return (
      <button
        onClick={() => setPliee(false)}
        data-testid="legende-toggle"
        className="glass absolute bottom-4 left-4 z-10 flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-code text-[10px] text-white/50 transition-colors hover:text-white"
      >
        Légende <CaretDown size={11} />
      </button>
    );
  }

  return (
    <div className="glass absolute bottom-24 left-4 z-10 max-w-[400px] rounded-lg px-3 py-2 min-[1500px]:bottom-4" data-testid="map-legend">
      <div className="flex items-center justify-between gap-3">
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
        <button onClick={() => setPliee(true)} data-testid="legende-replier" className="shrink-0 text-white/35 transition-colors hover:text-white" title="Replier la légende">
          <CaretUp size={11} />
        </button>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 border-t border-white/[0.06] pt-1.5">
        {Object.entries(DOMAINES).filter(([d]) => d !== "Non classé").map(([d, c]) => (
          <span key={d} className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-white/40">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} /> {d}
          </span>
        ))}
      </div>
    </div>
  );
}
