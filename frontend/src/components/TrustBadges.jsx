import { Gauge, GridFour, Clock, Warning } from "@phosphor-icons/react";
import { couleurConfiance } from "@/lib/domaines";

export default function TrustBadges({ indicateurs }) {
  if (!indicateurs) return null;
  const { confiance, couverture, fraicheur, contradictions } = indicateurs;

  const chip = (color) => ({
    borderColor: `${color}44`,
    color,
    backgroundColor: `${color}14`,
  });

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="trust-badges">
      <span className="inline-flex items-center gap-1.5 rounded border px-2 py-1 font-code text-[11px]" style={chip(couleurConfiance(confiance))} data-testid="trust-confiance">
        <Gauge size={13} /> Confiance {confiance} %
      </span>
      <span className="inline-flex items-center gap-1.5 rounded border px-2 py-1 font-code text-[11px]" style={chip(couleurConfiance(couverture))} data-testid="trust-couverture">
        <GridFour size={13} /> Couverture {couverture} %
      </span>
      <span className="inline-flex items-center gap-1.5 rounded border px-2 py-1 font-code text-[11px]" style={chip("#94A3B8")} data-testid="trust-fraicheur">
        <Clock size={13} /> Fraîcheur {fraicheur}
      </span>
      <span
        className="inline-flex items-center gap-1.5 rounded border px-2 py-1 font-code text-[11px]"
        style={chip(contradictions > 0 ? "#F59E0B" : "#10B981")}
        data-testid="trust-contradictions"
      >
        <Warning size={13} /> {contradictions} contradiction{contradictions > 1 ? "s" : ""}
      </span>
    </div>
  );
}
