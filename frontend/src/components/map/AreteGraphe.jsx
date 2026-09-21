import { BaseEdge } from "@xyflow/react";

// Lien de l'Atlas : courbe douce du bord d'un robot au bord de l'autre, flèche vers la cible.
// Le style (largeur, tirets, opacité) vient de `data` ; l'Atlas y superpose survol et focus via `style`.
export default function AreteGraphe({ id, sourceX, sourceY, targetX, targetY, data, style, markerEnd }) {
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const L = Math.hypot(dx, dy) || 1;
  const ux = dx / L;
  const uy = dy / L;
  const sx = sourceX + ux * data.r1;
  const sy = sourceY + uy * data.r1;
  const ex = targetX - ux * (data.r2 + 3);
  const ey = targetY - uy * (data.r2 + 3);
  const cx = (sx + ex) / 2 - uy * L * 0.09;
  const cy = (sy + ey) / 2 + ux * L * 0.09;
  return (
    <BaseEdge
      id={id}
      path={`M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}`}
      markerEnd={markerEnd}
      style={{
        stroke: data.couleur,
        strokeWidth: style?.strokeWidth ?? data.largeur,
        strokeDasharray: data.pointille ? "6 4" : undefined,
        opacity: style?.opacity ?? data.opacite,
        transition: "opacity 160ms ease, stroke-width 160ms ease",
      }}
    />
  );
}
