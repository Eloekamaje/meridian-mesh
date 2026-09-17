import { memo } from "react";

// Corridor macro (niveau Global) : arc monochrome cyan/ardoise entre les capitales des
// territoires. Trois états pilotés par le survol (Atlas) : repos quasi invisible,
// illuminé quand SON territoire est survolé, presque éteint quand c'est un autre.
// L'illumination ciblée lève l'ambiguïté des arcs qui traversent un domaine tiers.
export default memo(function AreteCorridor({ id, data, selected }) {
  const cap = data?.capitales;
  if (!cap) return null;
  const { sx, sy, tx, ty } = cap;
  const dx = tx - sx;
  const dy = ty - sy;
  const L = Math.hypot(dx, dy) || 1;
  const k = Math.min(0.16 * L, 90) * (data?.sens || 1);
  const d = `M ${sx} ${sy} Q ${(sx + tx) / 2 - (dy / L) * k} ${(sy + ty) / 2 + (dx / L) * k} ${tx} ${ty}`;

  const lumineux = selected || data?.survolee || data?.miseEnAvant;
  const eteint = data?.estompee && !lumineux;
  const sortie = data?.sortie ?? 1;
  const coreOp = (lumineux ? 1 : eteint ? 0.05 : 0.16) * sortie;
  const haloOp = (lumineux ? 0.3 : eteint ? 0 : 0.05) * sortie;
  const largeur = lumineux ? 2.4 : 1.5;

  return (
    <g data-testid={`arete-${id}`} style={{ transition: "opacity 250ms" }}>
      <path d={d} fill="none" stroke="#25D0C8" strokeWidth={lumineux ? 9 : 6} strokeLinecap="round" opacity={haloOp} style={{ transition: "opacity 250ms, stroke-width 250ms" }} />
      <path
        d={d}
        fill="none"
        stroke="#25D0C8"
        strokeWidth={largeur}
        strokeLinecap="round"
        opacity={coreOp}
        strokeDasharray={data?.actif ? "7 10" : undefined}
        className={data?.actif ? "corridor-actif" : undefined}
        style={{ transition: "opacity 250ms, stroke-width 250ms" }}
      />
      <path d={d} fill="none" stroke="transparent" strokeWidth={16} style={{ pointerEvents: "stroke" }} />
    </g>
  );
});
