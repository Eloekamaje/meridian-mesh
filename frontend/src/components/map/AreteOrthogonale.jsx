import { memo, useMemo } from "react";
import { construireD, ancreLabel, pointsMarqueurs } from "@/lib/routeur";

// Arête orthogonale — rendue par le moteur de routage dédié (data.points), pas par React Flow
const STYLES = {
  observee: { stroke: "#0E7490", strokeWidth: 2, marqueur: "marqueur-teal" },
  supposee: { stroke: "#D97706", strokeWidth: 1.7, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  contestee: { stroke: "#D97706", strokeWidth: 2, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  validation: { stroke: "#6D28D9", strokeWidth: 1.8, strokeDasharray: "7 5", marqueur: "marqueur-violet" },
  obsolete: { stroke: "rgba(17,17,16,0.4)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25, marqueur: "marqueur-ardoise" },
  confirmee: { stroke: "rgba(17,17,16,0.45)", strokeWidth: 1.4, opacity: 0.75, marqueur: "marqueur-ardoise" },
};

export default memo(function AreteOrthogonale({ id, data, selected, style: styleProp }) {
  const { points, sauts, etat, restreinte, nouvelle, label, survolee, estompee, niveau, agregat } = data;
  const base = STYLES[etat] || STYLES.confirmee;
  const actif = survolee || selected;

  const d = useMemo(() => construireD(points, sauts), [points, sauts]);
  const labelPos = useMemo(() => ancreLabel(points), [points]);
  const marqueurs = useMemo(() => (etat === "observee" ? pointsMarqueurs(points) : []), [points, etat]);

  // Libellés : survol/sélection, voie agrégée « N flux », ou zoom Application prononcé (jamais par défaut en vue Domaines)
  const afficheLabel = label && (actif || data.zoomFort || agregat);
  // Animation directionnelle discrète : uniquement survol, sélection ou nouveauté
  const anime = etat === "observee" && (actif || nouvelle) && !estompee && !agregat;

  const style = {
    ...base,
    ...(agregat ? { strokeWidth: 3 } : {}),
    ...(data.focus ? { strokeWidth: 2.4, opacity: 1 } : {}),
    ...(restreinte ? { opacity: 0.35, strokeDasharray: "3 5" } : {}),
    ...(styleProp || {}),
    ...(actif ? { strokeWidth: (base.strokeWidth || 1.5) + 1, opacity: 1 } : {}),
    ...(estompee ? { opacity: 0.18 } : {}),
  };

  return (
    <g data-testid={`arete-${id}`}>
      {/* Zone d'interaction fine — ne bloque pas le déplacement de la carte */}
      <path d={d} fill="none" stroke="transparent" strokeWidth={data.tactile ? 22 : 10} style={{ pointerEvents: "stroke" }} />
      <path
        d={d}
        fill="none"
        stroke={style.stroke}
        strokeWidth={style.strokeWidth}
        strokeDasharray={style.strokeDasharray}
        strokeLinecap="round"
        opacity={style.opacity ?? 1}
        markerEnd={base.marqueur ? `url(#${base.marqueur})` : undefined}
        markerStart={data.bidi && base.marqueur ? `url(#${base.marqueur})` : undefined}
        style={{ transition: "opacity 200ms", pointerEvents: "none" }}
      />
      {/* Point d'arrivée coloré selon le domaine cible — la couleur de l'arête porte le statut, le point porte le domaine */}
      {data.couleurCible && points?.length > 1 && !estompee && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={3.2} fill={data.couleurCible} stroke="#fff" strokeWidth={1} style={{ pointerEvents: "none" }} />
      )}
      {/* Marqueurs directionnels espacés (relation observée) */}
      {!estompee && marqueurs.map((m, i) => (
        <path key={i} d="M -3 -3 L 4 0 L -3 3 Z" fill={base.stroke} opacity={0.75} transform={`translate(${m.x} ${m.y}) rotate(${m.angle})`} />
      ))}
      {/* Animation directionnelle : point lumineux discret, uniquement survol/sélection/nouveauté */}
      {anime && (
        <circle r={2.6} fill="#0E7490">
          <animateMotion dur="3.2s" repeatCount="indefinite" path={d} />
        </circle>
      )}
      {/* Capsule de libellé sur le segment horizontal le plus long */}
      {afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect x={-(label.length * 3.4 + 10)} y={-9} width={label.length * 6.8 + 20} height={18} rx={9} fill="rgba(255,255,255,0.95)" stroke="#E5E5E3" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="IBM Plex Mono" fill="#3F3F3C">
            {label}
          </text>
        </g>
      )}
      {nouvelle && !afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect x={-30} y={-9} width={60} height={18} rx={9} fill="rgba(255,255,255,0.95)" stroke="#0E7490" strokeDasharray="3 3" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="IBM Plex Mono" fill="#0E7490">nouvelle</text>
        </g>
      )}
    </g>
  );
});
