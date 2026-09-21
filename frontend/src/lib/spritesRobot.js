// Sprites du robot-jumeau pour les rendus canvas : un par couleur de domaine, dessinés une seule fois
// (même personnage que RobotJumeauSvg). drawImage d'un sprite coûte une fraction d'un SVG dans le DOM.
import { COULEURS_DOMAINES } from "./laboEchelle";

// --- Sprite du robot-jumeau (même dessin que RobotJumeauSvg), un par couleur de domaine ------------
export const svgRobot = (c) => `<svg xmlns="http://www.w3.org/2000/svg" width="124" height="190" viewBox="-62 -88 124 190">
<defs><linearGradient id="k" x1="0" y1="0" x2="0.35" y2="1"><stop offset="0" stop-color="#f2f8ff"/><stop offset=".55" stop-color="#cfe3f7"/><stop offset="1" stop-color="#8fb0cf"/></linearGradient>
<linearGradient id="v" x1="0" y1="0" x2="0.2" y2="1"><stop offset="0" stop-color="#123651"/><stop offset="1" stop-color="#05141f"/></linearGradient>
<radialGradient id="o"><stop offset="0" stop-color="#fff"/><stop offset=".45" stop-color="${c}"/><stop offset="1" stop-color="${c}"/></radialGradient></defs>
<ellipse cx="0" cy="8" rx="56" ry="74" fill="${c}" opacity=".3"/><ellipse cx="0" cy="8" rx="56" ry="74" fill="none" stroke="${c}" stroke-width="2.4" opacity=".75"/>
<path d="M -30 34 C -30 18, -16 10, 0 10 C 16 10, 30 18, 30 34 L 30 52 C 30 66, 16 74, 0 74 C -16 74, -30 66, -30 52 Z" fill="url(#k)"/>
<ellipse cx="0" cy="46" rx="13" ry="13" fill="rgba(20,70,110,.5)"/><ellipse cx="0" cy="46" rx="6.5" ry="6.5" fill="url(#o)"/>
<ellipse cx="-38" cy="40" rx="9" ry="14" fill="url(#k)" transform="rotate(-12 -38 40)"/><ellipse cx="38" cy="40" rx="9" ry="14" fill="url(#k)" transform="rotate(12 38 40)"/>
<rect x="-48" y="-52" width="96" height="76" rx="34" fill="url(#k)"/><rect x="-38" y="-42" width="76" height="52" rx="25" fill="url(#v)"/>
<ellipse cx="-15" cy="-16" rx="9.5" ry="9.5" fill="url(#o)"/><ellipse cx="15" cy="-16" rx="9.5" ry="9.5" fill="url(#o)"/>
<ellipse cx="-17.5" cy="-19" rx="3" ry="3" fill="#fff" opacity=".95"/><ellipse cx="12.5" cy="-19" rx="3" ry="3" fill="#fff" opacity=".95"/>
<line x1="0" y1="-52" x2="0" y2="-70" stroke="#cfe3f7" stroke-width="3.5" stroke-linecap="round"/><circle cx="0" cy="-74" r="6" fill="url(#o)"/>
<ellipse cx="-50" cy="-16" rx="8" ry="13" fill="url(#k)"/><ellipse cx="50" cy="-16" rx="8" ry="13" fill="url(#k)"/>
<ellipse cx="0" cy="92" rx="36" ry="6.5" fill="${c}" opacity=".75"/></svg>`;

export function chargerSprites() {
  return Promise.all(
    COULEURS_DOMAINES.map(
      (c) =>
        new Promise((resolve) => {
          const img = new Image();
          img.onload = () => {
            const cv = document.createElement("canvas");
            cv.width = 124;
            cv.height = 190;
            cv.getContext("2d").drawImage(img, 0, 0);
            resolve(cv);
          };
          img.onerror = () => resolve(null);
          img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgRobot(c))}`;
        })
    )
  );
}

