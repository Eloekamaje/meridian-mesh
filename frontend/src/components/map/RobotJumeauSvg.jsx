import { memo, useId } from "react";

// Robot-jumeau vectoriel — le personnage du film (remotion-meridian/src/vector/Robot.tsx), porté en
// composant React SANS Remotion. Net à toute taille, transparent (contrairement à robot-jumeau.jpg dont
// le damier est cuit dans l'image), et TEINTÉ : yeux, cœur, antenne et aura prennent la couleur du groupe
// (domaine ou communauté), la coque reste blanche. Un jumeau « compris » (sélectionné) sourit.
//
// À utiliser avec <style>{STYLES_ROBOT}</style> une fois dans la page (clignement, flottement).

export const STYLES_ROBOT = `
@keyframes robot-flotte { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-2.5px) } }
@keyframes robot-clign { 0%,93%,100% { transform: scaleY(1) } 96% { transform: scaleY(0.1) } }
.robot-flotte { animation: robot-flotte 4.6s ease-in-out infinite; }
.robot-oeil { transform-box: fill-box; transform-origin: center; animation: robot-clign 6.4s infinite; }
@media (prefers-reduced-motion: reduce) { .robot-flotte, .robot-oeil { animation: none; } }
`;

const RATIO = 124 / 190; // largeur / hauteur du cadrage

const versRgb = (hex) => {
  const h = String(hex).replace("#", "");
  const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.padEnd(6, "0");
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
};
const melanger = (hex, cible, t) => {
  const a = versRgb(hex);
  const b = cible === "blanc" ? [255, 255, 255] : [0, 0, 0];
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
};

// `leger` : ni filtres SVG (flou) ni animations — indispensable quand on affiche des centaines de robots.
function RobotJumeauSvg({ hauteur = 64, couleur = "#38BDF8", ecart = false, content = false, delai = 0, leger = false }) {
  const id = useId().replace(/:/g, "");
  const largeur = Math.round(hauteur * RATIO);
  return (
    <div className={leger ? undefined : "robot-flotte"} style={{ width: largeur, height: hauteur, animationDelay: `${-delai}s` }} aria-hidden="true">
      <svg width={largeur} height={hauteur} viewBox="-62 -88 124 190" style={{ overflow: "visible", display: "block" }}>
        <defs>
          <linearGradient id={`coque-${id}`} x1="0" y1="0" x2="0.35" y2="1">
            <stop offset="0%" stopColor="#f2f8ff" />
            <stop offset="55%" stopColor="#cfe3f7" />
            <stop offset="100%" stopColor="#8fb0cf" />
          </linearGradient>
          <linearGradient id={`visiere-${id}`} x1="0" y1="0" x2="0.2" y2="1">
            <stop offset="0%" stopColor="#123651" />
            <stop offset="100%" stopColor="#05141f" />
          </linearGradient>
          <radialGradient id={`oeil-${id}`}>
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="45%" stopColor={melanger(couleur, "blanc", 0.3)} />
            <stop offset="100%" stopColor={melanger(couleur, "noir", 0.2)} />
          </radialGradient>
          <filter id={`lueur-${id}`} x="-150%" y="-150%" width="400%" height="400%">
            <feGaussianBlur stdDeviation="3.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Écart déclaré ↔ calculé : halo pointillé orange autour du jumeau */}
        {ecart && <ellipse cx="0" cy="8" rx="59" ry="90" fill="none" stroke="#F59E0B" strokeWidth="3.4" strokeDasharray="8 6" opacity="0.95" />}

        {/* Aura de la couleur du groupe : c'est elle qui porte la légende — assez marquée pour se lire de loin */}
        <ellipse cx="0" cy="8" rx="56" ry="74" fill={couleur} opacity="0.3" />
        <ellipse cx="0" cy="8" rx="56" ry="74" fill="none" stroke={couleur} strokeWidth="2.4" opacity="0.75" />

        {/* Buste flottant, sans jambes */}
        <path d="M -30 34 C -30 18, -16 10, 0 10 C 16 10, 30 18, 30 34 L 30 52 C 30 66, 16 74, 0 74 C -16 74, -30 66, -30 52 Z" fill={`url(#coque-${id})`} opacity="0.97" />
        <ellipse cx="0" cy="46" rx="13" ry="13" fill="rgba(20,70,110,0.5)" />
        <ellipse cx="0" cy="46" rx="6.5" ry="6.5" fill={`url(#oeil-${id})`} filter={leger ? undefined : `url(#lueur-${id})`} />

        {/* Bras */}
        <ellipse cx="-38" cy="40" rx="9" ry="14" fill={`url(#coque-${id})`} transform="rotate(-12 -38 40)" />
        <ellipse cx="38" cy="40" rx="9" ry="14" fill={`url(#coque-${id})`} transform="rotate(12 38 40)" />

        {/* Tête et visière */}
        <rect x="-48" y="-52" width="96" height="76" rx="34" fill={`url(#coque-${id})`} />
        <rect x="-38" y="-42" width="76" height="52" rx="25" fill={`url(#visiere-${id})`} />

        {/* Yeux : ronds, ou l'arc souriant du jumeau qui a compris (sélection) */}
        <g filter={leger ? undefined : `url(#lueur-${id})`}>
          {content ? (
            <g fill="none" stroke={melanger(couleur, "blanc", 0.35)} strokeWidth="5.2" strokeLinecap="round">
              <path d="M -22 -13 Q -15 -24, -8 -13" />
              <path d="M 8 -13 Q 15 -24, 22 -13" />
            </g>
          ) : (
            <g className={leger ? undefined : "robot-oeil"} style={{ animationDelay: `${-delai * 1.7}s` }}>
              <ellipse cx="-15" cy="-16" rx="9.5" ry="9.5" fill={`url(#oeil-${id})`} />
              <ellipse cx="15" cy="-16" rx="9.5" ry="9.5" fill={`url(#oeil-${id})`} />
              <ellipse cx="-17.5" cy="-19" rx="3" ry="3" fill="#ffffff" opacity="0.95" />
              <ellipse cx="12.5" cy="-19" rx="3" ry="3" fill="#ffffff" opacity="0.95" />
            </g>
          )}
        </g>

        {/* Antenne et écouteurs */}
        <line x1="0" y1="-52" x2="0" y2="-70" stroke="#cfe3f7" strokeWidth="3.5" strokeLinecap="round" />
        <circle cx="0" cy="-74" r="6" fill={`url(#oeil-${id})`} filter={leger ? undefined : `url(#lueur-${id})`} />
        <ellipse cx="-50" cy="-16" rx="8" ry="13" fill={`url(#coque-${id})`} />
        <ellipse cx="50" cy="-16" rx="8" ry="13" fill={`url(#coque-${id})`} />

        {/* Socle lumineux, de la couleur du groupe */}
        <ellipse cx="0" cy="92" rx="36" ry="6.5" fill={couleur} opacity="0.75" />
      </svg>
    </div>
  );
}

export default memo(RobotJumeauSvg);
