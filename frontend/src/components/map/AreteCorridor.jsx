import { memo } from "react";
import { construireD, ancreLabel } from "@/lib/routeur";
import { styleParEtat } from "@/lib/atlasGraph";

// Corridor parent : UN arc par couple de territoires, persistant du Global au Domaine.
// - Macro (detail→0) : voie cyan discrète entre les frontières, illuminée au survol.
// - Détail (detail→1) : voie « N flux » colorée par l'état dominant de ses relations.
// - Dissolution (sortie→0) : au niveau Jumeau, il fond pendant que ses membres naissent.
// Pathfinding orthogonal anti-obstacles (membranes tierces infranchissables),
// rendu à très grand rayon (64px) : « hybride fluide ».
export default memo(function AreteCorridor({ id, data, selected }) {
  const cap = data?.capitales;
  const points = data?.points;
  const detail = data?.detail ?? 0;
  const etat = data?.etat;
  let d = null;
  if (points && points.length >= 2) {
    // Orthogonal à grand rayon : les coudes 90° deviennent des courbes organiques
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
  // Couleur : cyan en macro, couleur d'état dominant en mode détail (transition douce)
  const st = etat ? styleParEtat({ etat, active: data?.actif }) : null;
  const couleur = detail > 0.5 && st ? st.stroke : "#60A5FA";
  const reposOp = 0.16 + 0.44 * detail;
  const coreOp = (lumineux ? 1 : eteint ? 0.05 : reposOp) * sortie;
  const haloOp = (lumineux ? 0.3 : eteint ? 0 : 0.05) * sortie;
  const largeur = lumineux ? 2.4 : 1.5 + 1.3 * detail;
  const anime = data?.actif && lumineux;
  // Pointillés d'état du corridor : trame LONGUE (voie principale), distincte du
  // pointillé court « 6 6 » des relations individuelles — sinon, à l'attache sur la
  // frontière, un corridor jaune et une relation jaune se lisent comme un seul arc.
  const pointillesEtat = detail > 0.5 && !anime && st?.strokeDasharray ? "14 10" : undefined;
  // Label « N flux » : se révèle avec le mode détail
  const labelPos = points?.length >= 2 && detail > 0.02 ? ancreLabel(points) : null;
  const label = data?.labelFlux;
  // Bornes de terminaison : courte barre perpendiculaire aux deux bouts du corridor —
  // marque « port du territoire » : l'arc S'ARRÊTE à la frontière, il ne se branche
  // pas sur une étoile et aucune relation ne « part » de son milieu.
  const borne = (a, b) => {
    const L = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const px = (-(b.y - a.y) / L) * 7;
    const py = ((b.x - a.x) / L) * 7;
    return `M ${a.x - px} ${a.y - py} L ${a.x + px} ${a.y + py}`;
  };
  const bornes = points?.length >= 2
    ? `${borne(points[0], points[1])} ${borne(points[points.length - 1], points[points.length - 2])}`
    : null;

  return (
    <g data-testid={`arete-${id}`} style={{ transition: "opacity 250ms" }}>
      <path d={d} fill="none" stroke={couleur} strokeWidth={lumineux ? 9 : 6} strokeLinecap="round" opacity={haloOp} style={{ transition: "opacity 250ms, stroke-width 250ms, stroke 250ms" }} />
      <path
        d={d}
        fill="none"
        stroke={couleur}
        strokeWidth={largeur}
        strokeLinecap="round"
        opacity={coreOp}
        strokeDasharray={anime ? "7 10" : pointillesEtat}
        className={anime ? "corridor-actif" : undefined}
        style={{ transition: "opacity 250ms, stroke-width 250ms, stroke 250ms" }}
      />
      <path d={d} fill="none" stroke="transparent" strokeWidth={16} style={{ pointerEvents: "stroke" }} />
      {bornes && (
        <path d={bornes} fill="none" stroke={couleur} strokeWidth={2.6} strokeLinecap="round" opacity={Math.min(1, coreOp + 0.35)} style={{ transition: "opacity 250ms, stroke 250ms" }} />
      )}
      {labelPos && label && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} opacity={detail * sortie} style={{ pointerEvents: "none", transition: "opacity 250ms" }}>
          <rect x={-(label.length * 3.4 + 10)} y={-9} width={label.length * 6.8 + 20} height={18} rx={9} fill="rgba(15,29,40,0.95)" stroke="rgba(148,163,184,0.16)" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="JetBrains Mono" fill="#D8E2EA">
            {label}
          </text>
        </g>
      )}
    </g>
  );
});
