import { useMemo } from "react";
import { Handle, Position } from "@xyflow/react";
import { genererConstellation } from "@/lib/constellation";

// Territoire = voile coloré très atténué + constellation de micro-points reliés par
// des filaments (spécification « ciel de nuit »). Le survol est géré par proximité au
// niveau de la carte (les zones d'interaction des arêtes recouvrent les frontières).
export default function RegionNode({ data }) {
  const survol = !!data.survol;
  const pointille = data.confirme === false; // territoire découvert, pas encore validé par l'organisation
  const vbW = data.wCible || data.w;
  const vbH = data.hCible || data.h;

  const constel = useMemo(
    () => genererConstellation(data.points, vbW, vbH, data.id, data.couleur),
    [data.points, vbW, vbH, data.id, data.couleur]
  );

  return (
    <div
      style={{ width: data.w, height: data.h, pointerEvents: "none" }}
      className="relative"
      data-testid={`region-${data.id}`}
    >
      <Handle type="target" id="t-l" position={Position.Left} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="source" id="s-l" position={Position.Left} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="target" id="t-r" position={Position.Right} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <Handle type="source" id="s-r" position={Position.Right} className="!h-0 !w-0 !border-0 !bg-transparent" style={{ top: "50%" }} />
      <svg
        viewBox={`0 0 ${vbW} ${vbH}`}
        width={data.w}
        height={data.h}
        preserveAspectRatio="none"
        className={`absolute inset-0 transition-opacity duration-300 ${data.attenue ? "opacity-40" : "opacity-100"}`}
        style={{ overflow: "visible" }}
      >
        {data.path ? (
          <path
            d={data.path}
            fill={survol ? `${data.couleur}1A` : `${data.couleur}0E`}
            stroke={survol ? `${data.couleur}59` : `${data.couleur}2E`}
            strokeWidth={survol ? 2.2 : 1.6}
            strokeDasharray={pointille ? "8 6" : undefined}
            strokeLinejoin="round"
            style={{ transition: "fill 200ms, stroke 200ms" }}
            data-testid={`region-membrane-${data.id}`}
          />
        ) : (
          <rect width={data.w} height={data.h} rx={56} fill={`${data.couleur}0A`} stroke={`${data.couleur}30`} strokeWidth={1.5} strokeDasharray={pointille ? "8 6" : undefined} />
        )}
        {/* Constellation : texture du niveau Domaine — elle s'efface au niveau Jumeau
            (convention map UI : le décor cède la place au contenu de travail) */}
        <g data-testid={`constellation-${data.id}`} opacity={(data.niveau || 2) >= 3 ? 0 : 1} style={{ transition: "opacity 400ms" }}>
          {constel.liens.map((l, i) => (
            <line key={`l${i}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke={data.couleur} strokeWidth={0.7} opacity={l.o} strokeLinecap="round" />
          ))}
          {constel.points.map((p, i) => (
            <g key={`p${i}`}>
              {p.halo && <circle cx={p.x} cy={p.y} r={p.r * 3.2} fill={p.c} opacity={p.o * 0.14} />}
              <circle
                cx={p.x}
                cy={p.y}
                r={p.r}
                fill={p.c}
                opacity={p.o}
                className={p.scintille ? "etoile-scintille" : undefined}
                style={p.scintille ? { "--op-base": p.o, animationDuration: `${p.duree}s`, animationDelay: `${p.delai}s` } : undefined}
              />
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
