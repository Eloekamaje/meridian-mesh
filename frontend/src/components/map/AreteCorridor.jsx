import { memo } from "react";

// Corridor macro (niveau Global) : arc lumineux « ligne aérienne » entre les capitales
// des territoires — dégradé couleur source → cible, halo doux, flux animé si activité.
// Les ancres (capitales = positions des étiquettes de domaines) sont pré-calculées
// dans atlasGraph ; les poignées de boîte React Flow ne sont pas utilisées.
export default memo(function AreteCorridor({ id, data, selected }) {
  const cap = data?.capitales;
  if (!cap) return null;
  const { sx, sy, tx, ty } = cap;
  const dx = tx - sx;
  const dy = ty - sy;
  const L = Math.hypot(dx, dy) || 1;
  const k = Math.min(0.16 * L, 90) * (data?.sens || 1);
  const d = `M ${sx} ${sy} Q ${(sx + tx) / 2 - (dy / L) * k} ${(sy + ty) / 2 + (dx / L) * k} ${tx} ${ty}`;
  const gid = `grad-${id}`;
  return (
    <g data-testid={`arete-${id}`}>
      <defs>
        <linearGradient id={gid} gradientUnits="userSpaceOnUse" x1={sx} y1={sy} x2={tx} y2={ty}>
          <stop offset="0%" stopColor={data.couleurA} />
          <stop offset="100%" stopColor={data.couleurB} />
        </linearGradient>
      </defs>
      <path d={d} fill="none" stroke={`url(#${gid})`} strokeWidth={selected ? 10 : 7} strokeLinecap="round" opacity={selected ? 0.24 : 0.16} />
      <path
        d={d}
        fill="none"
        stroke={`url(#${gid})`}
        strokeWidth={selected ? 2.6 : 2}
        strokeLinecap="round"
        opacity={selected ? 1 : 0.9}
        strokeDasharray={data?.actif ? "7 10" : undefined}
        className={data?.actif ? "corridor-actif" : undefined}
        style={{ transition: "stroke-width 200ms, opacity 200ms" }}
      />
      <path d={d} fill="none" stroke="transparent" strokeWidth={16} style={{ pointerEvents: "stroke" }} />
    </g>
  );
});
