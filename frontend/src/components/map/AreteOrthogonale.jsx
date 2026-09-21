import { memo, useMemo } from "react";
import { construireD, ancreLabel, pointsMarqueurs } from "@/lib/routeur";

// Arête orthogonale — rendue par le moteur de routage dédié (data.points), pas par React Flow
const STYLES = {
  observee: { stroke: "#60A5FA", strokeWidth: 2, marqueur: "marqueur-teal" },
  supposee: { stroke: "#F2B84B", strokeWidth: 1.7, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  contestee: { stroke: "#F2B84B", strokeWidth: 2, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  validation: { stroke: "#60A5FA", strokeWidth: 1.8, strokeDasharray: "7 5", marqueur: "marqueur-violet" },
  obsolete: { stroke: "rgba(148,163,184,0.65)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25, marqueur: "marqueur-ardoise" },
  confirmee: { stroke: "rgba(148,163,184,0.7)", strokeWidth: 1.4, opacity: 0.75, marqueur: "marqueur-ardoise" },
};

export default memo(function AreteOrthogonale({ id, data, selected, style: styleProp }) {
  const { points, sauts, etat, restreinte, nouvelle, label, survolee, estompee, niveau, agregat } = data;
  const base = STYLES[etat] || STYLES.confirmee;
  const actif = survolee || selected;

  // Ossature orthogonale à TOUS les niveaux de zoom : la même architecture de
  // relations (lignes droites à coudes arrondis) au Domaine comme au Jumeau —
  // dézoomer ne change plus la topologie visuelle, seulement l'échelle.
  const d = useMemo(() => construireD(points, sauts, data.routee ? 64 : undefined), [points, sauts, data.routee]);
  const labelPos = useMemo(() => ancreLabel(points), [points]);
  const marqueurs = useMemo(() => (etat === "observee" && !data.routee ? pointsMarqueurs(points) : []), [points, etat, data.routee]);

  // Libellés : survol/sélection toujours visibles ; sinon arbitrés par le moteur de labels
  const afficheLabel = label && (actif || (!data.labelMasque && (data.zoomFort || agregat)));
  // Animation directionnelle : point lumineux voyageant le long de l'arête
  const anime = etat === "observee" && (actif || nouvelle) && !estompee && !agregat && !data.cadastre;

  let style = {
    ...base,
    ...(agregat ? { strokeWidth: 3 } : {}),
    ...(data.focus ? { strokeWidth: 2.4, opacity: 1 } : {}),
    ...(restreinte ? { opacity: 0.35, strokeDasharray: "3 5" } : {}),
    ...(styleProp || {}),
    ...(actif ? { strokeWidth: (base.strokeWidth || 1.5) + 1, opacity: 1 } : {}),
    ...(estompee ? { opacity: 0.18 } : {}),
  };

  const estCadastre = !!data.cadastre || !!data.estompee;
  if (estCadastre) {
    style = { ...style, stroke: "rgba(148,163,184,0.35)", strokeWidth: 1, strokeDasharray: "4 4", opacity: 0.1 };
  }

  // Fondu d'entrée en bande Global ↔ Domaine : l'arête se révèle progressivement
  const entree = data.entree ?? 1;
  if (entree < 1 && !estCadastre) style.opacity = (style.opacity ?? 1) * entree;
  if (data.fonduPlongeon) {
    style.opacity = 0.04;
  }

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
        className={data.pulse ? "trait-pulse" : undefined}
        opacity={style.opacity ?? 1}
        markerEnd={base.marqueur ? `url(#${base.marqueur})` : undefined}
        markerStart={data.bidi && base.marqueur ? `url(#${base.marqueur})` : undefined}
        style={{ transition: "opacity 200ms", pointerEvents: "none" }}
      />
      {/* Point d'arrivée coloré selon le domaine cible */}
      {data.couleurCible && points?.length > 1 && !estompee && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={3.2} fill={data.couleurCible} stroke="#071019" strokeWidth={1} style={{ pointerEvents: "none" }} />
      )}
      {/* Marqueurs directionnels espacés (relation observée) */}
      {!estompee && marqueurs.map((m, i) => (
        <path key={i} d="M -3 -3 L 4 0 L -3 3 Z" fill={base.stroke} opacity={0.75} transform={`translate(${m.x} ${m.y}) rotate(${m.angle})`} />
      ))}
      {/* Animation directionnelle : particule lumineuse continue */}
      {anime && (
        <circle r={2.6} fill="#60A5FA">
          <animateMotion dur="3.2s" repeatCount="indefinite" path={d} />
        </circle>
      )}
      {/* Capsule de libellé sur le segment horizontal le plus long */}
      {afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect
            x={-(label.length * 3.6 + 12)}
            y={-10}
            width={label.length * 7.2 + 24}
            height={20}
            rx={10}
            fill="rgba(15,29,40,0.95)"
            stroke="rgba(148,163,184,0.16)"
            strokeWidth={1}
          />
          <text
            textAnchor="middle"
            dominantBaseline="central"
            fontSize={10}
            fontFamily="IBM Plex Mono"
            fontWeight="400"
            fill="#D8E2EA"
          >
            {label}
          </text>
        </g>
      )}
      {nouvelle && !afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect x={-30} y={-9} width={60} height={18} rx={9} fill="rgba(15,29,40,0.95)" stroke="#60A5FA" strokeDasharray="3 3" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="IBM Plex Mono" fill="#60A5FA">nouvelle</text>
        </g>
      )}
    </g>
  );
});
