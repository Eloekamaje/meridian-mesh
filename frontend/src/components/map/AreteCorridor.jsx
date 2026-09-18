import { memo } from "react";
import { construireD } from "@/lib/routeur";

// Corridor macro (niveau Global) : « voie hyper-espace » entre les FRONTIÈRES des
// territoires. Pathfinding orthogonal anti-obstacles (les membranes des domaines
// tiers sont infranchissables), rendu à très grand rayon (64px) : le zig-zag 90°
// devient une courbe organique qui ne traverse jamais un domaine.
// Trois états pilotés par le survol (Atlas) : repos quasi invisible,
// illuminé quand SON territoire est survolé, presque éteint quand c'est un autre.
export default memo(function AreteCorridor({ id, data, selected }) {
  const cap = data?.capitales;
  const points = data?.points;
  let d = null;
  if (points && points.length >= 2) {
    d = construireD(points, [], 64);
  } else if (cap) {
    // Secours : simple arc entre les capitales si le routage est indisponible
    const { sx, sy, tx, ty } = cap;
    const dx = tx - sx;
    const dy = ty - sy;
    const L = Math.hypot(dx, dy) || 1;
    const k = Math.min(0.16 * L, 90) * (data?.sens || 1);
    d = `M ${sx} ${sy} Q ${(sx + tx) / 2 - (dy / L) * k} ${(sy + ty) / 2 + (dx / L) * k} ${tx} ${ty}`;
  }
  if (!d) return null;

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
        strokeDasharray={data?.actif && lumineux ? "7 10" : undefined}
        className={data?.actif && lumineux ? "corridor-actif" : undefined}
        style={{ transition: "opacity 250ms, stroke-width 250ms" }}
      />
      <path d={d} fill="none" stroke="transparent" strokeWidth={16} style={{ pointerEvents: "stroke" }} />
    </g>
  );
});
