import { memo, useMemo } from "react";
import { construireD, ancreLabel, pointsMarqueurs } from "@/lib/routeur";

// Arête orthogonale — rendue par le moteur de routage dédié (data.points), pas par React Flow
const STYLES = {
  observee: { stroke: "#25D0C8", strokeWidth: 2, marqueur: "marqueur-teal" },
  supposee: { stroke: "#F2B84B", strokeWidth: 1.7, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  contestee: { stroke: "#F2B84B", strokeWidth: 2, strokeDasharray: "6 6", marqueur: "marqueur-orange" },
  validation: { stroke: "#9B87F5", strokeWidth: 1.8, strokeDasharray: "7 5", marqueur: "marqueur-violet" },
  obsolete: { stroke: "rgba(148,163,184,0.65)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25, marqueur: "marqueur-ardoise" },
  confirmee: { stroke: "rgba(148,163,184,0.7)", strokeWidth: 1.4, opacity: 0.75, marqueur: "marqueur-ardoise" },
};

export default memo(function AreteOrthogonale({ id, data, selected, style: styleProp }) {
  const { points, sauts, etat, restreinte, nouvelle, label, survolee, estompee, niveau, agregat } = data;
  const base = STYLES[etat] || STYLES.confirmee;
  const actif = survolee || selected;

  // Niveaux 1-2 « constellation » : arcs courbes lumineux entre les territoires/étoiles.
  // Niveau 3+ : routage orthogonal précis (lecture schéma de travail).
  const courbe = (niveau || 3) <= 2;
  const d = useMemo(() => {
    if (!courbe || !points || points.length < 2) return construireD(points, sauts);
    const a = points[0];
    const b = points[points.length - 1];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const L = Math.hypot(dx, dy) || 1;
    const sens = [...id].reduce((s, c) => s + c.charCodeAt(0), 0) % 2 === 0 ? 1 : -1;
    const k = Math.min(0.13 * L, 54) * sens;
    return `M ${a.x} ${a.y} Q ${(a.x + b.x) / 2 - (dy / L) * k} ${(a.y + b.y) / 2 + (dx / L) * k} ${b.x} ${b.y}`;
  }, [points, sauts, courbe, id]);
  const labelPos = useMemo(() => ancreLabel(points), [points]);
  const marqueurs = useMemo(() => (etat === "observee" && !courbe ? pointsMarqueurs(points) : []), [points, etat, courbe]);

  // Libellés : survol/sélection toujours visibles ; sinon arbitrés par le moteur de labels
  // (labelMasque = un label plus prioritaire occupe déjà cette zone)
  const afficheLabel = label && (actif || (!data.labelMasque && (data.zoomFort || agregat)));
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
  // Fondu d'entrée en bande Global ↔ Domaine : l'arête se révèle progressivement
  const entree = data.entree ?? 1;
  if (entree < 1) style.opacity = (style.opacity ?? 1) * entree;

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
      {/* Point d'arrivée coloré selon le domaine cible — la couleur de l'arête porte le statut, le point porte le domaine */}
      {data.couleurCible && points?.length > 1 && !estompee && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={3.2} fill={data.couleurCible} stroke="#071019" strokeWidth={1} style={{ pointerEvents: "none" }} />
      )}
      {/* Marqueurs directionnels espacés (relation observée) */}
      {!estompee && marqueurs.map((m, i) => (
        <path key={i} d="M -3 -3 L 4 0 L -3 3 Z" fill={base.stroke} opacity={0.75} transform={`translate(${m.x} ${m.y}) rotate(${m.angle})`} />
      ))}
      {/* Animation directionnelle : point lumineux discret, uniquement survol/sélection/nouveauté */}
      {anime && (
        <circle r={2.6} fill="#25D0C8">
          <animateMotion dur="3.2s" repeatCount="indefinite" path={d} />
        </circle>
      )}
      {/* Capsule de libellé sur le segment horizontal le plus long */}
      {afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect x={-(label.length * 3.4 + 10)} y={-9} width={label.length * 6.8 + 20} height={18} rx={9} fill="rgba(15,29,40,0.95)" stroke="rgba(148,163,184,0.16)" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="IBM Plex Mono" fill="#D8E2EA">
            {label}
          </text>
        </g>
      )}
      {nouvelle && !afficheLabel && labelPos && (
        <g transform={`translate(${labelPos.x} ${labelPos.y})`} style={{ pointerEvents: "none" }}>
          <rect x={-30} y={-9} width={60} height={18} rx={9} fill="rgba(15,29,40,0.95)" stroke="#25D0C8" strokeDasharray="3 3" />
          <text textAnchor="middle" dominantBaseline="central" fontSize={10} fontFamily="IBM Plex Mono" fill="#25D0C8">nouvelle</text>
        </g>
      )}
    </g>
  );
});
